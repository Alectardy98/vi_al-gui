# SPDX-License-Identifier: GPL-3.0-or-later
import sys,struct,unittest
from pathlib import Path
from . import test_leyden_editor as g
from .test_leyden_protocol import p,Hid,keyboard
class Persistent(Hid):
 def __init__(self):
  super().__init__();self.version=(0,10,0);self.offset=10;self.saved=False;self.drop=False
 def write(self,data):
  op,cmd=bytes(data)[1:3];body=bytes(data)[5:];answer=bytearray(28)
  if cmd not in (p.CALIBRATION_CAPS,p.CALIBRATION_PREFERENCE,p.CALIBRATION_DEFAULTS):return super().write(data)
  self.sent.append(bytes(data))
  if self.failure=='short-write':return 20
  if cmd==p.CALIBRATION_CAPS:answer[:3]=bytes((1,3,16))
  elif cmd==p.CALIBRATION_PREFERENCE:
   if op==p.SET and not self.drop:self.offset=struct.unpack_from('<h',body)[0];self.threshold=410+self.offset;self.saved=True
   if op==p.GET:struct.pack_into('<HhhB',answer,0,0,self.offset,10,self.saved)
  elif cmd==p.CALIBRATION_DEFAULTS:self.offset=10;self.saved=False;self.threshold=420
  self.queue.append(struct.pack('<BBH',op,cmd,p.MAGIC)+answer);return 33
class ProtocolTests(unittest.TestCase):
 def make(self):
  k=keyboard();k.dev=Persistent();return k,p.Client(k).connect()
 def test_read_only_connect_and_persistent_roundtrip(self):
  k,c=self.make();self.assertTrue(c.has_persistence);self.assertTrue(all(x[1]==p.GET for x in k.dev.sent))
  self.assertEqual(c.set_threshold(0,430),430);self.assertEqual(c.offsets,[20]);self.assertEqual(c.saved,[True])
  again=p.Client(k).connect();self.assertEqual(again.offsets,[20]);self.assertTrue(again.saved[0])
  self.assertEqual(c.restore_defaults(),[420]);self.assertFalse(c.saved[0])
 def test_failed_save_not_reported_as_success(self):
  k,c=self.make();k.dev.drop=True
  with self.assertRaises(p.ProtocolError):c.set_threshold(0,430)
  self.assertEqual(c.thresholds,[420])
 def test_invalid_offset_no_write(self):
  k,c=self.make();n=len(k.dev.sent)
  for value in (0,409,410):
   with self.assertRaises(p.ProtocolError):c.set_threshold(0,value)
  self.assertEqual(len(k.dev.sent),n)
 def test_legacy_stays_temporary(self):
  k=keyboard();c=p.Client(k).connect();self.assertFalse(c.has_persistence)
  with self.assertRaises(p.ProtocolError):c.restore_defaults()
class GuiTests(g.GuiTests):
 def setUp(self):
  super().setUp();self.k.dev=Persistent()
 def test_persistent_controls_and_unsent_edits(self):
  self.connect();c=self.c;self.assertTrue(c.restore_calibration.isEnabled());self.assertEqual(c.apply_threshold.text(),'Apply and save')
  before=[x for x in self.k.dev.sent if x[1]==p.SET and x[2] in (p.CALIBRATION_PREFERENCE,p.CALIBRATION_DEFAULTS)]
  c.threshold.setValue(430);g.app.processEvents()
  after=[x for x in self.k.dev.sent if x[1]==p.SET and x[2] in (p.CALIBRATION_PREFERENCE,p.CALIBRATION_DEFAULTS)]
  self.assertEqual(before,after);c.apply_threshold.click();self.wait();self.assertTrue(c.client.saved[0]);self.assertIn('saved to EEPROM',c.statuses[0].text())
  c.submit('restore_defaults');self.wait();self.assertFalse(c.client.saved[0]);self.assertEqual(c.threshold.value(),420)
 # Parent protocol rejection and manual RAM-only assertions exercise older firmware.
 def test_readback_preview_threshold_and_sampling(self):
  self.connect();self.c.threshold.setValue(430);self.c.apply_threshold.click();self.wait();self.assertEqual(self.c.client.thresholds,[430])
if __name__=='__main__':unittest.main(verbosity=2)
