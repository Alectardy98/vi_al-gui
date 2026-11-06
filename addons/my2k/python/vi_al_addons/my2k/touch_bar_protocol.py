# SPDX-License-Identifier: GPL-2.0-or-later
"""TCH2: bounded Main-only touch settings, live readback and durable status."""
import struct
import zlib


class UnsupportedTouchBar(RuntimeError):
    pass


def valid_key(code):
    if type(code) is not int or not 0 <= code <= 0x1fff:
        return False
    return code == 0 or 4 <= (code & 255) <= 0xc2 or 0xcd <= (code & 255) <= 0xe7


def defaults():
    return dict(mode=0, sensitivity=50, left=0xaa, right=0xa9, tap=0xa8, tap_jitter=50)


def encode(mode, sensitivity, left, right, tap, tap_jitter=50):
    if type(mode) is not int or mode not in (0, 1):
        raise ValueError('Choose Hold or Slider mode.')
    if type(sensitivity) is not int or not 1 <= sensitivity <= 100:
        raise ValueError('Sensitivity must be between 1 and 100.')
    if type(tap_jitter) is not int or not 0 <= tap_jitter <= 100:
        raise ValueError('Tap Jitter Threshold must be between 0 and 100.')
    if not all(valid_key(k) for k in (left, right, tap)):
        raise ValueError('Choose a keyboard, modifier, media or mouse key, or None. Layer, macro, tap-hold and firmware actions are not supported.')
    raw = struct.pack('<BBBB3H2x', 2, mode, sensitivity, tap_jitter, left, right, tap)
    return raw + struct.pack('<I', zlib.crc32(raw))


def decode(raw):
    raw = bytes(raw)
    if len(raw) != 16 or raw[0] != 2:
        raise ValueError('Unknown touch settings format.')
    result = dict(mode=raw[1], sensitivity=raw[2], tap_jitter=raw[3], **dict(zip(('left', 'right', 'tap'), struct.unpack_from('<3H', raw, 4))))
    if encode(**result) != raw:
        raise ValueError('Invalid touch settings or CRC.')
    return result


class TouchBarClient:
    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.token = 0
        self.uncertain = False

    def request(self, op, payload=b'', token=0):
        if self.uncertain:
            raise RuntimeError('Reload before editing; an uncertain transfer is never retried.')
        packet = bytes((253, 235, op, 2, token)) + bytes(payload)
        if len(packet) > 32:
            raise ValueError('Touch report exceeds 32 bytes.')
        try:
            if self.keyboard.dev.write(b'\0' + packet.ljust(32, b'\0')) != 33:
                raise RuntimeError('Short HID write.')
            r = bytes(self.keyboard.dev.read(32, timeout_ms=1000))
            if op == 0 and (len(r) != 32 or r[:2] != b'\xfd\xeb' or r[3] != 2 or r[2] != 170):
                raise UnsupportedTouchBar('Tap Jitter Threshold requires the matching Release 1 Tap Main firmware and GUI1.6. Keep AUX unchanged.')
            if len(r) != 32 or r[:2] != b'\xfd\xeb' or r[3:6] != bytes((2, op, token)):
                raise RuntimeError('Mismatched touch response.')
            if r[2] != 170:
                raise ValueError({1: 'Unsupported operation/version.', 2: 'Keyboard locked or storage mode active.',
                                  3: 'Settings changed; reload before editing.', 4: 'Invalid touch settings or CRC.',
                                  5: 'Main settings storage error.'}.get(r[6], 'Touch request rejected.'))
            return r
        except (UnsupportedTouchBar, ValueError):
            raise
        except (OSError, RuntimeError, TypeError) as error:
            self.uncertain = True
            raise RuntimeError('Touch transport failed; no settings update was retried.') from error

    def capabilities(self):
        r = self.request(0)
        if r[6:16] != b'TCH2' + bytes((16, 3, 1, 100, 50, 1)):
            raise UnsupportedTouchBar('Unknown touch capabilities.')
        if r[24:28] != bytes((0, 100, 50, 1)):
            raise UnsupportedTouchBar('Unknown tap-jitter capabilities.')
        return dict(revision=struct.unpack_from('<I', r, 16)[0], error=struct.unpack_from('<I', r, 20)[0], hold_jitter=bool(r[28] & 1))

    def read(self):
        r = self.request(1)
        return decode(r[8:24]), struct.unpack_from('<I', r, 24)[0]

    def apply_live(self, revision, **values):
        raw = encode(**values)
        self.token = self.token % 255 + 1
        r = self.request(2, struct.pack('<I', revision) + raw, self.token)
        actual, version = self.read()
        if version != (revision + 1) & 0xffffffff or encode(**actual) != raw or r[12:16] != raw[12:]:
            self.uncertain = True
            raise RuntimeError('Touch acknowledgement/readback mismatch; reload before editing.')
        return self.status()

    def status(self):
        r = self.request(3)
        return dict(revision=struct.unpack_from('<I', r, 8)[0], crc=r[12:16], pending=bool(r[16]), error=struct.unpack_from('<I', r, 20)[0])

    def diagnostics(self):
        r = self.request(4)
        return dict(mode=r[6], queued=r[7], raw=list(r[8:12]), samples=struct.unpack_from('<I', r, 12)[0],
                    pulses=struct.unpack_from('<I', r, 16)[0], dropped=struct.unpack_from('<I', r, 20)[0],
                    last_sample_ms=struct.unpack_from('<I', r, 24)[0], contact=bool(r[28]), enabled=bool(r[29]),
                    estimated_position=struct.unpack_from('<H', r, 30)[0])

    def tap_diagnostics(self):
        r = self.request(5)
        return dict(phase=r[6], tap_jitter=r[7], taps=struct.unpack_from('<I', r, 8)[0],
                    swipes=struct.unpack_from('<I', r, 12)[0], ambiguous=struct.unpack_from('<I', r, 16)[0],
                    candidate_at_ms=struct.unpack_from('<I', r, 20)[0], radius=struct.unpack_from('<H', r, 24)[0])
