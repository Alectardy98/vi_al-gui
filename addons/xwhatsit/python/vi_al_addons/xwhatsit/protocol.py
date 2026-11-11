# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded original utility protocol and optional eight-byte XCAL settings.

One caller owns the selected Vial handle. No discovery, automatic retries of
mutations, GPIO experiments, or layout tables live in this client.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import time


class ProtocolError(RuntimeError):
    pass


class KeysHeld(ProtocolError):
    pass


def supported(keyboard):
    uid = getattr(keyboard, 'keyboard_id', None)
    if isinstance(uid, int):
        if not 0 <= uid < 1 << 64:
            return False
        uid = uid.to_bytes(8, 'little')
    if not isinstance(uid, bytes):
        return False
    profiles = json.loads(Path(__file__).with_name('profiles.json').read_text())
    return any(uid.hex() == p['uid'] and (keyboard.rows, keyboard.cols) == (p['rows'], p['cols']) for p in profiles)


def crc8(data):
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ (7 if crc & 128 else 0)) & 255
    return crc


@dataclass(frozen=True)
class Settings:
    settle: int
    sample: int
    initial: int
    per_key: int
    groups: int
    margin: int

    def encode(self, max_groups=15, dac_max=4095):
        if not 1 <= self.settle <= 32 or not 1 <= self.sample <= 32:
            raise ProtocolError('Settling and sampling must be between 1 and 32.')
        exponents = []
        for repetitions in (self.initial, self.per_key):
            if repetitions not in (1, 2, 4, 8, 16, 32):
                raise ProtocolError('Averaging must be a power of two from 1 to 32.')
            exponents.append(repetitions.bit_length() - 1)
        if not 1 <= self.groups <= max_groups or not 0 <= self.margin <= dac_max:
            raise ProtocolError('Calibration groups or margin exceed this firmware’s limits.')
        data = bytes((0xa7, self.settle, self.sample, exponents[0] | (exponents[1] << 4), self.groups)) + struct.pack('<H', self.margin)
        return data + bytes((crc8(data),))

    @classmethod
    def decode(cls, data, max_groups=15, dac_max=4095):
        data = bytes(data)
        if len(data) != 8 or data[0] != 0xa7 or crc8(data[:7]) != data[7] or (data[3] & 15) > 5 or data[3] >> 4 > 5:
            raise ProtocolError('Invalid calibration record.')
        value = cls(data[1], data[2], 1 << (data[3] & 15), 1 << (data[3] >> 4), data[4], struct.unpack_from('<H', data, 5)[0])
        value.encode(max_groups, dac_max)
        return value


class Client:
    def __init__(self, keyboard):
        if not supported(keyboard):
            raise ProtocolError('This keyboard has no verified xwhatsit profile.')
        self.keyboard = keyboard
        self.handle = keyboard.dev
        self.rows, self.cols = keyboard.rows, keyboard.cols
        self.row_bytes = 4 if self.cols > 16 else 2 if self.cols > 8 else 1
        self.extension = False
        self.defaults = self.settings = None
        self._last_pressed = set()
        self._activity_at = 0.0
        self.background_allowed = True
        self._use_cached_matrix = False
        self._cached_matrix_supported = (getattr(keyboard, 'vial_protocol', -1) >= 3
                                         and (self.cols//8+1)*self.rows <= 28
                                         and callable(getattr(keyboard, 'matrix_poll', None))
                                         and callable(getattr(keyboard, 'get_unlock_status', None)))

    def exchange(self, op, payload=b'', timeout=2000):
        if len(payload) > 29:
            raise ProtocolError('Utility payload exceeds 29 bytes.')
        request = (b'\x55\xaa' + bytes((op,)) + bytes(payload)).ljust(32, b'\0')
        if self.handle.write(b'\0' + request) != 33:
            raise ProtocolError('USB command was not completely sent; it was not retried.')
        deadline = time.monotonic() + timeout / 1000
        for _ in range(16):
            remaining = max(1, round((deadline - time.monotonic()) * 1000))
            raw = bytes(self.handle.read(32, timeout_ms=remaining))
            if not raw:
                break
            if len(raw) != 32 or raw[:2] != b'\x55\xaa':
                if time.monotonic() >= deadline:
                    break
                continue
            if raw[2] == 0x24:
                raise KeysHeld('Release all keys; calibration will apply when the keyboard is idle.')
            if raw[2] != 0x22:
                raise ProtocolError('The firmware rejected utility command 0x%02X.' % op)
            return raw[3:]
        raise ProtocolError('No complete utility reply. The command was not retried.')

    def connect(self):
        raw = self.exchange(0x11)
        self.version = (raw[0], raw[1], int.from_bytes(raw[2:4], 'big'))
        if self.version < (2, 0, 2) or self.version[0] != 2:
            raise ProtocolError('Requires QMK xwhatsit utility protocol 2.0.2 or newer.')
        details = self.exchange(0x1a)
        if (details[1], details[0]) != (self.rows, self.cols):
            raise ProtocolError('The utility matrix does not match the Vial layout.')
        self.sense_rows = details[9]
        self.dac_max = int.from_bytes(details[7:9], 'little')
        if not 1 <= self.sense_rows <= self.rows or self.dac_max not in (1023, 4095):
            raise ProtocolError('Unsupported sensor matrix or DAC range.')
        self.settle, self.sample, self.auto = details[4], details[5], bool(details[6])
        self.debug = None
        if self.version >= (2, 1, 0):
            caps = self.exchange(0x30)
            if caps[:5] != b'XCAL\x01' or caps[5] not in range(1, 16) or int.from_bytes(caps[7:9], 'little') != self.dac_max:
                raise ProtocolError('Unknown XCAL capability descriptor.')
            self.extension, self.max_groups = True, caps[5]
            self.auto, self.debug = bool(caps[6] & 1), bool(caps[6] & 2)
            self.defaults = Settings.decode(caps[9:17], self.max_groups, self.dac_max)
            self.settings = self.get_settings()
        self.thresholds = self.get_thresholds()
        return self

    def get_settings(self):
        if not self.extension:
            raise ProtocolError('Live settings require the optional XCAL firmware extension.')
        return Settings.decode(self.exchange(0x31)[:8], self.max_groups, self.dac_max)

    def apply(self, settings):
        raw = settings.encode(self.max_groups, self.dac_max)
        echoed = self.exchange(0x32, raw, timeout=60000)
        if echoed[:8] != raw or self.get_settings() != settings:
            raise ProtocolError('Calibration save acknowledgement/readback did not match.')
        self.settings = settings
        self.thresholds = self.get_thresholds()
        return settings

    def reset_defaults(self):
        raw = self.exchange(0x33, timeout=60000)
        settings = Settings.decode(raw[:8], self.max_groups, self.dac_max)
        if settings != self.defaults or self.get_settings() != settings:
            raise ProtocolError('Default settings readback did not match.')
        self.settings = settings
        self.thresholds = self.get_thresholds()
        return settings

    def recalibrate(self):
        self.exchange(0x34, timeout=60000)
        self.thresholds = self.get_thresholds()
        return self.thresholds

    def get_thresholds(self):
        result = {}
        size = self.row_bytes * self.sense_rows
        group, count = 0, 1
        while group < count:
            bitmap = bytearray()
            threshold = None
            for offset in range(0, size, 26):
                raw = self.exchange(0x16, bytes((group, offset)))
                count = raw[0]
                if count > 15:
                    raise ProtocolError('Calibration group count is outside the supported range.')
                value = int.from_bytes(raw[1:3], 'little')
                if value > self.dac_max or (threshold is not None and threshold != value):
                    raise ProtocolError('Invalid or changing calibration threshold.')
                threshold = value
                bitmap += raw[3:3 + min(26, size - offset)]
            for row in range(self.sense_rows):
                bits = int.from_bytes(bitmap[row*self.row_bytes:(row+1)*self.row_bytes], 'little')
                for col in range(self.cols):
                    if count == 0 or bits & (1 << col):
                        if (row, col) in result:
                            raise ProtocolError('A key is assigned to multiple calibration groups.')
                        result[row, col] = (group, threshold)
            group += 1
        return result

    def key_state(self):
        if self._use_cached_matrix:
            # Same cached/debounced state used by Vial's Matrix Tester. Avoid
            # running another capacitive matrix scan just to check activity.
            raw = bytes(self.keyboard.matrix_poll())
            width = (self.cols+7)//8
            if len(raw) != 32 or raw[:2] != b'\x02\x03':
                raise ProtocolError('Invalid cached matrix response.')
            return {(row, col) for row in range(self.rows) for col in range(self.cols)
                    if int.from_bytes(raw[2+row*width:2+(row+1)*width], 'big') & (1 << col)}
        raw = bytearray()
        for offset in range(0, self.rows*self.row_bytes, 29):
            raw += self.exchange(0x15, bytes((offset,)))[:min(29, self.rows*self.row_bytes-offset)]
        return {(row, col) for row in range(self.rows) for col in range(self.cols)
                if int.from_bytes(raw[row*self.row_bytes:(row+1)*self.row_bytes], 'little') & (1 << col)}

    def read_signal(self, position):
        row, col = position
        if not 0 <= row < self.sense_rows or not 0 <= col < self.cols:
            return None
        sample = int.from_bytes(self.exchange(0x19, bytes((col, row, 1)))[:2], 'little')
        if sample > self.dac_max:
            raise ProtocolError('Signal sample exceeds the DAC range.')
        return sample

    def snapshot(self, position):
        return self.key_state(), self.read_signal(position)

    def observe_activity(self, pressed):
        if pressed or pressed != self._last_pressed:
            self._activity_at = time.monotonic()
        self._last_pressed = pressed
        self.background_allowed = not pressed and time.monotonic()-self._activity_at >= .35

    def frame(self, position, background=()):
        """Short individual reads, yielding between measurements.

        Initial fill may supply up to three background positions. Matrix state
        is checked before each one; typing pauses background measurements for
        350 ms after release. Never use Cap-Util's 14-key atomic measurement
        here: it pauses device scanning far longer than one-key requests.
        """
        self._use_cached_matrix = self._cached_matrix_supported and bool(self.keyboard.get_unlock_status(retries=1))
        try:
            pressed = self.key_state()
            added = sorted(pos for pos in pressed-self._last_pressed if pos[0] < self.sense_rows)
            if added:
                position = added[0]
            self.observe_activity(pressed)
            if background is None:
                background = ()
            elif len(background) == 2 and isinstance(background[0], int):
                background = (background,)
            readings = {}
            candidates = [position] + list(background[:3])
            for index, pos in enumerate(candidates):
                if pos in readings:
                    continue
                if index:
                    pressed = self.key_state()
                    self.observe_activity(pressed)
                    if not self.background_allowed:
                        break
                value = self.read_signal(pos)
                if value is not None:
                    readings[pos] = value
                    # Give the normal device loop time between raw HID requests.
                    time.sleep(.002)
            return position, pressed, readings
        finally:
            self._use_cached_matrix = False

    def enter_bootloader(self):
        # The bootloader jump disconnects USB before a reply can be sent.
        if self.handle.write(b'\0' + b'\x55\xaa\x12'.ljust(32, b'\0')) != 33:
            raise ProtocolError('Bootloader command was not completely sent; it was not retried.')

    def erase_eeprom(self):
        self.exchange(0x18, timeout=15000)
