# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict EC42 v2.9 client. Adapted from qmk-ec-util's protocol/settings/device.

The caller owns one existing Vial HID connection exclusively for each operation.
Mutation requests are sent once; timeouts never cause an automatic retry.
"""
from dataclasses import dataclass
from enum import IntEnum
import json
from pathlib import Path
import struct
import time
import zlib


class ECError(RuntimeError):
    pass


class Op(IntEnum):
    HELLO = 0x10
    LATCH = 0x11
    PAGE = 0x12
    CELL = 0x13
    STATUS = 0x14
    CONFIG = 0x15
    BACKUP = 0x16
    RESTORE_BEGIN = 0x17
    RESTORE_CHUNK = 0x18
    RESTORE_COMMIT = 0x19
    FIRMWARE = 0x1c
    ACTIVE = 0x1d
    CONTROL = 0x20
    VALIDATE = 0x22
    PROPOSAL = 0x23
    ACTIVATE = 0x24
    SAVE = 0x25
    EVIDENCE = 0x27
    ACTUATION = 0x28
    SET_ACTUATION = 0x29
    SET_RT = 0x2a
    DESCRIPTOR = 0x2b
    GLOBAL_RESET = 0x2c


def u16(data, offset=0):
    try:
        return struct.unpack_from('>H', data, offset)[0]
    except struct.error as e:
        raise ECError('Truncated EC42 integer') from e


def be16(value):
    return struct.pack('>H', value)


@dataclass(frozen=True)
class Profile:
    name: str
    uid: bytes
    rows: int
    cols: int
    magic: int

    @property
    def cells(self):
        return self.rows * self.cols

    @property
    def record_size(self):
        return 17 + 3 * self.cells


PROFILES = (
    Profile('Matrix Astro ME EC Kit', bytes.fromhex('0ec173239f8f8f2c'), 6, 16, 0xa996),
    Profile('Cipulot EC Pro X', bytes.fromhex('4d2d00bcadf8b927'), 5, 15, 0xa975),
    Profile('MM Studio Class0413 EC', bytes.fromhex('45464c4449414702'), 5, 21, 0xa105),
    Profile('Cipulot Virgo EC', bytes.fromhex('564952474f454301'), 6, 18, 0xa66c),
)


def profile_for_uid(uid):
    if isinstance(uid, int):
        if not 0 <= uid < 1 << 64:
            return None
        uid = uid.to_bytes(8, 'little')
    return next((p for p in PROFILES if p.uid == uid), None)


def encode(op, sequence, payload=b'', status=0, response=False):
    op = Op(op)
    if len(payload) > 20 or not 0 <= status <= 4 or (status and not response):
        raise ECError('Invalid EC42 packet parameters')
    return (b'\xcaEC42\x02' + bytes([op]) + be16(sequence) +
            bytes([status, len(payload), int(response)]) + payload).ljust(32, b'\0')


def decode(raw):
    raw = bytes(raw)
    if len(raw) != 32 or raw[:6] != b'\xcaEC42\x02':
        raise ECError('Invalid EC42 report length, magic or version')
    try:
        op = Op(raw[6])
    except ValueError as e:
        raise ECError('Unknown EC42 operation') from e
    status, length, flags = raw[9:12]
    if length > 20 or flags > 1 or status > 4 or (status and not flags) or any(raw[12+length:]):
        raise ECError('Invalid EC42 header/padding')
    return op, u16(raw, 7), status, bool(flags), raw[12:12+length]


@dataclass(frozen=True)
class Record:
    canonical: bytes
    overrides: tuple
    packed: bool


def decode_record(raw, profile):
    raw = bytes(raw)
    n, meta = profile.cells, 9 + 2 * profile.cells
    if len(raw) != profile.record_size or u16(raw, meta) != profile.magic or u16(raw, meta+2) not in (3, 0x42):
        raise ECError('EC record board, size or method mismatch (requires v2.9)')
    native = bytearray(raw)
    for i in list(range(1, 7, 2)) + list(range(9, meta+8, 2)):
        native[i], native[i+1] = native[i+1], native[i]
    expected = u16(raw, meta+4) | u16(raw, meta+6) << 16
    native[meta+4:meta+8] = bytes(4)
    if zlib.crc32(native) != expected:
        raise ECError('EC record CRC mismatch')
    if raw[0] > 1 or not 0 < u16(raw, 3) < u16(raw, 1) < 1023 or not raw[7] or not raw[8]:
        raise ECError('EC record parameters invalid')
    overrides = tuple(raw[meta+8:])
    for i, override in enumerate(overrides):
        v = u16(raw, 9+2*i)
        if (override > 99 or v & 0x1c00 or (v & 0x4000 and not v & 1023) or
                (v & 0x8000 and (not v & 0x4000 or v & 0x2000)) or
                (not v & 0x4000 and v & ~0x2000)):
            raise ECError('EC record cell flags/override invalid')
    return Record(raw[:meta], overrides, u16(raw, meta+2) == 0x42)


def backup_document(raw, profile, serial=''):
    try:
        restorable = decode_record(raw, profile).packed
    except ECError:
        restorable = False
    return dict(format='qmk-ec-backup-1', restorable=restorable, uid=profile.uid.hex(),
                serial=serial, rows=profile.rows, cols=profile.cols,
                crc32=format(zlib.crc32(raw), 'x'), record=raw.hex())


def load_backup(document, profile):
    if (document.get('format') != 'qmk-ec-backup-1' or document.get('uid') != profile.uid.hex() or
            document.get('rows') != profile.rows or document.get('cols') != profile.cols):
        raise ECError('Backup belongs to a different board or unsupported format')
    try:
        raw = bytes.fromhex(document['record'])
        checksum = int(document['crc32'], 16)
    except (ValueError, TypeError, KeyError) as e:
        raise ECError('Malformed backup') from e
    if zlib.crc32(raw) != checksum or not decode_record(raw, profile).packed:
        raise ECError('Backup checksum invalid or record is not restorable packed data')
    return raw


def save_backup(path, raw, profile, serial=''):
    """Exclusive creation: never overwrite a user's recovery backup."""
    with Path(path).open('x', encoding='utf-8') as out:
        json.dump(backup_document(raw, profile, serial), out, indent=2)
        out.write('\n')
        out.flush()
        import os
        os.fsync(out.fileno())


def percent_q(percent):
    if not 1 <= percent <= 99:
        raise ECError('Actuation must be 1–98 percent or 99 (Deepest)')
    return 1022 if percent == 99 else (percent * 1023 + 50) // 100


def affine(q, baseline, bottom):
    if not 0 <= q <= 1023 or not 0 <= baseline <= bottom <= 1023:
        raise ECError('Invalid measured actuation range')
    return baseline + q * (bottom - baseline) // 1023


class Client:
    def __init__(self, exchange, profile):
        self.exchange = exchange
        self.profile = profile
        self.sequence = 0
        self.ready = False
        self.healthy = True
        self.storage = False
        self.firmware = ''
        self.samples = []
        self.record = None
        self.metadata_cursor = 0
        self.raw_page_cursor = 0
        self.updated_indices = set()
        self.capabilities = 0

    def request(self, op, payload=b''):
        if not self.healthy:
            raise ECError('EC42 transport is unverified; reconnect before further commands')
        if not self.ready and op not in (Op.HELLO, Op.DESCRIPTOR, Op.FIRMWARE):
            raise ECError('EC42 capability/identity handshake required')
        self.sequence = (self.sequence + 1) & 0xffff
        try:
            result = decode(self.exchange(encode(op, self.sequence, payload)))
            rop, sequence, status, response, data = result
            if rop != op or sequence != self.sequence or not response:
                raise ECError('Mismatched EC42 reply; close other HID applications')
        except Exception:
            self.healthy = False
            raise
        if status:
            raise ECError('EC42 rejected operation: {}. No automatic retry.'.format(
                ('OK', 'invalid state/packet', 'unsupported', 'range/keys held', 'stale token/revision')[status]))
        return data

    def identify(self):
        self.ready = False
        identity = bytes(self.exchange(b'\xfe\x00'.ljust(32, b'\0')))
        if len(identity) != 32 or not 1 <= int.from_bytes(identity[:4], 'little') <= 6 or identity[4:12] != self.profile.uid:
            raise ECError('Vial identity changed; no EC command sent')
        h = self.request(Op.HELLO)
        p = self.profile
        if (len(h) != 16 or h[:5] != b'QEC2\x09' or (u16(h, 5), u16(h, 7)) != (p.rows, p.cols) or
                u16(h, 9) != 1023 or h[11] != 1 or u16(h, 12) & 0x46 != 0x46 or
                h[14] != 5 or h[15] != 1):
            raise ECError('Requires EC42 v2.9 explicit calibration and snapshot capabilities; no write sent')
        d = self.request(Op.DESCRIPTOR)
        if (len(d) != 20 or (u16(d), u16(d, 2), u16(d, 4)) != (p.magic, p.record_size, 1023) or
                u16(d, 6) >= 32 or not 0 <= int.from_bytes(d[8:12], 'big') < int.from_bytes(d[12:16], 'big') <= u16(d, 16)*1024 or
                d[18] > 1 or d[19] != 1):
            raise ECError('Invalid EC storage/sensor descriptor; no write sent')
        self.storage = bool(d[18])
        self.capabilities = u16(h, 12)
        self.descriptor = d
        fw = self.request(Op.FIRMWARE)
        if not fw or any(c < 32 or c > 126 for c in fw.rstrip(b'\0')):
            raise ECError('Invalid EC firmware identity')
        firmware = fw.rstrip(b'\0').decode('ascii')
        if self.firmware and self.firmware != firmware:
            raise ECError('Firmware identity changed; reconnect before writing')
        self.firmware = firmware
        self.ready = True
        return dict(name=p.name, firmware=firmware, storage=self.storage, descriptor=d.hex())

    def status(self):
        p = self.request(Op.STATUS)
        if len(p) != 6 or p[0] not in (0, 1, 3, 4, 5) or p[3] > 3 or p[4] > 1 or p[5] > 1:
            raise ECError('Invalid calibration status')
        self.cal_status = p
        return p

    def read_record(self, op=Op.BACKUP, session=None):
        raw = b''
        for offset in range(0, self.profile.record_size, 17):
            count = min(17, self.profile.record_size-offset)
            q = be16(offset)+bytes([count])
            data = self.request(op, (be16(session) if session is not None else b'')+q)
            if len(data) != count+3 or data[:3] != q:
                raise ECError('Invalid calibration record page')
            raw += data[3:]
        if op != Op.BACKUP:
            decode_record(raw, self.profile)
        return raw

    def active_record(self):
        raw = self.read_record(Op.ACTIVE)
        self.record = decode_record(raw, self.profile)
        return raw

    def actuation(self, index=0xffff):
        p = self.request(Op.ACTUATION, be16(index))
        if (len(p) != 20 or p[4] > 4 or p[5] > 1 or p[10] > 1 or p[13] > 99 or
                u16(p, 18) != index or not 0 < u16(p, 8) < u16(p, 6) < 1023):
            raise ECError('Invalid actuation readback')
        return p

    def poll(self, selected=0, full=False, selected_only=False, metadata=True, background_pages=0):
        """Read one latched snapshot, optionally rotating bounded matrix pages.

        A sparse call always refreshes the selected cell. Other cached cells keep
        their original timestamps; updated_indices identifies fresh observations.
        The rolling matrix is therefore not an atomic full-matrix observation.
        """
        if not 0 <= background_pages <= 4:
            raise ECError('Background page count out of bounds')
        started = time.monotonic()
        n = self.profile.cells
        selected = min(max(0, selected), n-1)
        latch = self.request(Op.LATCH)
        if len(latch) != 8 or not u16(latch) or u16(latch, 6) != n:
            raise ECError('Invalid sensor snapshot')
        snapshot, seconds = u16(latch), int.from_bytes(latch[2:6], 'big') / 1000
        samples = [dict(s) for s in self.samples] if self.samples else [dict() for _ in range(n)]
        full = full or not self.samples
        if full:
            selected_only = False
        def bounded_request(op, payload):
            if time.monotonic() - started > 3:
                raise ECError('Sensor snapshot exceeded three-second budget')
            return self.request(op, payload)
        requests = [(selected, 1)] if selected_only else [(start, min(5, n-start)) for start in range(0, n, 5)]
        if selected_only and background_pages:
            background = []
            for _ in range(background_pages):
                start = (self.raw_page_cursor % ((n+4)//5))*5
                self.raw_page_cursor += 1
                background.append((start, min(5, n-start)))
            if any(start <= selected < start+count for start, count in background):
                requests = []  # Selected cell is already covered; avoid a duplicate.
            requests.extend(background)
        updated = set()
        for start, count in requests:
            q = be16(snapshot)+be16(start)+bytes([count])
            data = bounded_request(Op.PAGE, q)
            if len(data) != 5+3*count or data[:5] != q:
                raise ECError('Invalid sensor page')
            for j in range(count):
                raw, flags = u16(data, 5+3*j), data[7+3*j]
                if raw > 1023 or flags & 0x70 > 0x40 or (flags and not flags & 1):
                    raise ECError('Invalid sensor sample')
                updated.add(start+j)
                samples[start+j].update(raw=raw, sampled=bool(flags & 1), active=bool(flags & 2),
                                        debounced=bool(flags & 4), enabled=bool(flags & 8),
                                        capture=(flags >> 4) & 7, qualified=bool(flags & 128), seconds=seconds)
        if full and metadata != 'selected':
            details = list(range(n))
        elif not metadata:
            details = []
        else:
            details = [selected]
            if not selected_only and metadata != 'selected':
                for _ in range(min(12, n)):
                    i = self.metadata_cursor % n
                    self.metadata_cursor += 1
                    if i not in details:
                        details.append(i)
        for i in details:
            if time.monotonic()-started > 3:
                raise ECError('Sensor snapshot exceeded three-second budget')
            self._cell_details(snapshot, i, samples)
        self.samples = samples
        self.updated_indices = updated
        self.snapshot_id = snapshot
        return samples

    def _cell_details(self, snapshot, index, samples):
        q = be16(snapshot)+be16(index)
        data = self.request(Op.CELL, q)
        if len(data) != 20 or data[:4] != q:
            raise ECError('Invalid sensor metadata')
        values = struct.unpack('>8H', data[4:])
        sample = samples[index]
        if (any(values[k] > 1023 for k in (0, 1, 4, 5, 6, 7)) or
                (sample.get('sampled') and not values[4] <= sample['raw'] <= values[5])):
            raise ECError('Invalid measured sensor range')
        sample.update(zip(('baseline', 'bottom', 'press', 'release', 'minimum', 'maximum', 'peak', 'extremum'), values))
        sample['metadata_seconds'] = sample['seconds']
        sample['metadata_snapshot'] = snapshot

    def selected_details(self, index):
        if not self.samples or not 0 <= index < len(self.samples):
            raise ECError('A complete sensor snapshot is required')
        self._cell_details(self.snapshot_id, index, self.samples)
        return self.samples[index]

    def finish_snapshot_metadata(self):
        """Complete an existing latch without repeating its raw-page transfers.

        Used after the first selected-key preview. The caller retains exclusive
        transport ownership; no new latch may interleave with these CELL reads.
        """
        if not self.samples or not getattr(self, 'snapshot_id', 0):
            raise ECError('A sensor snapshot is required before reading metadata')
        started = time.monotonic()
        for index, sample in enumerate(self.samples):
            if sample.get('metadata_snapshot') == self.snapshot_id and 'baseline' in sample:
                continue
            if time.monotonic()-started > 3:
                raise ECError('Sensor metadata exceeded three-second budget')
            self._cell_details(self.snapshot_id, index, self.samples)
        return self.samples

    def released(self):
        if any(s['sampled'] and (s['active'] or s['debounced']) for s in self.poll()):
            raise ECError('Release every physical key before this operation')

    def writable(self, idle=True):
        self.identify()  # Revalidate selected board + running firmware, not just VID/PID.
        status = self.status()
        if not self.storage:
            raise ECError('EC storage not ready; no write sent')
        if idle and status[0]:
            raise ECError('Finish or cancel calibration before changing settings')

    def set_actuation(self, index, percent):
        if index != 0xffff and not 0 <= index < self.profile.cells:
            raise ECError('Actuation coordinate out of bounds')
        if not (1 <= percent <= 99 if index == 0xffff else 0 <= percent <= 99):
            raise ECError('Invalid actuation percentage')
        self.writable()
        before = self.actuation(index)
        ack = self.request(Op.SET_ACTUATION, be16(index)+bytes([percent])+before[:2])
        actual = self.actuation(index)
        if len(ack) != 2 or ack != actual[:2] or (index != 0xffff and actual[13] != percent) or (index == 0xffff and u16(actual, 6) != percent_q(percent)):
            raise ECError('Actuation acknowledgement/readback mismatch; no retry')
        return actual

    def set_global_actuation(self, percent):
        """Atomically set Global and clear all per-key overrides, when supported."""
        if not 1 <= percent <= 99:
            raise ECError('Invalid global actuation percentage')
        self.writable()
        if not self.capabilities & 0x0080:
            raise ECError('Global reset requires updated EC firmware with atomic Global support; no write sent')
        before = self.actuation()
        ack = self.request(Op.GLOBAL_RESET, be16(0xffff)+bytes([percent])+before[:2])
        actual = self.actuation()
        record = decode_record(self.active_record(), self.profile)
        if (len(ack) != 2 or ack != actual[:2] or
                u16(actual, 6) != percent_q(percent) or any(record.overrides)):
            raise ECError('Global reset acknowledgement/readback mismatch; no retry')
        return actual

    def set_rt(self, enabled, press, release):
        if enabled not in (0, 1) or not 1 <= press <= 255 or not 1 <= release <= 255:
            raise ECError('Invalid Rapid Trigger offsets')
        self.writable()
        before = self.actuation()
        q = bytes([enabled, press, release])
        ack = self.request(Op.SET_RT, q+before[:2])
        actual = self.actuation()
        if len(ack) != 2 or ack != actual[:2] or actual[10:13] != q:
            raise ECError('Rapid Trigger acknowledgement/readback mismatch; no retry')
        return actual

    def control(self, action, tail=b''):
        if action not in (1, 3, 4, 5, 6):
            raise ECError('Unsupported calibration action')
        self.writable(idle=False)
        ack = self.request(Op.CONTROL, bytes([action])+tail)
        if action != 1 and ack:
            raise ECError('Invalid calibration control acknowledgement')
        state = self.status()[0]
        expected = {3: 3, 4: 0, 5: 1, 6: 1}.get(action)
        if expected is not None and state != expected:
            raise ECError('Calibration state transition was not verified')
        return ack

    def start(self, backup_path):
        self.writable()
        va = self.actuation()
        if va[4] not in (0, 4):
            raise ECError('Wait for actuation settings to report Saved before calibration')
        self.released()
        raw = self.read_record()
        save_backup(backup_path, raw, self.profile)  # Must succeed BEFORE volatile Start.
        self.capture_base = self.active_record()
        ack = self.request(Op.CONTROL, b'\x01'+self.status()[4:5])
        status = self.status()
        if len(ack) != 2 or not u16(ack) or status[0] != 1 or status[1:3] != ack:
            raise ECError('Calibration Start token/state was not verified')
        return status

    def review(self, fast=False):
        self.control(3)
        status = self.status()
        session = u16(status, 1)
        proposed = self.read_record(Op.PROPOSAL, session)
        current = getattr(self, 'capture_base', None) if fast else None
        current = current or self.active_record()
        samples = self.poll(metadata=False) if fast else self.poll(full=True)
        rows = []
        for i, s in enumerate(samples):
            if not s['sampled']:
                rows.append(dict(status=4, reason='Firmware nonexistent', index=i))
                continue
            if fast:
                v, old = u16(proposed, 9+2*i), u16(current, 9+2*i)
                state = s['capture']
                if ((state == 1 and (v & 0xc000 != 0xc000 or not v & 1023)) or
                        (state == 0 and v != old) or
                        (state in (2, 3) and v != ((old & ~0x8000) | 0x2000))):
                    raise ECError('Capture flags/proposal mismatch; not safe to apply')
                reason = ('Saved calibration retained' if v & 0x8000 else 'Untouched; disabled',
                          'NEW firmware-qualified capture', 'Insufficient movement; retry',
                          'Invalid thresholds/RT range; retry')[state]
                rows.append(dict(index=i, status=state, high=v & 1023 if state == 1 else None, reason=reason))
                continue
            data = self.request(Op.EVIDENCE, be16(session)+be16(i))
            if len(data) != 9 or u16(data) != i or data[8] > 3:
                raise ECError('Invalid manual capture evidence')
            low, high, count, flags, state = u16(data, 2), u16(data, 4), data[6], data[7], data[8]
            v, old = u16(proposed, 9+2*i), u16(current, 9+2*i)
            if state == 1:
                baseline, press_q, release_q = s['baseline'], u16(proposed, 1), u16(proposed, 3)
                press = affine(press_q, baseline, high)
                release = affine(release_q, baseline, high)
                if count < 16 or low > high or high-low < 100 or high < baseline+100 or not baseline < release < press < high:
                    raise ECError('Capture does not contain sustained measured travel/valid thresholds')
            if ((state == 1 and (v & 0xc000 != 0xc000 or v & 1023 != high)) or
                    (state == 0 and v != old) or
                    (state in (2, 3) and v != ((old & ~0x8000) | 0x2000))):
                raise ECError('Capture evidence/proposal mismatch; not safe to apply')
            reason = ('Saved calibration retained' if v & 0x8000 else 'Untouched; disabled',
                      'NEW sustained capture', 'Insufficient sustained movement; retry',
                      'Invalid thresholds/RT range; retry')[state]
            rows.append(dict(index=i, status=state, low=low, high=high, count=count, flags=flags, reason=reason))
        can_apply = any(r['status'] == 1 for r in rows)
        error = ''
        if can_apply:
            try:
                self.request(Op.VALIDATE, be16(session))
            except ECError as e:
                can_apply, error = False, str(e)
        return dict(session=session, proposed=proposed, rows=rows, can_apply=can_apply, error=error)

    def apply_review(self, review):
        self.writable(idle=False)
        status = self.status()
        session = be16(review['session'])
        if status[0] not in (3, 4) or status[1:3] != session or not review['can_apply']:
            raise ECError('Stale or invalid calibration review; finish a fresh capture')
        self.released()
        self.request(Op.VALIDATE, session)
        expected = self.read_record(Op.PROPOSAL, review['session'])
        if expected != review['proposed']:
            raise ECError('Proposal changed since review; no activation sent')
        self.request(Op.ACTIVATE, session)
        try:
            if self.request(Op.CONFIG, b'\x01') != expected[:9]:
                raise ECError('Active configuration readback mismatch')
            time.sleep(.1)  # Firmware/debounce reconciliation, not a save delay.
            for i, s in enumerate(self.poll(full=True)):
                v = u16(expected, 9+2*i)
                if s['sampled'] and (s['enabled'] != bool(v & 0x8000) or s['qualified'] != bool(v & 0x4000) or s['active'] or s['debounced']):
                    raise ECError('Active flags or released-key verification failed; not saved')
        except Exception:
            # Only cancel if the transport still has a verified reply stream.
            if self.healthy:
                self.request(Op.CONTROL, b'\x04')
            raise
        self.request(Op.SAVE, session)
        actual = self.read_record()
        if decode_record(actual, self.profile).canonical != decode_record(expected, self.profile).canonical or decode_record(actual, self.profile).overrides != decode_record(expected, self.profile).overrides:
            raise ECError('Saved record mismatch; stop and restore a verified backup')
        self.record = decode_record(actual, self.profile)
        return actual

    def restore(self, raw):
        if not decode_record(raw, self.profile).packed:
            raise ECError('Only validated packed backups can be restored')
        self.writable()
        self.released()
        token = self.request(Op.RESTORE_BEGIN, be16(len(raw))+struct.pack('>I', zlib.crc32(raw)))
        if len(token) != 2 or not u16(token):
            raise ECError('Invalid restore token')
        for offset in range(0, len(raw), 15):
            part = raw[offset:offset+15]
            self.request(Op.RESTORE_CHUNK, token+be16(offset)+bytes([len(part)])+part)
        self.request(Op.RESTORE_COMMIT, token)
        if self.read_record() != raw:
            raise ECError('Restore readback mismatch; no automatic retry')
        return raw

    def bootloader(self):
        self.control(4)
        q = b'\xcaEC41\x07'.ljust(32, b'\0')
        reply = bytes(self.exchange(q))
        if len(reply) != 32 or reply[:8] != q[:8] or reply[8]:
            raise ECError('Bootloader entry not acknowledged; no automatic retry')
