#!/usr/bin/env python3
"""Refresh the checked-in web catalogue from the desktop's keycode definitions."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/main/python'))
from keycodes.keycodes import Keycode, KEYCODES
result = {}
for version in (5, 6):
    Keycode.protocol = version
    rows = []
    for key in KEYCODES:
        if key.masked:
            continue
        try:
            code = Keycode.resolve(key.qmk_id)
        except RuntimeError:
            continue
        if isinstance(code, int) and 0 <= code <= 65535:
            rows.append(dict(code=code, id=key.qmk_id, label=key.label.replace('\n', ' '), title=key.tooltip or ''))
    result[str(version)] = rows
(ROOT / 'web/src/data/keycodes.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'))+'\n')
print('Exported', sum(map(len, result.values())), 'versioned keycodes')
