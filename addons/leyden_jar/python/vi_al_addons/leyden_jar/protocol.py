# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Leyden Jar 0.9.1+ protocol, using the selected Vial HID handle.

Packet offsets follow LeydenJarProtocol.cpp and board-local util_protocol.c.
Discovery and file logging are intentionally absent. Mutations are never retried.
"""
from dataclasses import dataclass
from collections import deque
import json
from pathlib import Path
import struct
import time

PROFILES = json.loads(Path(__file__).with_name('profiles.json').read_text())

MAGIC = 0x21C0
GET, SET = 2, 3
VERSION, DETAILS, ENABLE, DETECT, THRESHOLD, LEVELS = range(0x81, 0x87)
SCAN_LOGICAL, SCAN_PHYSICAL, BOOT, REBOOT, ERASE = range(0x87, 0x8C)
LOGICAL_ROW, PHYSICAL_VALUES, MAPPING, REFERENCE, BINS, SIDE = range(0x8C, 0x92)


class ProtocolError(RuntimeError):
    pass


def supported(keyboard):
    uid = getattr(keyboard, 'keyboard_id', None)
    if isinstance(uid, int) and 0 <= uid < 1 << 64:
        uid = uid.to_bytes(8, 'little')
    if not isinstance(uid, bytes):
        return False
    return any(uid.hex() == p['uid'] and (keyboard.rows, keyboard.cols) == (p['rows'], p['cols'])
               for p in PROFILES)


@dataclass(frozen=True)
class Details:
    rows: int
    cols: int
    physical_rows: int
    physical_cols: int
    technology: int
    bins: int

    @classmethod
    def decode(cls, data):
        if len(data) < 6:
            raise ProtocolError('Incomplete Leyden Jar controller details.')
        value = cls(*data[:6])
        if (not 1 <= value.rows <= 8 or not 1 <= value.cols <= 18
                or value.physical_rows != 8 or value.physical_cols not in (16, 18)
                or value.technology not in (0, 1) or not 1 <= value.bins <= 16):
            raise ProtocolError('Unsupported Leyden Jar matrix, switch technology or bin count.')
        return value


class Client:
    def __init__(self, keyboard):
        if not supported(keyboard):
            raise ProtocolError('The selected keyboard has no verified Leyden Jar identity.')
        self.keyboard, self.handle = keyboard, keyboard.dev
        self.thresholds, self.references, self.bin_map = [], [], {}
        self.minimum, self.maximum = {}, {}
        self.stable_low, self.stable_high, self.history = {}, {}, {}
        self.details = None

    def exchange(self, operation, command, payload=b'', timeout=2500, reply=True):
        payload = bytes(payload)
        if operation not in (GET, SET) or not 0x81 <= command <= 0x91 or len(payload) > 28:
            raise ProtocolError('Invalid native Leyden Jar command or payload.')
        request = (struct.pack('<BBH', operation, command, MAGIC) + payload).ljust(32, b'\0')
        if self.handle.write(b'\0' + request) != 33:
            raise ProtocolError('Incomplete HID write; command was not retried.')
        if not reply:
            return None  # Boot/reset intentionally disconnect without an acknowledgement.
        deadline = time.monotonic() + timeout / 1000
        for _ in range(8):
            remaining = max(1, round((deadline - time.monotonic()) * 1000))
            raw = bytes(self.handle.read(32, timeout_ms=remaining))
            if not raw:
                break
            if len(raw) == 32 and raw[1:4] == request[1:4]:
                if raw[0] == 0xFF:
                    raise ProtocolError('Firmware rejected command 0x%02X.' % command)
                if raw[0] == operation:
                    return raw[4:]
            if time.monotonic() >= deadline:
                break
        raise ProtocolError('No matching complete Leyden Jar reply; command was not retried.')

    def connect(self):
        raw = self.exchange(GET, VERSION)
        self.version = (raw[0], raw[1], struct.unpack_from('<H', raw, 2)[0])
        if self.version < (0, 9, 1) or self.version >= (2, 0, 0):
            raise ProtocolError('Requires native Leyden Jar protocol 0.9.1 or 1.x.')
        self.details = Details.decode(self.exchange(GET, DETAILS))
        if (self.details.rows, self.details.cols) != (self.keyboard.rows, self.keyboard.cols):
            raise ProtocolError('Firmware matrix differs from its Vial definition; refusing mismapped diagnostics.')
        raw = self.exchange(GET, MAPPING)
        self.mapping_type = raw[0]
        ncols, nrows = self.details.physical_cols, self.details.physical_rows
        self.col_map = tuple(raw[1:1+ncols])
        self.row_map = tuple(raw[1+ncols:1+ncols+nrows])
        if self.mapping_type not in (0, 1, 2):
            raise ProtocolError('Unknown native matrix mapping convention.')
        for mapping, used, limit in ((self.row_map, self.details.rows, nrows),
                                      (self.col_map, self.details.cols, ncols)):
            values = [v for v in mapping[:used] if v != 255]
            if any(v >= limit for v in values) or len(set(values)) != len(values):
                raise ProtocolError('Invalid or aliased logical-to-controller mapping.')
        self.enabled = self.exchange(GET, ENABLE)[0] != 0
        self.refresh_bins()
        self.side = None
        if self.version >= (1, 0, 0):
            side = self.exchange(GET, SIDE)[0]
            if side not in (0, 1):
                raise ProtocolError('Invalid split-controller side.')
            self.side = 'left' if side else 'right'
        return self

    def refresh_bins(self):
        thresholds, references, bin_map = [], [], {}
        for number in range(self.details.bins):
            thresholds.append(self.read_threshold(number))
            value = struct.unpack_from('<H', self.exchange(GET, REFERENCE, struct.pack('<H', number)), 2)[0]
            if value > 1023:
                raise ProtocolError('DAC reference exceeds the native ten-bit range.')
            references.append(value)
        for col in range(self.details.physical_cols):
            raw = self.exchange(GET, BINS, struct.pack('<H', col))
            if struct.unpack_from('<H', raw)[0] != col:
                raise ProtocolError('Column-bin reply belongs to another column.')
            for row, number in enumerate(raw[2:2+self.details.physical_rows]):
                if number != 255 and number >= self.details.bins:
                    raise ProtocolError('Invalid calibration bin assignment.')
                bin_map[row, col] = number
        self.thresholds, self.references, self.bin_map = thresholds, references, bin_map

    def read_threshold(self, number):
        if not 0 <= number < self.details.bins:
            raise ProtocolError('Calibration bin is out of range.')
        raw = self.exchange(GET, THRESHOLD, struct.pack('<H', number))
        if struct.unpack_from('<H', raw)[0] != number:
            raise ProtocolError('Threshold reply belongs to another bin.')
        value = struct.unpack_from('<H', raw, 2)[0]
        if value > 1023:
            raise ProtocolError('Threshold exceeds the native ten-bit DAC range.')
        return value

    def set_threshold(self, number, value):
        if not 0 <= number < self.details.bins or not 0 <= value <= 1023:
            raise ProtocolError('Threshold or calibration bin is out of range.')
        self.exchange(SET, THRESHOLD, struct.pack('<HB', value, number))
        actual = self.read_threshold(number)
        if actual != value:
            raise ProtocolError('Threshold readback differs from the requested value.')
        self.thresholds[number] = actual
        self.reset_extrema()
        return actual

    def set_enabled(self, enabled):
        self.exchange(SET, ENABLE, bytes((bool(enabled),)))
        self.enabled = self.exchange(GET, ENABLE)[0] != 0
        if self.enabled != bool(enabled):
            raise ProtocolError('Keyboard enable readback differs from the requested state.')
        return self.enabled

    def physical_position(self, position):
        row, col = position
        if not 0 <= row < self.details.rows or not 0 <= col < self.details.cols:
            return None
        mapped = self.row_map[row], self.col_map[col]
        return None if 255 in mapped else mapped

    def logical_position(self, position):
        row, col = position
        rows, cols = self.row_map[:self.details.rows], self.col_map[:self.details.cols]
        return (rows.index(row), cols.index(col)) if row in rows and col in cols else None

    def keypresses(self):
        self.exchange(SET, SCAN_LOGICAL)
        logical = set()
        for row in range(self.details.rows):
            raw = self.exchange(GET, LOGICAL_ROW, struct.pack('<H', row))
            if struct.unpack_from('<H', raw)[0] != row:
                raise ProtocolError('Matrix row reply belongs to another row.')
            bits = struct.unpack_from('<I', raw, 4)[0]
            if bits >> self.details.cols:
                raise ProtocolError('Matrix reply contains columns outside the declared matrix.')
            logical.update((row, col) for col in range(self.details.cols) if bits & (1 << col))
        self.exchange(SET, SCAN_PHYSICAL)
        raw = self.exchange(GET, PHYSICAL_VALUES)
        physical = set()
        for col, bits in enumerate(raw[:self.details.physical_cols]):
            for row in range(self.details.physical_rows):
                active = self.bin_map[row, col] != 255
                pressed = bool(bits & (1 << row)) != bool(self.details.technology)
                if active and pressed:
                    physical.add((row, col))
        return logical, physical

    def levels(self):
        # The native sweep changes the DAC and scans 350..499. It is explicit,
        # page-scoped and bounded, never started by detection or page creation.
        self.exchange(SET, DETECT, timeout=20000)
        values = {}
        for col in range(self.details.physical_cols):
            raw = self.exchange(GET, LEVELS, struct.pack('<H', col))
            if struct.unpack_from('<H', raw)[0] != col:
                raise ProtocolError('Level reply belongs to another column.')
            for row, value in enumerate(struct.unpack_from('<8H', raw, 2)):
                if value > 1023:
                    raise ProtocolError('Level exceeds the native DAC range.')
                position = row, col
                values[position] = value
                if self.bin_map[position] != 255:
                    self.minimum[position] = min(self.minimum.get(position, value), value)
                    self.maximum[position] = max(self.maximum.get(position, value), value)
                    recent = self.history.setdefault(position, deque(maxlen=3))
                    recent.append(value)
                    if len(recent) == 3:
                        threshold = self.thresholds[self.bin_map[position]]
                        median = sorted(recent)[1]
                        if max(recent) < threshold:
                            self.stable_low[position] = min(self.stable_low.get(position, median), median)
                        elif min(recent) >= threshold:
                            self.stable_high[position] = max(self.stable_high.get(position, median), median)
        return values

    def reset_extrema(self):
        self.minimum.clear()
        self.maximum.clear()
        self.stable_low.clear()
        self.stable_high.clear()
        self.history.clear()

    def enter_bootloader(self):
        self.exchange(SET, BOOT, reply=False)

    def reboot(self):
        self.exchange(SET, REBOOT, reply=False)

    def erase_eeprom(self):
        self.exchange(SET, ERASE, reply=False)
