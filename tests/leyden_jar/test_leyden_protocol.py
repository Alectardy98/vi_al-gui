# SPDX-License-Identifier: GPL-3.0-or-later
import sys, json, struct, unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src/main/python'),str(ROOT/'addons/leyden_jar/python')]
from vi_al_addons.leyden_jar import protocol as p
PROFILES=json.loads((ROOT/'addons/leyden_jar/python/vi_al_addons/leyden_jar/profiles.json').read_text())
PROFILE=next(x for x in PROFILES if x['rows']==8 and x['cols']==16)
class Hid:
 def __init__(self):
  self.sent=[];self.queue=[];self.enabled=True;self.threshold=420;self.technology=0;self.version=(0,9,1);self.failure=None
 def write(self,data):
  self.sent.append(data);op,cmd,magic=struct.unpack_from('<BBH',data,1);assert len(data)==33 and data[0]==0 and magic==p.MAGIC
  payload=data[5:];number=struct.unpack_from('<H',payload)[0];answer=bytearray(payload)
  if self.failure=='short-write':return 20
  if op==p.GET:
   if cmd==p.VERSION:answer[:4]=struct.pack('<BBH',*self.version)
   elif cmd==p.DETAILS:answer[:6]=bytes((8,16,8,18,self.technology,1))
   elif cmd==p.MAPPING:answer[:27]=bytes([1]+list(range(16))+[255,255]+list(range(8)))
   elif cmd==p.ENABLE:answer[0]=self.enabled
   elif cmd in (p.THRESHOLD,p.REFERENCE):answer[2:4]=struct.pack('<H',self.threshold if cmd==p.THRESHOLD else 410)
   elif cmd==p.BINS:answer[2:10]=bytes([0]*8) if number<16 else bytes([255]*8)
   elif cmd==p.LOGICAL_ROW:answer[4:8]=struct.pack('<I',1 if number==2 else 0)
   elif cmd==p.PHYSICAL_VALUES:
    answer[:18]=bytes((255 if self.technology else 0 for _ in range(18)));answer[0]=251 if self.technology else 4
   elif cmd==p.LEVELS:answer[2:18]=struct.pack('<8H',*range(410,418))
   elif cmd==p.SIDE:answer[0]=1
  elif cmd==p.THRESHOLD:self.threshold=number
  elif cmd==p.ENABLE:self.enabled=bool(payload[0])
  elif cmd in (p.BOOT,p.REBOOT,p.ERASE):return 33
  response=struct.pack('<BBH',255 if self.failure=='reject' else op,cmd,magic)+answer
  if self.failure=='short':response=response[:15]
  if self.failure=='stale':self.queue.append(bytes(32))
  if self.failure!='timeout':self.queue.append(response)
  return 33
 def read(self,n,timeout_ms=0):return self.queue.pop(0) if self.queue else b''
def keyboard():return SimpleNamespace(keyboard_id=bytes.fromhex(PROFILE['uid']),rows=8,cols=16,dev=Hid())
class ProtocolTests(unittest.TestCase):
 def test_native_connect_is_read_only(self):
  k=keyboard();c=p.Client(k).connect();self.assertEqual(c.version,(0,9,1));self.assertEqual(c.thresholds,[420]);self.assertTrue(all(x[1]==p.GET for x in k.dev.sent))
 def test_readback_and_bounds(self):
  k=keyboard();c=p.Client(k).connect();self.assertEqual(c.set_threshold(0,433),433);self.assertFalse(c.set_enabled(False));before=len(k.dev.sent)
  for args in [(1,400),(0,1024),(0,-1)]:
   with self.assertRaises(p.ProtocolError):c.set_threshold(*args)
  self.assertEqual(len(k.dev.sent),before)
 def test_logical_physical_polarity_and_unused_pads(self):
  for technology in (0,1):
   k=keyboard();k.dev.technology=technology;c=p.Client(k).connect();logical,physical=c.keypresses();self.assertEqual(logical,{(2,0)});self.assertEqual(physical,{(2,0)});self.assertEqual(c.physical_position((2,0)),(2,0));self.assertIsNone(c.physical_position((8,0)))
 def test_levels_and_extrema_are_ram_only(self):
  k=keyboard();c=p.Client(k).connect();self.assertEqual(c.levels()[0,0],410);self.assertEqual(c.minimum[0,0],410);self.assertNotIn((0,17),c.minimum);c.reset_extrema();self.assertEqual(c.minimum,{})
 def test_stable_extrema_need_three_samples_on_same_side(self):
  c=p.Client(keyboard()).connect();c.levels();c.levels();self.assertEqual(c.stable_low,{})
  c.levels();self.assertEqual(c.stable_low[0,0],410);self.assertEqual(c.stable_high,{})
  c.set_threshold(0,400);self.assertEqual(c.stable_low,{});c.levels();c.levels();c.levels();self.assertEqual(c.stable_high[0,0],410)
 def test_invalid_payload_and_short_details(self):
  k=keyboard();c=p.Client(k);before=len(k.dev.sent)
  with self.assertRaises(p.ProtocolError):c.exchange(p.SET,p.THRESHOLD,bytes(29))
  with self.assertRaises(p.ProtocolError):p.Details.decode(bytes(3))
  self.assertEqual(before,len(k.dev.sent))
 def test_mismatched_threshold_readback_rejected(self):
  class Ignore(Hid):
   def write(self,data):
    old=self.threshold;result=super().write(data)
    if data[1:3]==bytes((p.SET,p.THRESHOLD)):self.threshold=old
    return result
  k=keyboard();k.dev=Ignore();c=p.Client(k).connect()
  with self.assertRaises(p.ProtocolError):c.set_threshold(0,440)
  self.assertEqual(c.thresholds,[420])
 def test_physical_snapshot_uses_two_existing_commands(self):
  k=keyboard();c=p.Client(k).connect();before=len(k.dev.sent);self.assertEqual(c.physical_keypresses(),{(2,0)});self.assertEqual([b[2] for b in k.dev.sent[before:]],[p.SCAN_PHYSICAL,p.PHYSICAL_VALUES])
 def test_reset_commands_do_not_wait_or_retry(self):
  for method,cmd in [('reboot',p.REBOOT),('enter_bootloader',p.BOOT),('erase_eeprom',p.ERASE)]:
   k=keyboard();c=p.Client(k).connect();before=len(k.dev.sent);getattr(c,method)();self.assertEqual(len(k.dev.sent),before+1);self.assertEqual(k.dev.sent[-1][2],cmd)
 def test_rejection_short_timeout_and_write_are_not_retried(self):
  for fault in ['reject','short','timeout','short-write']:
   k=keyboard();c=p.Client(k).connect();k.dev.failure=fault;before=len(k.dev.sent)
   with self.assertRaises(p.ProtocolError):c.set_threshold(0,460)
   self.assertEqual(len(k.dev.sent),before+1)
 def test_stale_reply_ignored(self):
  k=keyboard();k.dev.failure='stale';self.assertEqual(p.Client(k).connect().thresholds,[420])
 def test_identity_and_dimensions_gated(self):
  k=keyboard();k.keyboard_id=b'\0'*8
  with self.assertRaises(p.ProtocolError):p.Client(k)
  k=keyboard();k.rows=7
  with self.assertRaises(p.ProtocolError):p.Client(k)
 def test_split_protocol(self):
  k=keyboard();k.dev.version=(1,0,0);self.assertEqual(p.Client(k).connect().side,'left')
 def test_details_reject_unsupported_matrix(self):
  for data in [bytes((9,16,8,18,0,1)),bytes((8,16,8,18,0,0)),bytes((8,16,8,24,0,1))]:
   with self.assertRaises(p.ProtocolError):p.Details.decode(data)
class DescriptorTests(unittest.TestCase):
 def test_direct_switch_stays_outside_capacitive_rows(self):
  d=p.Details.decode(bytes((9,13,8,16,0,1,1,8,12,27)),direct_supported=True)
  self.assertEqual(d.direct_key,(8,12,27));self.assertFalse(d.expanded_columns)
 def test_expanded_scanner_descriptor_preserves_wire_compatibility(self):
  raw=bytearray(28);raw[:7]=bytes((4,20,4,20,1,2,2));raw[10:15]=bytes((31,32,4,4,7))
  d=p.Details.decode(raw,direct_supported=True,expanded_supported=True)
  self.assertTrue(d.expanded_columns);self.assertEqual(d.physical_rows,4);self.assertEqual(d.physical_cols,20)
  with self.assertRaises(p.ProtocolError):p.Details.decode(raw,direct_supported=True)
 def test_unknown_or_malformed_expanded_scanner_rejected(self):
  raw=bytearray(28);raw[:7]=bytes((4,20,4,20,1,2,2));raw[10:12]=bytes((31,33))
  with self.assertRaises(p.ProtocolError):p.Details.decode(raw,direct_supported=True,expanded_supported=True)
if __name__=='__main__':unittest.main(verbosity=2)
