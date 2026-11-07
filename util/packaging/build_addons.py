#!/usr/bin/env python3
"""Build optional, installable Vi_al add-on ZIPs. No GUI or USB access."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def build(source, output):
    metadata = json.loads((source/'addon.json').read_text())
    output.mkdir(parents=True, exist_ok=True)
    path = output / ('Vi_al-'+metadata['id']+'-'+metadata['version']+'.zip')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(source.rglob('*')):
            if item.is_file() and '__pycache__' not in item.parts and item.suffix != '.pyc':
                archive.write(item, item.relative_to(source).as_posix())
    # Bundle only current packages; retain older generated ZIPs outside dist/.
    for old in output.glob('Vi_al-'+metadata['id']+'-*.zip'):
        if old == path:
            continue
        history=ROOT/'artifacts/addon-history';history.mkdir(parents=True,exist_ok=True)
        previous=history/old.name
        if previous.exists():
            previous=history/(old.stem+'-'+hashlib.sha256(old.read_bytes()).hexdigest()[:12]+old.suffix)
        old.replace(previous)
    print(path)
    return path


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'addons')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/addons')
    args=parser.parse_args()
    if not args.source.is_dir():
        parser.exit(0,'No optional add-ons directory; core build is unaffected.\n')
    for manifest in sorted(args.source.glob('*/addon.json')):
        build(manifest.parent,args.output)
