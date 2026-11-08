# SPDX-License-Identifier: GPL-2.0-or-later
"""Frozen-app bridge: load each definition through Vi_al's offline dummy loader.

Set VI_AL_SMOKE_TEST=1, VI_AL_TEST_BRIDGE to this file, VI_AL_LAYOUT_REVIEW to
an output directory prepared by review_layouts.py, and use an isolated add-on
profile. No hardware or keyboard settings are accessed.
"""
import json,os,time,traceback
from pathlib import Path
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox
from keycodes.keycodes import Keycode,recreate_keyboard_keycodes

root=Path(os.environ['VI_AL_LAYOUT_REVIEW']);cases=json.loads((root/'cases.json').read_text());results=[];index=0;loaded=False;deadline=time.monotonic()+180
WINDOW.resize(1800,1100)

def tick():
 global index,loaded
 try:
  assert time.monotonic()<deadline,'Offline layout review timed out'
  assert not [w for w in APP.topLevelWidgets()if isinstance(w,QMessageBox)and w.isVisible()]
  if index==len(cases):
   (root/'sideload-results.json').write_text(json.dumps(results,indent=2)+'\n')
   WINDOW.close();APP.exit(0);return
  case=cases[index]
  if not loaded:
   WINDOW.autorefresh.load_dummy(json.dumps(case['definition']).encode());WINDOW.autorefresh.update(quiet=False,hard=True);loaded=True
   QTimer.singleShot(150,tick);return
  device=WINDOW.autorefresh.current_device
  if not device or not device.sideload or device.keyboard.definition!=case['definition']:
   QTimer.singleShot(100,tick);return
  keyboard=device.keyboard
  keyboard.vial_protocol=6;keyboard.layers=case['layers'];recreate_keyboard_keycodes(keyboard)
  for layer in range(keyboard.layers):
   for row,col in keyboard.rowcol:
    code=case['codes'][row*case['cols']+col]if layer==0 else 1
    keyboard.layout[(layer,row,col)]=Keycode.serialize(code)
  WINDOW.combobox_devices.setItemText(WINDOW.combobox_devices.currentIndex(),'[OFFLINE JSON REVIEW] '+case['board'])
  WINDOW.rebuild();WINDOW.refresh_tabs();WINDOW.tabs.setCurrentIndex(0)
  editor=WINDOW.keymap_editor;editor.container.set_scale(.9);editor.refresh_layer_display()
  APP.processEvents()
  assert len(editor.container.widgets)==len(keyboard.keys),(case['board'],len(editor.container.widgets),len(keyboard.keys))
  assert WINDOW.grab().save(str(root/(case['board']+'-vial.png')))
  assert editor.container.grab().save(str(root/(case['board']+'-keyboard.png')))
  results.append({'board':case['board'],'mode':'Vi_al built-in offline JSON loader','visible_keys':len(editor.container.widgets),'version':APP.applicationVersion(),'geometry':[dict(row=k.row,col=k.col,x=k.x,y=k.y,w=k.width,h=k.height,x2=k.x2,y2=k.y2,w2=k.width2,h2=k.height2)for k in keyboard.keys]})
  index+=1;loaded=False;QTimer.singleShot(100,tick)
 except Exception:
  (root/'error.txt').write_text(traceback.format_exc());traceback.print_exc();APP.exit(1)
QTimer.singleShot(100,tick)
