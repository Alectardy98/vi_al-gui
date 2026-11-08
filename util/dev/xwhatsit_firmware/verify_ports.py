#!/usr/bin/env python3
"""Verify each new IBM Vial image, its layout payload and boot boundary."""
import argparse,json,re,lzma,subprocess,hashlib,tempfile
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('qmk_root',type=Path);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();root=args.qmk_root.resolve();base=root/'keyboards/xwhatsit/vial'
results=[]
for row in json.loads((base/'ports.json').read_text()):
 name=row['target'].replace('/', '_').replace(':','_');elf=root/'.build'/(name+'.elf');hexfile=root/(name+'.hex')
 assert elf.exists()and hexfile.exists(),row['board']
 size=subprocess.check_output(['avr-size',str(elf)],text=True).splitlines()[1].split();flash=int(size[0])+int(size[1]);ram=int(size[1])+int(size[2]);assert flash<=28672 and ram<2560
 address=0;addresses=[];image=bytearray([255])*32768
 for line in hexfile.read_text().splitlines():
  raw=bytes.fromhex(line[1:]);assert sum(raw)%256==0
  count,kind=raw[0],raw[3]
  if kind==4:address=int.from_bytes(raw[4:6],'big')<<16
  elif kind==2:address=int.from_bytes(raw[4:6],'big')<<4
  elif kind==0:
   start=address+int.from_bytes(raw[1:3],'big');addresses.extend(range(start,start+count));image[start:start+count]=raw[4:4+count]
 assert max(addresses)<0x7000,(row['board'],hex(max(addresses)))
 assert bytes.fromhex(row['uid'])in image,row['board']
 with tempfile.TemporaryDirectory(prefix='xwhatsit-image-')as temporary:
  binary=Path(temporary)/'firmware.bin'
  subprocess.run(['avr-objcopy','-O','binary',str(elf),str(binary)],check=True)
  assert bytes(image[:max(addresses)+1])==binary.read_bytes(), 'HEX differs from ELF: '+row['board']
 header=(root/'.build'/('obj_'+name)/'src/vial_generated_keyboard_definition.h').read_text()
 compressed=bytes(int(s,16)for s in re.findall(r'0x([0-9A-Fa-f]{2})',header))
 definition=json.loads(lzma.decompress(compressed))
 assert definition==json.loads((base/row['board']/'keymaps/vial/vial.json').read_text())
 assert definition['matrix']==dict(rows=row['rows'],cols=row['cols'])
 coords=[]
 for line in definition['layouts']['keymap']:
  for key in line:
   if isinstance(key,str):
    r,c=map(int,key.split(',')[:2]);assert 0<=r<row['rows'] and 0<=c<row['cols'];coords.append((r,c))
 assert len(coords)==len(set(coords))
 info=json.loads((base/row['board']/'universal/keyboard.json').read_text())
 source={(k['matrix'][0],k['matrix'][1])for k in info['layouts'][row['layout']]['layout']}
 assert set(coords)==source
 results.append({**row,'flash_bytes':flash,'flash_free':28672-flash,'static_ram_bytes':ram,'layout_keys':len(coords),'hex_sha256':hashlib.sha256(hexfile.read_bytes()).hexdigest()})
args.output.write_text(json.dumps(results,indent=2)+'\n')
print('PASS:',len(results),'ELF/HEX identity, UIDs, boot boundaries, compiled XZ layouts and matrix coordinates')
