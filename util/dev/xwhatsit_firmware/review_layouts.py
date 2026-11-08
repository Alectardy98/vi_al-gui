#!/usr/bin/env python3
"""Prepare a hardware-free frozen Vi_al layout-review run; never opens USB."""
import argparse,json,lzma,re,subprocess,shutil
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('qmk_root',type=Path);p.add_argument('--output',type=Path,required=True)
p.add_argument('--reference-revision',default='5a3dc76a2a^',help='Historical QMK revision containing original photograph links')
a=p.parse_args();root=a.qmk_root.resolve();a.output.mkdir(parents=True,exist_ok=True)
rows=json.loads(Path(__file__).with_name('ports.json').read_text());cases=[]
for row in rows:
 board=root/'keyboards/xwhatsit/ibm'/row['board'];definition=json.loads((board/'keymaps/vial/vial.json').read_text());info=json.loads((board/'universal/keyboard.json').read_text())
 keymap=(board/'keymaps/vial/keymap.c').read_text();used=re.search(r'\[_BASE\]\s*=\s*(LAYOUT\w*)',keymap)[1]
 name=row['target'].replace('/','_').replace(':','_');elf=root/'.build'/(name+'.elf')
 symbols=subprocess.check_output(['avr-nm','-S',str(elf)],text=True);match=re.search(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+\w\s+keymaps$',symbols,re.M);assert match,row['board']
 address=int(match[1],16);image=bytearray([255])*32768;upper=0
 for line in(root/(name+'.hex')).read_text().splitlines():
  raw=bytes.fromhex(line[1:]);assert sum(raw)%256==0
  if raw[3]==4:upper=int.from_bytes(raw[4:6],'big')<<16
  elif raw[3]==0:
   start=upper+int.from_bytes(raw[1:3],'big');image[start:start+raw[0]]=raw[4:-1]
 codes=[int.from_bytes(image[i:i+2],'little')for i in range(address,address+row['rows']*row['cols']*2,2)]
 # Use original source photograph URLs, preserved in Git, only as visual references.
 try:old=subprocess.check_output(['git','show',a.reference_revision+':keyboards/xwhatsit/ibm/'+row['board']+'/universal/readme.md'],cwd=root,text=True,stderr=subprocess.DEVNULL)
 except subprocess.CalledProcessError:old=''
 photos=re.findall(r'!\[[^]]*\]\((https?://[^)]+)\)',old)
 cases.append({**row,'definition':definition,'qmk_layouts':info['layouts'],'keymap_layout':used,'codes':codes,'photo_urls':photos})
(a.output/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
print('Prepared',len(cases),'offline definitions and compiled default keymaps.')
