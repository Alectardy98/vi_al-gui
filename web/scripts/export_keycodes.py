#!/usr/bin/env python3
"""Refresh web categories, aliases and encodings from desktop Vial definitions."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/main/python'))
from keycodes import keycodes as desktop

Keycode = desktop.Keycode
sets = [
    ('Basic', desktop.KEYCODES_SPECIAL + desktop.KEYCODES_BASIC + desktop.KEYCODES_SHIFTED),
    ('ISO/JIS', desktop.KEYCODES_SPECIAL + desktop.KEYCODES_BASIC + desktop.KEYCODES_SHIFTED + desktop.KEYCODES_ISO),
    ('Quantum', desktop.KEYCODES_BOOT + desktop.KEYCODES_MODIFIERS + desktop.KEYCODES_QUANTUM),
    ('Backlight', desktop.KEYCODES_BACKLIGHT),
    ('Media & Mouse', desktop.KEYCODES_MEDIA),
    ('MIDI', desktop.KEYCODES_MIDI_BASIC + desktop.KEYCODES_MIDI_ADVANCED),
    ('Macro', desktop.KEYCODES_MACRO_BASE),
]
result = {'encodings': {}}
for version in (5, 6):
    Keycode.protocol = version
    rows = {}
    def resolved(name):
        try:
            value = Keycode.resolve(name)
            return value if isinstance(value, int) and 0 <= value <= 65535 else None
        except RuntimeError:
            return None
    for category, keys in sets:
        for key in keys:
            code = resolved(key.qmk_id)
            if code is None:
                continue
            if key.qmk_id not in rows:
                row = dict(code=code, id=key.qmk_id, label=key.label.replace('\n', ' '),
                           title=key.tooltip or '', categories=[], aliases=key.alias,
                           masked=key.masked)
                if key.requires_feature:
                    row['feature'] = key.requires_feature
                if category == 'MIDI':
                    row['midi'] = 'advanced' if key in desktop.KEYCODES_MIDI_ADVANCED else 'basic'
                rows[key.qmk_id] = row
            rows[key.qmk_id]['categories'].append(category)
    result[str(version)] = list(rows.values())
    result['encodings'][str(version)] = dict(
        layers={name: resolved(name + '(0)') for name in ('MO','DF','PDF','TG','TT','OSL','TO')},
        layerTap=resolved('LT0(kc)'), macro=resolved('M0'), tapDance=resolved('TD(0)'),
        user=resolved('USER00'), fn13=resolved('FN_MO13'), fn23=resolved('FN_MO23'),
        layerLock=resolved('QK_LAYER_LOCK'))
(ROOT / 'web/src/data/keycodes.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
print('Exported', sum(len(result[str(v)]) for v in (5, 6)), 'categorized keycodes and dynamic encodings')
