# SPDX-License-Identifier: GPL-2.0-or-later
"""GME1 mapping extension. No probe/start on editing; bounded atomic profile saves."""
import struct


def valid_key(code):
    return type(code) is int and (code == 0 or 4 <= code <= 0x73 or 0x87 <= code <= 0xa4 or 0xe0 <= code <= 0xe7)


def encode(keys):
    if len(keys) != 8 or not all(valid_key(k) for k in keys):
        raise ValueError('Choose eight ordinary keyboard keys, modifiers, or None. Macros, layers and firmware actions are not game bindings.')
    return struct.pack('<8H', *keys)


class GamingClient:
    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.uncertain = False

    def request(self, op, game=0, payload=b''):
        if self.uncertain:
            raise RuntimeError('Gaming transport uncertain. Reopen the tab before editing; no save was retried.')
        q = bytes((253, 230, op, 1, game)) + bytes(payload)
        if len(q) > 32:
            raise ValueError('Gaming packet exceeds 32 bytes.')
        try:
            if self.keyboard.dev.write(b'\0' + q.ljust(32, b'\0')) != 33:
                raise RuntimeError('Short Gaming HID write.')
            r = bytes(self.keyboard.dev.read(32, timeout_ms=1000))
            if len(r) != 32 or r[:2] != b'\xfd\xe6' or r[3:5] != bytes((1, op)):
                raise RuntimeError('Missing or mismatched Gaming reply.')
            if r[2] != 170:
                raise ValueError({2: 'Exit games/storage mode and unlock Vial before changing controls.', 3: 'Settings changed. Reopen Gaming to reload.', 4: 'Unsupported game control key.', 5: 'Main settings persistence error.'}.get(r[6], 'Gaming requires the matching Release 1 Main firmware.'))
            if op in (5, 6) and r[5] != game:
                raise RuntimeError('Wrong game profile in reply.')
            return r
        except ValueError:
            raise
        except (OSError, RuntimeError, TypeError):
            self.uncertain = True
            raise

    def capabilities(self):
        r = self.request(0)
        if r[8:12] != b'GME1' or not r[28] & 8:
            raise ValueError('Game control mapping needs the new Gaming Main firmware. No settings changed.')
        return dict(ready=bool(r[5]), active=r[6], error=r[7], high_performance=bool(r[27]), doom=bool(r[28] & 4), gbc=bool(r[28] & 16))

    def read(self, game):
        if game not in (1, 2, 3):
            raise ValueError('Unknown game.')
        r = self.request(5, game)
        keys = struct.unpack_from('<8H', r, 8)
        encode(keys)
        return keys, struct.unpack_from('<I', r, 24)[0], dict(pending=bool(r[28]), error=bool(r[29]))

    def apply(self, game, keys, revision):
        raw = encode(keys)
        ack = self.request(6, game, struct.pack('<I', revision) + raw)
        actual, current, status = self.read(game)
        if encode(actual) != raw or current != (revision + 1) & 0xffffffff or struct.unpack_from('<I', ack, 24)[0] != current:
            self.uncertain = True
            raise RuntimeError('Gaming acknowledgement/readback mismatch. No save was retried.')
        return current, status
