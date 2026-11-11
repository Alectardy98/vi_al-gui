# SPDX-License-Identifier: GPL-3.0-or-later
import os,sys,json,time,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from .test_leyden_protocol import ROOT,keyboard,Hid
from types import SimpleNamespace
from PyQt5.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QTabWidget,QComboBox,QPushButton
from PyQt5.QtCore import QObject,pyqtSignal,Qt
from vi_al_addons.leyden_jar.provider import LeydenJarSession
from kle_serial import Serial
app=QApplication.instance() or QApplication([])
class Layout(QObject):
 changed=pyqtSignal()
 def get_choice(self,index):return 0
class Lock:
 def __init__(self):self.n=0
 def _lock(self):self.n+=1
 def _unlock(self):self.n-=1;assert self.n>=0
class Window(QMainWindow):
 def __init__(self):
  super().__init__();self.layout_editor=Layout();self.autorefresh=Lock();self.combobox_devices=QComboBox();self.btn_refresh_devices=QPushButton();self.tabs=QTabWidget();self.setCentralWidget(self.tabs)
class GuiTests(unittest.TestCase):
 def setUp(self):
  self.w=Window();self.s=LeydenJarSession(self.w,None);self.c=self.s.controller
  self.k=keyboard();self.k.name='Synthetic Leyden Jar firmware emulator';self.k.vial_protocol=6
  data=json.loads((Path(__file__).parent/'fixtures/fat-vial.json').read_text())
  keys=Serial().deserialize(data['layouts']['keymap']).keys
  for k in keys:
   k.row,k.col=map(int,k.labels[0].split(','));k.layout_index=k.layout_option=-1
   if k.labels[8]:k.layout_index,k.layout_option=map(int,k.labels[8].split(','))
  self.k.keys=keys;self.k.encoders=[]
  self.device=SimpleNamespace(keyboard=self.k)
  for spec in self.s.pages:
   page=QWidget();page.setLayout(spec.editor);self.w.tabs.addTab(page,spec.title);spec.editor.rebuild(self.device)
  self.w.resize(1100,760);self.w.show();app.processEvents()
 def wait(self):
  deadline=time.monotonic()+3
  while self.c.worker and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
  self.c.timer.stop();self.assertIsNone(self.c.worker)
 def tearDown(self):
  self.c.deactivate();self.wait();self.assertTrue(self.s.before_close());self.w.close();app.processEvents()
 def connect(self):
  self.c.activate('calibration');self.wait();self.assertIsNotNone(self.c.client)
 def test_construct_bind_resize_and_render_without_hid(self):
  self.assertEqual(self.k.dev.sent,[])
  for width,height in [(900,650),(1500,1000)]:
   self.w.resize(width,height)
   for index in range(self.w.tabs.count()):self.w.tabs.setCurrentIndex(index);app.processEvents();self.assertFalse(self.w.grab().isNull())
  self.assertEqual(self.k.dev.sent,[])
 def test_readback_preview_threshold_and_sampling(self):
  self.connect();self.assertTrue(self.c.general.valid());self.assertEqual(self.c.bins.rowCount(),1)
  self.c.threshold.setValue(450);app.processEvents();self.assertTrue(all(x[1]==2 for x in self.k.dev.sent))
  self.c.submit('set_threshold',0,450);self.wait();self.assertEqual(self.c.client.thresholds,[450])
  self.c.submit('levels');self.wait();self.assertEqual(self.c.values[0,0],410);self.assertGreater(len(self.c.previews['calibration'].widgets),80)
  self.assertEqual(self.w.autorefresh.n,0)
 def test_fault_is_reported_and_stops_polling(self):
  self.connect();self.k.dev.failure='reject';self.c.submit('keys');self.wait();self.assertIsNone(self.c.client);self.assertFalse(self.c.timer.isActive());self.assertIn('rejected',self.c.statuses[0].text())
 def test_leaving_page_stops_sampling(self):
  self.connect();self.c.deactivate();app.processEvents();self.assertFalse(self.c.timer.isActive())
if __name__=='__main__':unittest.main(verbosity=2)
