# SPDX-License-Identifier: GPL-2.0-or-later
"""SLP1 visual sleep policy. No storage-mode transitions or speculative retries."""
import struct
import zlib


class UnsupportedSleepMode(RuntimeError):
    pass


def encode(enabled, minutes):
    if type(enabled) is not bool or type(minutes) is not int or not 5 <= minutes <= 120:
        raise ValueError('Choose a sleep timeout from 5 to 120 minutes.')
    raw = struct.pack('<BBH4s4x', 1, enabled, minutes, b'SLP1')
    return raw + struct.pack('<I', zlib.crc32(raw))


def decode(raw):
    raw = bytes(raw)
    if len(raw) != 16 or raw[1] > 1:
        raise ValueError('Invalid sleep settings.')
    values = dict(enabled=bool(raw[1]), minutes=struct.unpack_from('<H', raw, 2)[0])
    if encode(**values) != raw:
        raise ValueError('Unsupported sleep settings or invalid CRC.')
    return values


class SleepModeClient:
    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.token = 0
        self.uncertain = False

    def request(self, op, payload=b'', token=0):
        if self.uncertain:
            raise RuntimeError('Sleep transport uncertain; reconnect before editing. No update was retried.')
        q = bytes((253, 231, op, 1, token)) + bytes(payload)
        if len(q) > 32:
            raise ValueError('Sleep packet too large.')
        try:
            if self.keyboard.dev.write(b'\0' + q.ljust(32, b'\0')) != 33:
                raise RuntimeError('Short HID write.')
            r = bytes(self.keyboard.dev.read(32, timeout_ms=1000))
            if op == 0 and (len(r) != 32 or r[:5] != bytes((253, 231, 170, 1, 0))):
                raise UnsupportedSleepMode('Sleep Mode needs the matching Sleep Main firmware.')
            if len(r) != 32 or r[:2] != b'\xfd\xe7' or r[3:6] != bytes((1, op, token)):
                raise RuntimeError('Mismatched Sleep response.')
            if r[2] != 170:
                raise ValueError({1: 'Unsupported sleep command.', 2: 'Keyboard locked, busy, or matching AUX unavailable.',
                                  3: 'Sleep settings changed; reopen the tab.', 4: 'Invalid sleep settings.',
                                  5: 'Main settings storage error.'}.get(r[6], 'Sleep update rejected.'))
            return r
        except (UnsupportedSleepMode, ValueError):
            raise
        except (OSError, TypeError, RuntimeError):
            self.uncertain = True
            raise

    def capabilities(self):
        r = self.request(0)
        if r[6:13] != b'SLP1' + bytes((16, 5, 120)) or r[15] != 1:
            raise UnsupportedSleepMode('Unknown Sleep capabilities.')
        return dict(aux_supported=bool(r[13]), aux_error=r[14])

    def read(self):
        r = self.request(1)
        return decode(r[8:24]), struct.unpack_from('<I', r, 24)[0]

    def apply(self, revision, **values):
        raw = encode(**values)
        self.token = self.token % 255 + 1
        ack = self.request(2, struct.pack('<I', revision) + raw, self.token)
        actual, version = self.read()
        if version != (revision + 1) & 0xffffffff or encode(**actual) != raw or struct.unpack_from('<I', ack, 16)[0] != version:
            self.uncertain = True
            raise RuntimeError('Sleep acknowledgement/readback mismatch; no retry.')
        return self.status()

    def status(self):
        r = self.request(3)
        return dict(wanted_sleep=bool(r[6]), actual=r[7], aux_supported=bool(r[8]), command_pending=r[9],
                    aux_error=r[10], attempts=r[11], idle_ms=struct.unpack_from('<I', r, 12)[0],
                    revision=struct.unpack_from('<I', r, 16)[0], save_pending=bool(r[20]),
                    save_error=struct.unpack_from('<I', r, 24)[0])
