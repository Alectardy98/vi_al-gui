# SPDX-License-Identifier: GPL-2.0-or-later
"""AW768 lighting codec, recovered from Dell's Durotan DLL and V0039 image.

All offsets below exclude HIDAPI's leading zero report-number placeholder.
The native PCB, not the RP2040, renders the effects. Never use these reports
on QMK's 32-byte Raw HID interface. See docs/aw768/ for provenance/limitations.
"""
from dataclasses import dataclass, replace

GROUPS = ((0x0002, 'WASD'), (0x0010, 'Arrows'), (0xE000, 'Number row'),
          (0x0700, 'Function row'), (0x0020, 'Numpad'), (0x1000, 'Logo'),
          (0x0080, 'Ambient'), (0x004D, 'Other keys'))
MACRO_ZONE = 0x10000  # UI-only zone; never serialize as a 16-bit lighting mask
ALTERNATE_ZONES = (0x2103, 0x4204, 0x8408, 0x0810, 0x0060, 0x1080)
EFFECTS = ((0, 'Color'), (1, 'Pulse'), (2, 'Breathing'), (3, 'Morph'), (4, 'Spectrum'))
GLOBAL_EFFECTS = EFFECTS + ((8, 'Scanner'), (10, 'Rainbow wave'))
ZONE_GROUPS = tuple((mask, 'Zone {}'.format(i+1)) for i, mask in enumerate(ALTERNATE_ZONES))
MASK_ORDER = (0xFFFF, 0xFFFF) + ALTERNATE_ZONES * 2 + tuple(m for m, _ in GROUPS) * 2


class ProtocolError(ValueError):
    pass


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ProtocolError(f'Invalid {label}: expected {low}–{high}.')
    return value


def profile_number(profile):
    return integer(profile, 1, 3, 'profile')


def selector(command, profile=0):
    # Closed allowlist: no firmware/DFU, keymap, macro or reset commands.
    if command not in (0x05, 0x85, 0x88, 0x8D, 0x86):
        raise ProtocolError('Unsupported lighting command.')
    if command != 0x88:
        profile_number(profile)
    elif profile != 0:
        raise ProtocolError('Status query has no profile.')
    return bytes((0, command, profile)) + bytes(62)


@dataclass(frozen=True)
class Lighting:
    mode: int = 0
    color0: tuple = (255, 255, 255)
    color1: tuple = (0, 0, 0)
    tempo: int = 2
    brightness: int = 10

    def validate(self):
        if self.mode not in dict(GLOBAL_EFFECTS) or type(self.mode) is not int:
            raise ProtocolError('Unsupported autonomous effect.')
        for color in (self.color0, self.color1):
            if not isinstance(color, tuple) or len(color) != 3:
                raise ProtocolError('Expected three RGB components.')
            for component in color:
                integer(component, 0, 255, 'RGB component')
        integer(self.tempo, 0, 3, 'speed')  # zero retained for existing native settings
        integer(self.brightness, 1, 10, 'brightness')
        return self


@dataclass(frozen=True)
class Record:
    raw: bytes
    legacy: bool = False
    @property
    def mask(self):
        return int.from_bytes(self.raw[14:16], 'big')
    @property
    def lighting(self):
        p = self.raw
        return Lighting(p[2], tuple(p[3:6]), tuple(p[6:9]), 3 - p[9] if self.legacy else p[9], p[10])


@dataclass(frozen=True)
class Snapshot:
    profile: int
    variant: str
    records: tuple
    fine: object = None
    macro_colors: object = None
    macro_sent: object = None
    @property
    def named_settings(self):
        return self.settings_for('groups')

    def records_for(self, scheme, *, reactive=False):
        if scheme == 'groups':
            return self.records[22:30] if reactive else self.records[14:22]
        if scheme == 'zones':
            return self.records[8:14] if reactive else self.records[2:8]
        if scheme == 'all':
            return self.records[1:2] if reactive else self.records[:1]
        raise ProtocolError('Unknown lighting selection scheme.')

    def settings_for(self, scheme):
        if scheme == 'fine':
            return dict(self.fine.settings) if self.fine is not None else {}
        return {r.mask: r.lighting for r in self.records_for(scheme)}


def parse_status(report):
    if len(report) != 65 or report[:2] != bytes((0, 0x88)):
        raise ProtocolError('Invalid native AW768 status response.')
    return profile_number(report[3])


def parse_snapshot(profile, reports):
    profile_number(profile)
    if len(reports) != 30:
        raise ProtocolError('Incomplete AW768 lighting snapshot (expected 30 records).')
    records = []
    for raw, mask in zip(reports, MASK_ORDER):
        raw = bytes(raw)
        if len(raw) != 64 or raw[:2] != bytes((0x85, profile)):
            raise ProtocolError('Unexpected AW768 lighting response.')
        record = Record(raw)
        if record.mask != mask or any(raw[16:]):
            raise ProtocolError('Unknown AW768 lighting layout/order; no writes permitted.')
        integer(raw[2], 0, 255, 'effect')
        integer(raw[9], 0, 3, 'speed')
        integer(raw[10], 0, 10, 'brightness')
        records.append(record)
    if all(r.raw[12:14] == bytes(2) for r in records):
        variant = 'legacy-readback'
    else:
        channels = (1, 2) + (1,) * 6 + (2,) * 6 + (1,) * 8 + (2,) * 8
        if not all(r.raw[12] == channel and r.raw[13] in (1, 2, 3)
                   for r, channel in zip(records, channels)):
            raise ProtocolError('Unknown AW768 channel layout; no writes permitted.')
        variant = 'v0039-readback'
    return Snapshot(profile, variant, tuple(replace(r, legacy=variant == 'legacy-readback') for r in records))


def named_batch(snapshot, changes):
    return lighting_batch(snapshot, changes, 'groups')


def lighting_batch(snapshot, changes, scheme='groups'):
    """Build the autonomous (live) half of a native lighting transaction.

    Never send an arbitrary partial zone: firmware FUN_00002504 uses a sequence
    counter starting at WASD and ending at Other keys. Preserve existing fields
    in all unchanged records. This half alone does not commit the active
    profile: use lighting_save_batch for the complete vendor save sequence.
    """
    records = snapshot.records_for(scheme)
    if not changes or not set(changes) <= {r.mask for r in records}:
        raise ProtocolError('Select a supported lighting group or zone.')
    for setting in changes.values():
        if not isinstance(setting, Lighting):
            raise ProtocolError('Invalid lighting settings.')
        setting.validate()
        if scheme != 'all' and setting.mode not in dict(EFFECTS):
            raise ProtocolError('This effect requires All keys.')
    brightnesses = {setting.brightness for setting in changes.values()}
    if len(brightnesses) != 1:
        raise ProtocolError('AW768 brightness is shared across the native profile.')
    brightness = next(iter(brightnesses))
    packets = []
    for record in records:
        # Legacy GET leaves channel/color-mode zero; these bytes are NOT an
        # alternate SET layout. SET uses the vendor DLL format on both boards.
        raw = bytearray(record.raw)
        if raw[2] not in dict(GLOBAL_EFFECTS if scheme == 'all' else EFFECTS):
            raise ProtocolError('Existing unsupported effect; refusing lossy batch rewrite.')
        raw[0] = 5
        if record.legacy:
            raw[9] = 3 - raw[9]
        raw[10] = brightness  # hardware profile brightness, not per-zone
        raw[12] = 1  # autonomous channel, unrelated to RP2040 key activity
        if snapshot.variant == 'legacy-readback':
            # Legacy GET omits color mode. Normalize the autonomous
            # effect to our documented single/morph/spectrum configuration.
            # Never infer hidden reactive settings from these zero bytes.
            raw[13] = 2 if raw[2] == 3 else 3 if raw[2] in (4,10) else 1
        if record.mask in changes:
            setting = changes[record.mask]
            raw[2] = setting.mode
            raw[3:6] = bytes(setting.color0)
            raw[6:9] = bytes(setting.color1)
            raw[9] = setting.tempo
            raw[10] = setting.brightness
            raw[11] = 0  # continuous animation, no keypress timeout
            raw[13] = 2 if setting.mode == 3 else 3 if setting.mode in (4,10) else 1
        packets.append(bytes((0,)) + bytes(raw))
    return tuple(packets)


def lighting_save_batch(snapshot, changes, scheme='groups'):
    """Dell's complete two-pass save: autonomous, then keypress NoChange.

    The original DLL uses mode FF on channel 2 for autonomous effects. On the
    current profile, the final channel-2 record triggers the native save flag;
    the channel-1-only sequence changes live output without that commit.
    Native key-reactive effects are not exposed on this RP2040 matrix swap.
    NoChange is the vendor's neutral keypress mode, not a firmware/reset command.
    """
    autonomous = lighting_batch(snapshot, changes, scheme)
    completion = []
    for packet in autonomous:
        raw = bytearray(packet)
        raw[3] = 0xFF  # native keypress NoChange mode
        raw[13] = 2    # keypress channel (HIDAPI includes leading report zero)
        completion.append(bytes(raw))
    return autonomous + tuple(completion)

FINE_GROUPS = tuple((index,'Zone {}'.format(index-1)) for index in range(2,14))

def fine_selector(profile):
    return bytes((0,0x0D,profile_number(profile),1))+bytes(61)


@dataclass(frozen=True)
class FineState:
    settings: dict
    priority: tuple


def parse_fine(profile,raw):
    """V0039 has separate ordinal RGB slots and a priority-ID permutation.

    The tag beside RGB slot i is priority[i], NOT that slot's color ID. The
    colors always belong to IDs2+i. See firmware c7ea..c81a and field tests.
    """
    if len(raw)!=64 or raw[:2]!=bytes((0x8D,profile)) or any(raw[51:]):
        raise ProtocolError('Invalid 12-zone readback.')
    brightness=integer(raw[2],1,10,'12-zone brightness')
    priority=tuple(raw[3+4*i] for i in range(12))
    if set(priority)!={i for i,_ in FINE_GROUPS}:
        raise ProtocolError('Invalid 12-zone priority permutation.')
    settings={}
    for i,(zone_id,_) in enumerate(FINE_GROUPS):
        offset=3+4*i
        settings[zone_id]=Lighting(0,tuple(raw[offset+1:offset+4]),(0,0,0),2,brightness)
    return FineState(settings,priority)


def fine_packet(profile,settings,priority=None):
    if set(settings)!={i for i,_ in FINE_GROUPS}:raise ProtocolError('Expected all 12 zone colors.')
    brightnesses={v.brightness for v in settings.values()}
    if len(brightnesses)!=1:raise ProtocolError('12-zone brightness is shared.')
    priority=tuple(priority) if priority is not None else tuple(i for i,_ in FINE_GROUPS)
    if len(priority)!=12 or set(priority)!=set(settings):raise ProtocolError('Invalid 12-zone priority.')
    raw=bytearray((0,0x0D,profile_number(profile),12))
    for zone_id in priority:
        setting=settings[zone_id].validate()
        if setting.mode!=0:raise ProtocolError('12-zone mode supports color only.')
        raw.extend((zone_id,*setting.color0,setting.brightness))
    return bytes(raw)+bytes(65-len(raw))


def macro_packet(profile,color):
    if not isinstance(color,tuple) or len(color)!=3:
        raise ProtocolError('Expected one Macro RGB color.')
    for component in color:integer(component,0,255,'Macro RGB component')
    # Three native modes are intentionally identical: X and M1–M5 are one
    # user-visible zone. This is NOT a macro assignment or profile command.
    return bytes((0,6,profile_number(profile)))+bytes(color)*3+bytes(53)


def parse_macro(profile,raw):
    if len(raw)!=65 or raw[:3]!=bytes((0,0x86,profile)):
        raise ProtocolError('Macro color readback unavailable.')
    return tuple(tuple(raw[i:i+3]) for i in (3,6,9))
