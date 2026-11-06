import os,sys,struct,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from vi_al_addons.my2k.nes_library_protocol import decode,encode_name,GbcLibraryClient
from vi_al_addons.my2k.gaming import Gaming
from PyQt5.QtWidgets import QApplication,QWidget
from keycodes.keycodes import Keycode
from test_gaming import Device

def catalogue(selected=False):
 d=bytearray(128);d[:8]=b'GRL1'+bytes((1,24,1,0));struct.pack_into('<IIIHBB',d,16,2097152,2097152,32768,3,0,selected);d[32:41]=b'Game.gbc\0';return bytes(d)
class Files:
 def __init__(self,*args):self.fast=type('F',(),{'gbc_library':True,'close':lambda s:None})();self.saved=False;self.calls=[]
 def capabilities(self):pass
 def request(self,op,**kwargs):
  self.calls.append((op,kwargs))
  if op==14:self.saved=True;return bytes(32)+b'GRS1'+bytes(4)
  return bytes(32)+catalogue(self.saved)
class GbcDevice(Device):
 def __init__(self):super().__init__();self.keys[3]=self.keys[1][:]
 def write(self,b):
  n=super().write(b)
  if b[3]==0:self.reply[28]=31
  return n
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance()or QApplication([]);Keycode.protocol=6
 def test_encoding_and_version_gate(self):
  self.assertEqual(encode_name('A.gb',True),b'A.gb\0')
  self.assertEqual(encode_name('Game.GBC',True),b'Game.GBC\0')
  for name in ('Game.nes','../A.gb','a'*92+'.gbc','A\0.gb'):
   with self.assertRaises(ValueError):encode_name(name,True)
  rows,_=decode(catalogue(),True);self.assertEqual(rows[0]['mapper'],3);self.assertEqual(rows[0]['chr'],32768)
  with self.assertRaises(ValueError):decode(catalogue())
  with patch('vi_al_addons.my2k.nes_library_protocol.AnimationFilesClient',Files):
   c=GbcLibraryClient(object());c.catalogue();self.assertEqual(c.files.calls[0][0],13)
   rows,_=c.select('Game.gbc');self.assertTrue(rows[0]['selected']);self.assertEqual([x[0]for x in c.files.calls],[13,14,13])
 def test_old_AUX_refused_before_command(self):
  f=Files();f.fast.gbc_library=False
  with patch('vi_al_addons.my2k.nes_library_protocol.AnimationFilesClient',return_value=f),self.assertRaises(ValueError):GbcLibraryClient(object())
  self.assertEqual(f.calls,[])
 def test_Qt_page_order_independent_controls_and_persistence_ack(self):
  d=GbcDevice();root=QWidget();ui=Gaming(None);root.setLayout(ui);ui.keyboard=type('K',(),{'dev':d})();ui.activate()
  try:
   self.assertTrue(ui.pages.isTabEnabled(1));self.assertEqual([ui.pages.tabText(i)for i in range(3)],['NES','Game Boy Color','Doom'])
   before={g:k[:]for g,k in d.keys.items()};ui.keys[3][0].set_keycode('KC_Q');ui.apply_live()
   self.assertEqual(d.keys[3][0],20);self.assertEqual(d.keys[1],before[1]);self.assertEqual(d.keys[2],before[2]);self.assertIn('Saved',ui.status.text())
   ui.defaults(3);ui.apply_live();self.assertEqual(d.keys[3],before[3])
  finally:ui.deactivate();root.close();self.app.processEvents()
 def test_old_Main_disables_GBC_only(self):
  root=QWidget();ui=Gaming(None);root.setLayout(ui);ui.keyboard=type('K',(),{'dev':Device()})();ui.activate()
  try:
   self.assertFalse(ui.pages.isTabEnabled(1));self.assertTrue(ui.pages.isTabEnabled(0));self.assertTrue(ui.pages.isTabEnabled(2))
  finally:ui.deactivate();root.close();self.app.processEvents()
