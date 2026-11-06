# SPDX-License-Identifier: GPL-2.0-or-later
"""LKS2: immediate acknowledged/read-back preview, separate durable status."""
import struct
import zlib
from vi_al_addons.my2k.lock_lights_protocol import UnsupportedLockLights

CONFIG_BYTES = 128
EFFECTS = ('Solid color', 'Blink', 'Breathing', 'Pulse', 'Rainbow cycle')
TRIGGERS = ('None', 'Caps Lock', 'Num Lock', 'Scroll Lock', 'Layer 1', 'Layer 2', 'Layer 3')


def _rgb(color):
    if len(color) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in color):
        raise ValueError('Color must contain three RGB bytes.')
    return tuple(color)


def defaults():
    return dict(rules=[], fallback_enabled=False, fallback=(0, 0, 0),
                fixed=[dict(enabled=True, color=(255, 255, 255), effect=0, speed=8) for _ in range(5)])


def encode_rules(rules, fallback_enabled=False, fallback=(0, 0, 0), fixed=None):
    if len(rules) > 8:
        raise ValueError('At most eight LED Square rules are supported.')
    if fixed is None:
        fixed = defaults()['fixed']
    if len(fixed) != 5:
        raise ValueError('Exactly five fixed indicators are required.')
    raw = bytearray(CONFIG_BYTES)
    raw[:3] = bytes((2, len(rules), int(bool(fallback_enabled))))
    raw[4:7] = bytes(_rgb(fallback))
    for i, rule in enumerate(rules):
        trigger, layer, effect, speed = (rule[k] for k in ('trigger', 'layer', 'effect', 'speed'))
        if (any(type(n) is not int for n in (trigger, layer, effect, speed)) or
                not 0 <= trigger <= 4 or (not 1 <= layer <= 3 if trigger == 4 else layer != 0) or
                not 0 <= effect < 5 or not 0 <= speed <= 15):
            raise ValueError('Invalid rule; LED Square supports layers 1 through 3.')
        raw[8+i*8:16+i*8] = bytes((trigger, bool(rule['enabled']), layer, effect, speed, *_rgb(rule['color'])))
    for i, item in enumerate(fixed):
        effect, speed = item['effect'], item['speed']
        if type(effect) is not int or not 0 <= effect < 5 or type(speed) is not int or not 0 <= speed <= 15:
            raise ValueError('Invalid indicator effect or speed.')
        raw[72+i*8:80+i*8] = bytes((bool(item['enabled']), effect, speed, *_rgb(item['color']), 0, 0))
    struct.pack_into('<I', raw, 124, zlib.crc32(raw[:124]))
    return bytes(raw)


def decode_rules(raw):
    raw = bytes(raw)
    if len(raw) != 128 or raw[0] != 2 or raw[1] > 8 or raw[2] > 1 or raw[3] or struct.unpack_from('<I', raw, 124)[0] != zlib.crc32(raw[:124]):
        raise ValueError('Invalid Lock Lights configuration or CRC.')
    result = dict(rules=[], fallback_enabled=bool(raw[2]), fallback=tuple(raw[4:7]), fixed=[])
    for i in range(raw[1]):
        trigger, enabled, layer, effect, speed, r, g, b = raw[8+i*8:16+i*8]
        if enabled > 1:
            raise ValueError('Invalid enable flag.')
        result['rules'].append(dict(trigger=trigger, enabled=bool(enabled), layer=layer,
                                    effect=effect, speed=speed, color=(r, g, b)))
    for i in range(5):
        enabled, effect, speed, r, g, b, _, _ = raw[72+i*8:80+i*8]
        if enabled > 1:
            raise ValueError('Invalid enable flag.')
        result['fixed'].append(dict(enabled=bool(enabled), effect=effect, speed=speed, color=(r, g, b)))
    if encode_rules(**result) != raw:
        raise ValueError('Noncanonical Lock Lights configuration.')
    return result


class LockLightsClient:
    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.token = 0
        self.uncertain = False

    def request(self, operation, payload=b'', token=0):
        if self.uncertain:
            raise RuntimeError('Transport uncertain. Reload before further edits; no request was retried.')
        packet = bytes((253, 233, operation, 2, token)) + bytes(payload)
        if len(packet) > 32:
            raise ValueError('Report exceeds 32 bytes.')
        try:
            if self.keyboard.dev.write(b'\0' + packet.ljust(32, b'\0')) != 33:
                raise RuntimeError('Short HID write.')
            reply = bytes(self.keyboard.dev.read(32, timeout_ms=1000))
            if operation == 0 and (len(reply) != 32 or reply[:2] != b'\xfd\xe9' or reply[3] != 2):
                raise UnsupportedLockLights('Live Lock Lights requires the Release 1 EEPROM32 Main firmware. AUX needs no update.')
            if len(reply) != 32 or reply[:2] != b'\xfd\xe9' or reply[3:6] != bytes((2, operation, token)):
                raise RuntimeError('Missing or mismatched Lock Lights response.')
            if reply[2] != 170:
                raise ValueError({1:'Unsupported version/operation.', 2:'Keyboard locked or storage mode active.',
                    3:'Invalid or incomplete upload.', 4:'Another upload is active.',
                    5:'Configuration changed. Reload before editing.', 6:'Invalid configuration or CRC.',
                    7:'Main settings storage reports a failure.'}.get(reply[6], 'Request rejected.'))
            return reply
        except (UnsupportedLockLights, ValueError):
            raise
        except (OSError, RuntimeError, TypeError) as error:
            self.uncertain = True
            raise RuntimeError('Lock Lights transport failed; no mutation was retried.') from error

    def capabilities(self):
        r = self.request(0)
        if r[6:16] != b'LKS2' + bytes((128, 8, 5, 14, 5, 1)) or r[23] != 1:
            raise UnsupportedLockLights('Unknown live Lock Lights capabilities.')
        return dict(revision=struct.unpack_from('<I', r, 16)[0], error=bool(r[22]))

    def read(self):
        data = bytearray()
        for at in range(0, 128, 24):
            n = min(24, 128-at)
            r = self.request(1, bytes((at, n)))
            if r[6:8] != bytes((at, n)):
                raise RuntimeError('Readback offset/length mismatch.')
            data.extend(r[8:8+n])
        return decode_rules(data)

    def apply_live(self, revision, **values):
        raw = encode_rules(**values)
        self.token = self.token % 255 + 1
        self.request(2, struct.pack('<I', revision), self.token)
        for at in range(0, 128, 24):
            chunk = raw[at:at+24]
            self.request(3, bytes((at, len(chunk)))+chunk, self.token)
        self.request(4, token=self.token)
        status = self.status()
        if status['revision'] != (revision+1) & 0xffffffff or status['crc'] != raw[124:] or encode_rules(**self.read()) != raw:
            self.uncertain = True
            raise RuntimeError('Live acknowledgement/readback mismatch. Reload before editing.')
        return status

    def status(self):
        r = self.request(5)
        return dict(state=r[6], error=r[7], pending=bool(r[8]), flash_error=bool(r[9]),
                    revision=struct.unpack_from('<I', r, 10)[0], crc=r[14:18],
                    commits=struct.unpack_from('<I', r, 18)[0])
