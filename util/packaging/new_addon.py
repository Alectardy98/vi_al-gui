#!/usr/bin/env python3
"""Create a safe, UID-gated add-on using the same format as the shipped three."""
import argparse
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('id');parser.add_argument('--name',required=True)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
if not re.fullmatch(r'[a-z][a-z0-9_]{1,63}',args.id):parser.error('Use a lowercase snake_case ID.')
root=args.output or ROOT/'addons'/args.id
root.mkdir(parents=True,exist_ok=False)
package=root/'python/vi_al_addons'/args.id;package.mkdir(parents=True)
(root/'addon.json').write_text(json.dumps({'api':1,'id':args.id,'name':args.name,'version':'1.0.0',
 'entrypoint':'provider','description':'Describe the keyboard and supported features.'},indent=2)+'\n')
(package/'__init__.py').write_text('"""'+args.name+' add-on."""\n')
(package/'provider.py').write_text('''from PyQt5.QtWidgets import QLabel
from addon_runtime import Addon, Page, Session
from editor.basic_editor import BasicEditor

# Add verified Vial UID integers here before the tab becomes available.
SUPPORTED_UIDS = set()

class KeyboardPage(BasicEditor):
    def __init__(self):
        super().__init__()
        self.addWidget(QLabel("Add the keyboard controls here."))
    def valid(self):
        keyboard = getattr(self.device, 'keyboard', None)
        return getattr(keyboard, 'keyboard_id', None) in SUPPORTED_UIDS

class KeyboardSession(Session):
    def __init__(self, window, appctx):
        self.pages = (Page(KeyboardPage(), '''+repr(args.name)+''', 240),)

ADDON = Addon('''+repr(args.id)+''', create_session=KeyboardSession)
''')
(root/'README.md').write_text('Add a verified keyboard UID in provider.py, implement its controls, then package\nthis directory with util/packaging/build_addons.py. Never send board-specific\ncommands to an unidentified keyboard. See docs/ADDONS.md for API and lifecycle.\n')
print(root)
