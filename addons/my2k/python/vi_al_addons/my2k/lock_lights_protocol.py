# SPDX-License-Identifier: GPL-2.0-or-later
"""MY-2K Lock Lights v1: bounded transactions, durable ACK and exact readback."""
import struct
import time
import zlib

CONFIG_BYTES = 76
MAX_RULES = 8
TRIGGERS = ('None', 'Caps Lock', 'Num Lock', 'Scroll Lock', 'Active layer')
EFFECTS = ('Solid color', 'Blink', 'Breathing', 'Pulse', 'Rainbow cycle')


class UnsupportedLockLights(RuntimeError):
    pass


def encode_rules(rules, fallback_enabled=False, fallback=(0, 0, 0)):
    if len(rules) > MAX_RULES:
        raise ValueError('At most eight LED Square rules are supported.')
    raw = bytearray(CONFIG_BYTES)
    raw[:3] = bytes((1, len(rules), int(bool(fallback_enabled))))
    if len(fallback) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in fallback):
        raise ValueError('Fallback must contain three RGB bytes.')
    raw[4:7] = bytes(fallback)
    for i, rule in enumerate(rules):
        trigger, layer, effect, speed = (rule[k] for k in ('trigger', 'layer', 'effect', 'speed'))
        color = rule['color']
        if (any(type(n) is not int for n in (trigger, layer, effect, speed)) or
                not 0 <= trigger < len(TRIGGERS) or not 0 <= layer < 4 or
                (trigger != 4 and layer != 0) or not 0 <= effect < len(EFFECTS) or not 0 <= speed <= 15 or
                len(color) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in color)):
            raise ValueError('Invalid trigger, layer, effect, speed or RGB color.')
        raw[8+i*8:16+i*8] = bytes((trigger, int(bool(rule['enabled'])), layer, effect, speed, *color))
    struct.pack_into('<I', raw, 72, zlib.crc32(raw[:72]))
    return bytes(raw)


def decode_rules(raw):
    raw = bytes(raw)
    if len(raw) != CONFIG_BYTES or raw[0] != 1 or raw[1] > MAX_RULES or raw[2] > 1 or struct.unpack_from('<I',raw,72)[0] != zlib.crc32(raw[:72]):
        raise ValueError('Invalid LED Square configuration or CRC.')
    rules = []
    for i in range(raw[1]):
        trigger, enabled, layer, effect, speed, r, g, b = raw[8+i*8:16+i*8]
        if enabled > 1:
            raise ValueError('Invalid rule enable flag.')
        rules.append(dict(trigger=trigger, enabled=bool(enabled), layer=layer, effect=effect, speed=speed, color=(r,g,b)))
    values = dict(rules=rules, fallback_enabled=bool(raw[2]), fallback=tuple(raw[4:7]))
    if encode_rules(**values) != raw:
        raise ValueError('Noncanonical LED Square configuration.')
    return values


class LockLightsClient:
    def __init__(self, keyboard, clock=time.monotonic, sleep=time.sleep):
        self.keyboard, self.clock, self.sleep = keyboard, clock, sleep
        self.uncertain = False
        self.token = 0

    def request(self, operation, payload=b'', token=0):
        if self.uncertain:
            raise RuntimeError('LED Square transaction uncertain. Reload before another attempt; nothing was retried.')
        packet = bytes((253,233,operation,1,token)) + bytes(payload)
        if len(packet) > 32:
            raise ValueError('Lock Lights report exceeds 32 bytes.')
        try:
            if self.keyboard.dev.write(b'\0'+packet.ljust(32,b'\0')) != 33:
                raise RuntimeError('Short Lock Lights HID write.')
            reply = bytes(self.keyboard.dev.read(32, timeout_ms=5000))
            if operation == 0 and len(reply) == 32 and (reply[0] == 255 or reply[:3] == bytes((253,233,85)) and reply[3] != 1):
                raise UnsupportedLockLights('LED Square rules require Release 1 Lock Lights Main firmware. Fixed indicators remain available.')
            if len(reply) != 32 or reply[:2] != bytes((253,233)) or reply[3:6] != bytes((1,operation,token)):
                raise RuntimeError('Missing or mismatched Lock Lights response.')
            if reply[2] != 170:
                raise ValueError({1:'Unsupported protocol version or operation.',2:'Keyboard locked or storage mode active.',3:'Invalid, missing or out-of-order configuration chunk.',4:'Another transaction is active; reload after completion.',5:'Keyboard configuration changed. Reload before saving.',6:'Invalid LED Square configuration or CRC.',7:'Settings flash save/verification failed.',8:'LED Square journal is full. Existing rules were preserved; no erase was attempted.'}.get(reply[6], 'Lock Lights request rejected.'))
            return reply
        except (UnsupportedLockLights, ValueError):
            raise
        except (OSError, RuntimeError, TypeError) as error:
            self.uncertain = True
            raise RuntimeError('Lock Lights transport failed; no request was repeated.') from error

    def capabilities(self):
        r = self.request(0)
        if r[6:10] != b'LKS1' or r[10:14] != bytes((76,8,5,4)) or r[15] != 1:
            raise UnsupportedLockLights('Unknown Lock Lights capability schema.')
        return dict(legacy=bool(r[14]), revision=struct.unpack_from('<I',r,16)[0], remaining=struct.unpack_from('<H',r,20)[0], error=bool(r[22]))

    def read(self):
        data = bytearray()
        for at in range(0,CONFIG_BYTES,24):
            n = min(24, CONFIG_BYTES-at)
            r = self.request(1, bytes((at,n)))
            if r[6:8] != bytes((at,n)):
                raise RuntimeError('Invalid LED Square readback offset/length.')
            data.extend(r[8:8+n])
        return decode_rules(data)

    def status(self):
        r = self.request(5)
        return dict(state=r[6], error=r[7], pending=bool(r[8]), flash_error=bool(r[9]), revision=struct.unpack_from('<I',r,10)[0], crc=r[14:18], commits=struct.unpack_from('<I',r,18)[0], legacy=bool(r[22]))

    def apply(self, revision, **values):
        raw = encode_rules(**values)  # Validate before any write operation.
        self.token = self.token % 255 + 1
        self.request(2, struct.pack('<I',revision), self.token)
        for at in range(0,CONFIG_BYTES,24):
            chunk = raw[at:at+24]
            self.request(3, bytes((at,len(chunk)))+chunk, self.token)
        self.request(4, token=self.token)
        deadline = self.clock()+12
        while self.clock() < deadline:
            status = self.status()
            if status['state'] == 3 or status['flash_error']:
                raise RuntimeError('LED Square persistent save failed; active settings were not replaced.')
            if status['state'] == 2 and not status['pending']:
                if status['revision'] != (revision+1)&0xffffffff or status['crc'] != raw[72:] or encode_rules(**self.read()) != raw:
                    raise RuntimeError('LED Square acknowledgement/readback mismatch.')
                return status
            self.sleep(.02)
        self.uncertain = True
        raise RuntimeError('LED Square save still pending. Stop typing briefly, then Reload; no transaction was retried.')

    def diagnostics(self):
        r = self.request(6)
        return dict(selected=None if r[6]==255 else r[6], legacy=bool(r[7]), locks=r[8], layers=struct.unpack_from('<I',r,9)[0], output=tuple(r[13:16]), frames=struct.unpack_from('<I',r,16)[0], selection_changes=struct.unpack_from('<I',r,20)[0], logical_led=r[24], driver=r[25], pending=bool(r[26]), flash_error=bool(r[27]))
