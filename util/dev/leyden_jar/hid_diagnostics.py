#!/usr/bin/env python3
"""Bounded native Leyden Jar status/capture; no persistent or output-state writes."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'src/main/python'), str(ROOT/'addons/leyden_jar/python')]


def running_gui():
    if not sys.platform.startswith('linux'):
        return False
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():
            continue
        try:
            if (item/'comm').read_text().strip().lower() == 'vi_al':
                return True
        except OSError:
            pass
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='List raw Vial HID interfaces without opening them')
    parser.add_argument('--uid', help='Exact eight-byte Vial UID, written as sixteen hexadecimal digits')
    parser.add_argument('--levels', action='store_true', help='Run one native DAC sweep')
    parser.add_argument('--capture-seconds', type=float, default=0, help='Finite capture duration, up to 600 seconds')
    parser.add_argument('--interval', type=float, default=.4, help='Minimum gap between completed captures')
    parser.add_argument('--output', type=Path, help='New directory for metadata and JSONL frames')
    args = parser.parse_args()
    if not 0 <= args.capture_seconds <= 600 or args.interval < .05:
        parser.error('Capture duration must be 0–600 seconds and interval at least 0.05 seconds.')
    if args.capture_seconds and not args.output:
        parser.error('A capture needs --output; existing evidence directories are never overwritten.')
    if sys.platform.startswith('linux'):
        import hidraw as hid
    else:
        import hid
    devices = [d for d in hid.enumerate() if d.get('usage_page') == 0xff60 and d.get('usage') == 0x61]
    if args.list:
        print(json.dumps([{k:(os.fsdecode(v) if isinstance(v,bytes) else v) for k,v in d.items()} for d in devices],indent=2))
        return
    if not args.uid or len(args.uid) != 16:
        parser.error('Specify an exact 16-digit --uid, or use --list.')
    try:
        uid = bytes.fromhex(args.uid)
    except ValueError:
        parser.error('UID must be hexadecimal.')
    if running_gui():
        parser.error('Close Vi_al before using a second HID client. Also close browser configurators.')
    from types import SimpleNamespace
    from editor.qmk_settings import QmkSettings
    QmkSettings.initialize(SimpleNamespace(get_resource=lambda name:str(ROOT/'src/main/resources/base'/name)))
    from protocol.keyboard_comm import Keyboard
    from vi_al_addons.leyden_jar.protocol import Client, PROFILES
    if uid.hex() not in {p['uid'] for p in PROFILES}:
        parser.error('UID is not a known Leyden Jar identity.')
    matches = []
    for device in devices:
        handle = hid.device()
        try:
            handle.open_path(device['path'])
            keyboard = Keyboard(handle)
            if keyboard.get_uid() == uid:
                matches.append((handle, keyboard))
            else:
                handle.close()
        except OSError:
            handle.close()
    if len(matches) != 1:
        for handle,_ in matches:
            handle.close()
        parser.error('Expected one matching controller; found %d.' % len(matches))
    handle,keyboard = matches[0]
    try:
        keyboard.reload()
        client = Client(keyboard).connect()
        status = {'uid':uid.hex(),'version':client.version,'details':vars(client.details),
                  'row_map':client.row_map,'col_map':client.col_map,'thresholds':client.thresholds,
                  'references':client.references,'typing_enabled':client.enabled,
                  'persistent_offsets':client.offsets,'active_pads':sum(v!=255 for v in client.bin_map.values())}
        print(json.dumps(status,indent=2))
        if args.output:
            args.output.mkdir(parents=True,exist_ok=False)
            (args.output/'status.json').write_text(json.dumps(status,indent=2)+'\n')
        if args.capture_seconds:
            start=time.monotonic()
            with (args.output/'frames.jsonl').open('x') as stream:
                while time.monotonic()-start < args.capture_seconds:
                    if running_gui():
                        print('Vi_al opened; stopping capture before another HID exchange.')
                        break
                    values=client.levels();logical,physical=client.keypresses()
                    frame={'seconds':time.monotonic()-start,'levels':{f'{r},{c}':v for (r,c),v in values.items()},
                           'logical_pressed':sorted(logical),'physical_pressed':sorted(physical)}
                    stream.write(json.dumps(frame)+'\n');stream.flush();time.sleep(args.interval)
        elif args.levels:
            print(json.dumps({'levels':{f'{r},{c}':v for (r,c),v in client.levels().items()}},indent=2))
    finally:
        handle.close()


if __name__=='__main__':
    main()
