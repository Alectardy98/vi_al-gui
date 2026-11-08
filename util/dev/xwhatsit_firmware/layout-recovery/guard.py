import os
from pathlib import Path
from PyQt5 import QtCore
import hidraw
root=Path(os.environ['COMPARE_OUT']);root.mkdir(parents=True,exist_ok=True)
Original=QtCore.QSettings
class Settings(Original):
 def __init__(self,*a,**kw):
  if a==('Vi_al','Vi_al'):super().__init__(str(root/'preferences.ini'),Original.IniFormat)
  else:super().__init__(*a,**kw)
QtCore.QSettings=Settings
original_enumerate=hidraw.enumerate
hidraw.enumerate=lambda *a,**kw:[d for d in original_enumerate(*a,**kw) if d.get('product_string') in ('IBM Model F AT','EC Pro X ANSI/ISO - Alectardy98')]

# Test-only evidence: list xwhatsit opcodes; assert the capture sends no saves.
import atexit,json
original_device=hidraw.device
commands=[]
class Device:
 def __init__(self):self.handle=original_device()
 def __getattr__(self,name):return getattr(self.handle,name)
 def write(self,data):
  if len(data)>=4 and bytes(data[1:3])==b'\x55\xaa':
   opcode=data[3]
   assert opcode in (0x11,0x1a,0x30,0x31,0x16,0x15,0x19),hex(opcode)
   if opcode==0x19:assert data[6]==1, 'A long signal measurement was requested'
   commands.append(opcode)
  return self.handle.write(data)
hidraw.device=Device
atexit.register(lambda:(root/'hid-commands.json').write_text(json.dumps(commands)))
import builtins
from protocol.keyboard_comm import Keyboard
builtins.vi_al_fault={'mode':'always','corruptions':0}
original_packet=Keyboard.layout_packet
def packet(self,message):
 data=original_packet(self,message)
 state=builtins.vi_al_fault
 if message[:2]==b'\xfe\x02' and int.from_bytes(message[2:6],'little')==0 and state['mode']!='off':
  state['corruptions']+=1
  if state['mode']=='once':state['mode']='off'
  return bytes([data[0]^255])+bytes(data[1:])
 return data
Keyboard.layout_packet=packet
