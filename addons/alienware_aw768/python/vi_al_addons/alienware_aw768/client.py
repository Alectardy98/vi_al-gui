# SPDX-License-Identifier: GPL-2.0-or-later
"""Serialized native lighting operations; never opens the RP2040 or DFU.

Each operation re-proves USB topology, opens the native lighting interface, and
closes it on every exit. Errors never trigger automatic write retries. A failed
batch may have partially changed native lights: Reload and explicitly Apply.
"""
import threading
import time
from dataclasses import replace

from .identity import resolve_companion
from .protocol import (ProtocolError, parse_status, parse_snapshot, selector,
                       lighting_save_batch, parse_fine, fine_packet, fine_selector, MACRO_ZONE, macro_packet, parse_macro)


class Client:
    def __init__(self, selected_descriptor, vial_uid, *, backend=None, resolver=resolve_companion,
                 sleep=time.sleep, monotonic=time.monotonic):
        if backend is None:
            from hidproxy import hid as backend
        self.backend = backend
        self.selected = dict(selected_descriptor)
        self.uid = vial_uid
        self.resolver = resolver
        self.sleep = sleep
        self.monotonic = monotonic
        self.lock = threading.Lock()
        self._supports_fine = None
        self._supports_macro_read = None

    def close(self):
        # Handles are scoped to operations, not retained across device switches.
        pass

    def _open(self):
        companion = self.resolver(self.selected, self.uid, self.backend.enumerate())
        handle = self.backend.device()
        try:
            handle.open_path(companion.path)
        except Exception:
            handle.close()
            raise
        return handle

    def _feature(self, h, command, profile=0):
        self.sleep(.01)  # vendor sendSetFeature pacing, off the Qt thread
        if h.send_feature_report(selector(command, profile)) != 65:
            raise ProtocolError('Short native lighting feature transfer.')
        self.sleep(.01)

    def _profile(self, h):
        self._feature(h, 0x88)
        return parse_status(bytes(h.get_feature_report(0, 65)))

    def _load(self, h):
        profile = self._profile(h)
        # Drain stale responses left by a prior failed transaction. Bounded.
        for _ in range(32):
            if not h.read(64, timeout_ms=1):
                break
        else:
            raise ProtocolError('Native lighting input did not become idle.')
        self._feature(h, 0x85, profile)
        frames = []
        deadline = self.monotonic() + 3
        while len(frames) < 30:
            if self.monotonic() >= deadline:
                raise ProtocolError('Native lighting readback timed out; settings are unconfirmed.')
            raw = bytes(h.read(64, timeout_ms=100))
            if raw:
                frames.append(raw)
        result = parse_snapshot(profile, frames)
        if self._supports_fine is not False:
            self._feature(h,0x8D,profile)
            raw=bytes(h.read(64,timeout_ms=300))
            if not raw:
                if self._supports_fine:
                    raise ProtocolError('12-zone readback timed out; settings are unconfirmed.')
                self._supports_fine=False
            else:
                result=replace(result,fine=parse_fine(profile,raw))
                self._supports_fine=True
        if self._supports_macro_read is not False:
            self._feature(h,0x86,profile)
            raw=bytes(h.get_feature_report(0,65))
            if len(raw)==65 and raw[1]==0x88:
                # Confirmed legacy behavior: stale status, not RGB values.
                self._supports_macro_read=False
            else:
                result=replace(result,macro_colors=parse_macro(profile,raw))
                self._supports_macro_read=True
        return result

    def load(self):
        with self.lock:
            h = self._open()
            try:
                return self._load(h)
            finally:
                h.close()

    def apply(self, settings, scheme='groups'):
        with self.lock:
            h = self._open()
            try:
                before = self._load(h)
                settings=dict(settings)
                macro=settings.pop(MACRO_ZONE,None) if scheme=='groups' else None
                if macro is not None:
                    macro.validate()
                    if macro.mode!=0:raise ProtocolError('Macro zone supports Color or Off only.')
                    macro_packet(before.profile,macro.color0)
                if scheme=='fine':
                    if before.fine is None:
                        raise ProtocolError('This PCB did not provide 12-zone readback; no 12-zone settings sent.')
                    original=before.fine.settings
                    if not settings or not set(settings)<=set(original):
                        raise ProtocolError('Invalid 12-zone selection.')
                    merged=dict(original);merged.update(settings)
                    brightnesses={v.brightness for v in settings.values()}
                    if len(brightnesses)!=1:raise ProtocolError('12-zone brightness is shared.')
                    brightness=next(iter(brightnesses))
                    merged={k:replace(v,brightness=brightness) for k,v in merged.items()}
                    # Native updates raise changed regions above overlapping
                    # regions. Retain all other priorities, colors and bounds.
                    changed=[k for k,v in settings.items() if v.color0!=original[k].color0]
                    priority=tuple(k for k in before.fine.priority if k not in changed)+tuple(changed)
                    packets=(fine_packet(before.profile,merged,priority),)
                    settings=merged
                else:
                    packets = lighting_save_batch(before, settings, scheme) if settings else ()
                    if not packets and macro is None:raise ProtocolError('No lighting zones selected.')
                # A native profile change invalidates the intended destination.
                if self._profile(h) != before.profile:
                    raise ProtocolError('Native profile changed; reload before applying.')
                for packet in packets:
                    if scheme=='fine':
                        self.sleep(.01)
                        if h.send_feature_report(fine_selector(before.profile))!=65:
                            raise ProtocolError('Short 12-zone selector transfer.')
                        self.sleep(.01)
                    else:
                        self._feature(h, 0x05, before.profile)
                    self.sleep(.01)
                    if h.write(packet) != 65:
                        raise ProtocolError('Short native lighting output; reload before retrying.')
                    self.sleep(.01)
                if macro is not None:
                    self.sleep(.01)
                    if h.send_feature_report(macro_packet(before.profile,macro.color0))!=65:
                        raise ProtocolError('Short Macro color transfer; no automatic retry.')
                    self.sleep(.03)
                self.sleep(.10)
                after = self._load(h)
                if macro is not None:
                    if after.macro_colors is not None and any(c!=macro.color0 for c in after.macro_colors):
                        raise ProtocolError('Macro color readback does not match.')
                    after=replace(after,macro_sent=macro.color0)
                if after.profile != before.profile:
                    raise ProtocolError('Native profile changed while applying; reload.')
                if scheme=='fine':
                    actual=after.settings_for('fine')
                    if after.fine is None or after.fine.priority!=priority or set(actual)!=set(settings) or any(actual[k].color0!=v.color0 or actual[k].brightness!=v.brightness for k,v in settings.items()):
                        raise ProtocolError('12-zone readback does not match; success unconfirmed.')
                    return after
                for channel in (1, 2):
                    expected = {int.from_bytes(p[15:17], 'big'): p[3:12]
                                for p in packets if p[13] == channel}
                    for record in after.records_for(scheme, reactive=channel == 2):
                        if record.mask not in expected:continue
                        observed = bytearray(record.raw[2:11])
                        if record.legacy:
                            observed[7] = 3 - observed[7]
                        if bytes(observed) != expected[record.mask]:
                            raise ProtocolError('Native lighting readback does not match; success unconfirmed.')
                return after
            finally:
                h.close()
