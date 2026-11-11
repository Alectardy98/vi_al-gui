#!/usr/bin/env python3
"""Refresh native Leyden Jar UID/dimension gates from a QMK source checkout."""
import argparse
import json
from pathlib import Path
import re


def profiles(qmk):
    root = qmk / 'keyboards/leyden_jar'
    result = {}
    for definition in sorted(root.glob('**/keymaps/*/vial.json')):
        config = definition.with_name('config.h')
        if not config.exists():
            continue
        match = re.search(r'^\s*#define\s+VIAL_KEYBOARD_UID\s+\{([^}]+)\}', config.read_text(), re.M)
        if not match:
            continue
        uid = bytes(int(n.strip(), 0) for n in match.group(1).split(',') if n.strip())
        if len(uid) != 8:
            raise ValueError('Expected eight UID bytes: ' + str(config))
        data = json.loads(definition.read_text())
        matrix = data['matrix']
        key = uid.hex(), matrix['rows'], matrix['cols']
        result[key] = {'uid': uid.hex(), 'rows': matrix['rows'], 'cols': matrix['cols'],
                       'source': definition.relative_to(qmk).as_posix()}
    if not result:
        raise ValueError('No native Leyden Jar Vial definitions found.')
    return sorted(result.values(), key=lambda p: (p['uid'], p['rows'], p['cols']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('qmk', type=Path, help='QMK repository root')
    parser.add_argument('--web', type=Path, help='Optional checkout containing web/addons/leyden_jar')
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[3] / 'addons/leyden_jar/python/vi_al_addons/leyden_jar/profiles.json'
    values = profiles(args.qmk.resolve())
    target.write_text(json.dumps(values, indent=2) + '\n')
    print('%d UID/dimension profiles: %s' % (len(values), target))
    if args.web:
        browser = args.web / 'web/addons/leyden_jar/profiles.json'
        if not browser.parent.is_dir():
            raise ValueError('The web Leyden Jar add-on directory does not exist.')
        browser.write_text(json.dumps(values, indent=2) + '\n')
        print(browser)
