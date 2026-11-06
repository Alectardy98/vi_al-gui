# SPDX-License-Identifier: GPL-2.0-or-later
"""Release 1 OLED protocol. No device discovery, retries, or asset-file writes."""
import struct
import time
import zlib


class UnsupportedOled(RuntimeError):
    pass


CONFIG_BYTES = 480


def encode_config(message, label, typing=True, happy=False, clock=False,
                  font_family='DejaVu Sans Mono', font_size=8, bitmap=None):
    try:
        text, corner, family = message.encode('ascii'), label.encode('ascii'), font_family.encode('ascii')
    except UnicodeEncodeError as error:
        raise ValueError('Use ASCII message, label and font-family names.') from error
    if len(text)>59 or len(corner)>10 or len(family)>40 or not 8<=font_size<=38:
        raise ValueError('Maximum59message bytes,10label characters,40font-name bytes; font size8–38.')
    if happy and clock:
        raise ValueError('Choose either Happy or Clock mode, not both.')
    if any(c!=10 and not 32<=c<=126 for c in text) or any(not 32<=c<=126 for c in corner+family):
        raise ValueError('Only printable ASCII and message line breaks are supported.')
    if bitmap is not None and len(bitmap)!=360:
        raise ValueError('The OLED bitmap must contain360page-packed bytes.')
    raw=bytearray(CONFIG_BYTES)
    raw[:4]=bytes((1,int(bool(typing))|(int(bool(happy))<<1)|(4 if bitmap is not None else 0)|(int(bool(clock))<<3),len(text),len(corner)))
    raw[4:4+len(text)]=text;raw[64:64+len(corner)]=corner
    raw[74:76]=bytes((font_size,len(family)));raw[76:76+len(family)]=family
    if bitmap is not None:raw[116:476]=bytes(bitmap)
    struct.pack_into('<I',raw,476,zlib.crc32(raw[:476]))
    return bytes(raw)


def decode_config(raw):
    raw=bytes(raw)
    if len(raw)!=CONFIG_BYTES or raw[0]!=1 or raw[1]&~15 or raw[2]>59 or raw[3]>10 or raw[75]>40 or struct.unpack_from('<I',raw,476)[0]!=zlib.crc32(raw[:476]):
        raise ValueError('Invalid OLED configuration or CRC.')
    values=dict(message=raw[4:4+raw[2]].decode('ascii'),label=raw[64:64+raw[3]].decode('ascii'),typing=bool(raw[1]&1),happy=bool(raw[1]&2),clock=bool(raw[1]&8),font_family=raw[76:76+raw[75]].decode('ascii'),font_size=raw[74],bitmap=raw[116:476] if raw[1]&4 else None)
    if encode_config(**values)!=raw:raise ValueError('OLED configuration is not canonical.')
    return values


class OledClient:
    def __init__(self, keyboard, clock=time.monotonic, sleep=time.sleep):
        self.keyboard, self.clock, self.sleep = keyboard, clock, sleep
        self.uncertain = False

    def request(self, operation, payload=b''):
        if self.uncertain:
            raise RuntimeError('OLED transfer is uncertain. Reconnect in the GUI before retrying; no command was repeated.')
        packet = bytes((253, 232, operation)) + bytes(payload)
        if len(packet) > 32:
            raise ValueError('OLED report exceeds 32 bytes.')
        try:
            if self.keyboard.dev.write(b'\0' + packet.ljust(32, b'\0')) != 33:
                raise RuntimeError('Short OLED HID write.')
            reply = bytes(self.keyboard.dev.read(32, timeout_ms=5000))
            if operation == 0 and (len(reply) == 32 and (reply[0] == 255 or reply[:3] == b'\xfd\xe8\x55')):
                raise UnsupportedOled('This firmware does not support Release 1 OLED configuration.')
            if len(reply) != 32 or reply[:2] != packet[:2] or reply[3:5] != bytes((1, operation)):
                raise RuntimeError('Missing or mismatched OLED response.')
            if reply[2] != 170:
                raise ValueError('OLED request rejected: AUX unavailable, storage mode active, busy, or invalid data.')
            return reply
        except (UnsupportedOled, ValueError):
            raise
        except (OSError, RuntimeError, TypeError) as error:
            self.uncertain = True
            raise RuntimeError('OLED transport failed; no request was retried.') from error

    def capabilities(self):
        r = self.request(0)
        if r[6] & 31 != 31 or r[7:12] != bytes((72, 40, 11, 5, 10)) or struct.unpack_from("<H",r,12)[0] != CONFIG_BYTES:
            raise UnsupportedOled('Unknown OLED geometry or protocol.')
        return dict(peer_ready=bool(r[5]), persistent=bool(r[14]), features=r[6])

    def read(self, refresh=False):
        if refresh:
            self.request(6)
            self.wait_applied()
        data = bytearray()
        while len(data) < CONFIG_BYTES:
            at = len(data)
            r = self.request(1, struct.pack("<H",at))
            n = min(24, CONFIG_BYTES-at)
            if r[5:8] != struct.pack("<HB",at,n):
                raise RuntimeError('Invalid OLED readback offset or length.')
            data.extend(r[8:8+n])
        return decode_config(data)

    def status(self):
        r = self.request(5)
        return dict(state=r[5], peer_ready=bool(r[6]), error=r[7], crc=bytes(r[8:12]),
                    pending_save=bool(r[12]), durable=bool(r[13]), applies=struct.unpack_from('<I', r, 16)[0])

    def wait_applied(self):
        deadline = self.clock()+12
        while self.clock() < deadline:
            s = self.status()
            if s['state'] == 3:
                message = {1:'AUX response timed out; no request was retried.', 3:'Incompatible AUX firmware.', 4:'AUX acknowledgement CRC did not match.', 5:'AUX communication unavailable.', 17:'AUX rejected the configuration transaction.', 18:'The OLED output is unavailable.', 19:'AUX could not save or verify the display files; the active configuration was not replaced.'}.get(s['error'],'AUX update failed (error {}).'.format(s['error']))
                raise RuntimeError(message)
            if s['state'] == 2:
                return s
            self.sleep(.03)
        raise RuntimeError('OLED completion timed out; check diagnostics before retrying.')

    def apply(self, **values):
        raw = encode_config(**values)
        self.request(2, b'\x01')
        for at in range(0, CONFIG_BYTES, 24):
            part = raw[at:at+24]
            self.request(3, struct.pack("<HB",at,len(part)) + part)
        self.request(4)
        status = self.wait_applied()
        if status['crc'] != raw[476:480] or self.read() != values:
            raise RuntimeError('OLED acknowledgement/readback differs from the requested configuration.')
        return status

    def sync_datetime(self, year, month, day, weekday, hour, minute, second):
        self.request(7, struct.pack('<H6B', year, month, day, weekday, hour, minute, second))
        return self.wait_applied()
