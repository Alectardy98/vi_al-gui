#!/usr/bin/env python3
"""Export real Vial definitions and independent desktop placement vectors.

Optional developer tool; requires the desktop Python/Qt environment. Browser
builds and tests use the checked-in output without Python or firmware source.
"""
import argparse
import base64
from copy import deepcopy
import json
import lzma
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/main/python'))
from PyQt5.QtWidgets import QApplication
from kle_serial import Serial
from widgets.keyboard_widget import KeyboardWidget


class Choices:
    def __init__(self, values):
        self.values = values

    def get_choice(self, index):
        return self.values[index]


def export(path):
    definition = json.loads(path.read_text())
    keys = Serial().deserialize(definition['layouts']['keymap']).keys
    raw = [[k.x, k.y] for k in keys]
    for key in keys:
        key.row = key.col = None
        key.layout_index = key.layout_option = -1
        if key.labels[0] and ',' in key.labels[0]:
            key.row, key.col = map(int, key.labels[0].split(','))
        if key.labels[8]:
            key.layout_index, key.layout_option = map(int, key.labels[8].split(','))
    keys = [k for k in keys if k.row is not None or k.decal]
    labels = definition['layouts'].get('labels', [])
    counts = [2 if isinstance(label, str) else len(label) - 1 for label in labels]
    variants = [[0] * len(labels)]
    for group, count in enumerate(counts):
        for choice in range(1, count):
            values = [0] * len(labels)
            values[group] = choice
            variants.append(values)
    variants.append([count - 1 for count in counts])
    snapshots = []
    for values in variants:
        widget = KeyboardWidget(Choices(values))
        widget.set_keys(deepcopy(keys), [])
        positions = [[w.desc.row, w.desc.col,
                      round(w.desc.x + (w.shift_x - widget.padding) / w.size, 4),
                      round(w.desc.y + (w.shift_y - widget.padding) / w.size, 4)]
                     for w in widget.widgets]
        snapshots.append(dict(values=values, positions=positions))
    parts = path.parts
    source = str(Path(*parts[parts.index('keyboards'):])) if 'keyboards' in parts else path.name
    return dict(source=source, definition=definition, rawCoordinates=raw,
                layouts=snapshots,
                compressed=base64.b64encode(lzma.compress(json.dumps(definition).encode())).decode())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('definitions', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, default=ROOT / 'web/tests/fixtures/zenithal-layouts.json')
    args = parser.parse_args()
    app = QApplication([])
    result = [export(path) for path in args.definitions]
    args.output.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    print(f'Exported {len(result)} definitions and desktop placement vectors to {args.output}')
