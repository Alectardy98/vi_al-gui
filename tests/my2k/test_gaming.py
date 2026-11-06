import os,struct,sys,unittest
from unittest.mock import patch
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from vi_al_addons.my2k.gaming_protocol import GamingClient,encode,valid_key
from vi_al_addons.my2k.gaming import Gaming,key_filter
from PyQt5.QtWidgets import QApplication,QWidget
from PyQt5.QtTest import QTest
from PyQt5.QtCore import Qt,QPoint
from keycodes.keycodes import Keycode

class Device:
 def __init__(self):self.keys={1:[29,27,229,40,82,81,80,79],2:[29,27,229,40,26,22,4,7]};self.rev=1;self.writes=[];self.bad=False;self.active=0;self.wanted=0;self.pending=False
 def write(self,b):
  self.writes.append(bytes(b));q=b[1:];assert len(q)==32
  op,g=q[2],q[4];r=bytearray(32);r[:5]=bytes((253,230,170,1,op))
  if op==0:r[5]=1;r[6]=self.active;r[25]=self.wanted;r[8:12]=b'GME1';r[28]=15
  elif op in (5,6):
   r[5]=g
   if op==6:
    assert struct.unpack_from('<I',q,5)[0]==self.rev
    self.keys[g]=list(struct.unpack_from('<8H',q,9));self.rev+=1
   r[8:24]=encode(self.keys[g]);struct.pack_into('<I',r,24,self.rev);r[28]=self.pending
  self.reply=r;return 33
 def read(self,*args,**kwargs):return b'' if self.bad else self.reply

class GamingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance()or QApplication([]);Keycode.protocol=6
 def setUp(self):self.dev=Device();self.keyboard=type('K',(),{'dev':self.dev})();self.client=GamingClient(self.keyboard);self.roots=[]
 def tearDown(self):
  for root,ui in self.roots:
   ui.timer.stop();ui.poll_timer.stop()
   for keys in ui.keys.values():
    for key in keys:key.deleteLater()
   root.close();root.deleteLater()
  self.app.processEvents()
 def page(self):
  root=QWidget();ui=Gaming(None);root.setLayout(ui);ui.keyboard=self.keyboard;ui.activate();self.roots.append((root,ui));return ui
 def test_key_validation(self):
  for v in (0,4,0x73,0x87,0xa4,0xe1):self.assertTrue(valid_key(v))
  for v in (True,-1,1,0x74,0xaa,0x204,0x7e0f):self.assertFalse(valid_key(v))
  with self.assertRaises(ValueError):encode([4]*7)
  self.assertTrue(key_filter('KC_A'));self.assertFalse(key_filter('MO(1)'));self.assertFalse(key_filter('LSFT(KC_A)'))
 def test_read_has_no_mutations(self):
  ui=self.page();self.assertEqual(ui.pages.count(),3);self.assertEqual([ui.pages.tabText(i)for i in range(3)],['NES','Game Boy Color','Doom']);self.assertTrue(all(b[3]in(0,5)for b in self.dev.writes));self.assertFalse(ui.dirty)
 def test_rom_combobox_edit_does_not_write(self):
  ui=self.page();before=len(self.dev.writes)
  rows=[dict(name='One.nes',size=40976,mapper=0,error=0,selected=True,status='Supported'),dict(name='Two.nes',size=262160,mapper=2,error=0,selected=False,status='Supported')]
  ui.show_roms(rows,False);ui.roms.setCurrentIndex(1)
  self.assertEqual(len(self.dev.writes),before);self.assertTrue(ui.rom_use.isEnabled());self.assertFalse(ui.dirty)
  rows[1]['name']='Very long name '*6+'.nes';ui.show_roms(rows,False);self.assertLess(ui.roms.minimumSizeHint().width(),350)
 def test_live_independent_profiles_ack_readback(self):
  ui=self.page();before=self.dev.keys[2][:];ui.keys[1][0].set_keycode('KC_Q');ui.apply_live();self.assertEqual(self.dev.keys[1][0],20);self.assertEqual(self.dev.keys[2],before);self.assertIn('Saved',ui.status.text());self.assertEqual(self.dev.writes[-2][3],6);self.assertEqual(self.dev.writes[-1][3],5)
 def test_both_dirty_saves_in_revision_order(self):
  ui=self.page();ui.keys[1][0].set_keycode('KC_Q');ui.keys[2][0].set_keycode('KC_E');ui.apply_live();self.assertEqual(self.dev.rev,3);self.assertEqual((self.dev.keys[1][0],self.dev.keys[2][0]),(20,8))
 def test_transport_not_retried(self):
  self.dev.bad=True
  with self.assertRaises(RuntimeError):self.client.capabilities()
  n=len(self.dev.writes)
  with self.assertRaises(RuntimeError):self.client.read(1)
  self.assertEqual(len(self.dev.writes),n)
 def test_no_edits_while_game_active(self):
  self.dev.active=2;ui=self.page();self.assertFalse(ui.pages.isEnabled());self.assertTrue(all(b[3]!=6 for b in self.dev.writes))
 def test_pending_save_not_false_success(self):
  self.dev.pending=True;ui=self.page();ui.keys[1][0].set_keycode('KC_Q');ui.apply_live();self.assertIn('saving',ui.status.text());self.dev.pending=False;ui.poll();self.assertIn('Saved',ui.status.text())
 def test_picker_directly_below_defaults_and_not_global_tray(self):
  ui=self.page()
  for game,index in ((1,0),(3,1),(2,2)):
   page=ui.pages.widget(index).widget();layout=page.layout();index=layout.indexOf(ui.default_buttons[game])
   self.assertIs(layout.itemAt(index+1).widget(),ui.pickers[game])
  key=ui.keys[1][0]
  with patch('tabbed_keycodes.TabbedKeycodes.open_tray',side_effect=AssertionError('Global tray opened')):
   QTest.mouseClick(key,Qt.LeftButton,pos=QPoint(25,25))
  self.assertIs(ui.targets[1],key);self.assertTrue(ui.pickers[1].isEnabled())
  before=len(self.dev.writes);ui.pickers[1].keycode_changed.emit('KC_Q');self.assertEqual(key.keycode,'KC_Q')
  self.assertEqual(len(self.dev.writes),before);ui.apply_live();self.assertEqual(self.dev.keys[1][0],20)
  self.assertEqual(self.dev.keys[2][0],29)
 def test_switch_page_clears_local_selection(self):
  ui=self.page();ui.select_control(1,ui.keys[1][0]);ui.pages.setCurrentIndex(1)
  self.assertIsNone(ui.targets[1]);self.assertFalse(ui.pickers[1].isEnabled())
  ui.pickers[1].keycode_changed.emit('KC_Q');self.assertFalse(ui.dirty)
 def test_mismatched_readback_stops(self):
  self.client.capabilities();keys,rev,_=self.client.read(1)
  old=self.dev.read
  def bad(*a,**kw):
   r=bytearray(old(*a,**kw))
   if r[4]==5:r[8]=5
   return r
  self.dev.read=bad
  with self.assertRaises(RuntimeError):self.client.apply(1,keys,rev)
  self.assertTrue(self.client.uncertain)
if __name__=='__main__':unittest.main()
