# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from vi_al_addons.alienware_aw768.client import Client
from vi_al_addons.alienware_aw768.protocol import Lighting, ProtocolError, MASK_ORDER

class FakeBackend:
    def __init__(self):
        d=json.loads((Path(__file__).parent/'fixtures/legacy-lighting.json').read_text())
        self.frames=[bytearray.fromhex(r) for r in d['frames']]
        self.persisted=[bytes(r) for r in self.frames]
        self.queue=[];self.commands=[];self.writes=[];self.closed=0
        self.short=False;self.short_feature=False;self.timeout=False;self.profile=1
        self.corrupt=False;self.profile_queries=0;self.change_profile=False
    def enumerate(self):return []
    def device(self):return self
    def open_path(self,path):assert path==b'/dev/native'
    def close(self):self.closed+=1
    def send_feature_report(self,p):
        self.commands.append(p[1]);
        if self.short_feature:return 64
        if p[1]==0x85 and not self.timeout:self.queue=[bytes(r) for r in self.frames]
        return 65
    def get_feature_report(self,report_id,length):
        self.profile_queries+=1
        profile=2 if self.change_profile and self.profile_queries>=2 else self.profile
        return bytes((0,0x88,0,profile))+bytes(61)
    def read(self,length,timeout_ms=0):return list(self.queue.pop(0)) if self.queue else []
    def write(self,p):
        self.writes.append(p)
        if self.short:return 64
        mask=int.from_bytes(p[15:17],'big')
        indices=[i for i,m in enumerate(MASK_ORDER) if m==mask]
        r=self.frames[indices[p[13]-1]]
        r[2:11]=p[3:12];r[9]=3-p[10]
        if self.corrupt:r[3]^=0xff
        if p[13]==2 and mask in (0xffff,0x1080,0x004d):
            self.persisted=[bytes(r) for r in self.frames]
        return 65

class ClientTests(unittest.TestCase):
    def setUp(self):
        self.b=FakeBackend();self.clock=0
        def now():self.clock+=.01;return self.clock
        self.pair_calls=0
        def pair(*args):self.pair_calls+=1;return SimpleNamespace(path=b'/dev/native')
        self.c=Client({},b'',backend=self.b,resolver=pair,sleep=lambda _:None,monotonic=now)
    def test_load_only_uses_read_selectors_and_closes_handle(self):
        s=self.c.load();self.assertEqual(s.profile,1)
        self.assertEqual(self.b.commands,[0x88,0x85,0x8D,0x86]);self.assertEqual(self.b.writes,[])
        self.assertEqual(self.b.closed,1)
    def test_apply_reads_before_and_after_both_ordered_passes(self):
        s=self.c.apply({2:Lighting(3,(1,2,3),(4,5,6),2,8)})
        self.assertEqual(s.named_settings[2],Lighting(3,(1,2,3),(4,5,6),2,8))
        self.assertEqual(len(self.b.writes),16)
        self.assertEqual(self.b.commands.count(5),16)
        self.assertEqual(self.b.closed,1)
    def test_live_only_batch_does_not_survive_model_reconnect_but_full_save_does(self):
        from vi_al_addons.alienware_aw768.protocol import lighting_batch
        before=self.c.load()
        for p in lighting_batch(before,{2:Lighting(color0=(7,8,9))}):self.b.write(p)
        self.assertNotEqual([bytes(r) for r in self.b.frames],self.b.persisted)
        self.b.frames=[bytearray(r) for r in self.b.persisted]
        after=self.c.apply({2:Lighting(color0=(7,8,9))})
        self.b.frames=[bytearray(r) for r in self.b.persisted]
        self.assertEqual(self.c.load().named_settings,after.named_settings)
        self.assertEqual([p[13] for p in self.b.writes[-16:]],[1]*8+[2]*8)
        self.assertTrue(all(p[3]==0xff for p in self.b.writes[-8:]))

    def test_partial_second_pass_stops_without_retry_or_claiming_commit(self):
        persisted=list(self.b.persisted);original=self.b.write
        def fail_second(p):
            if len(self.b.writes)==8:
                self.b.writes.append(p);return 64
            return original(p)
        self.b.write=fail_second
        with self.assertRaisesRegex(ProtocolError,'Short native lighting output'):
            self.c.apply({2:Lighting(color0=(7,8,9))})
        self.assertEqual(len(self.b.writes),9)
        self.assertEqual(self.b.persisted,persisted)
        self.assertEqual(self.b.closed,1)

    def test_second_client_can_update_saved_morph_without_hidden_cache(self):
        self.c.apply({2:Lighting(mode=3)})
        self.c._known=None # no cache is consulted
        self.c.apply({16:Lighting(mode=2)})
        self.assertEqual(self.c.load().named_settings[2].mode,3)
    def test_short_write_fails_once_closes_without_retry(self):
        self.b.short=True
        with self.assertRaisesRegex(ProtocolError,'Short native lighting output'):self.c.apply({2:Lighting()})
        self.assertEqual(len(self.b.writes),1);self.assertEqual(self.b.closed,1)
    def test_short_feature_never_sends_lighting_output(self):
        self.b.short_feature=True
        with self.assertRaises(ProtocolError):self.c.apply({2:Lighting()})
        self.assertEqual(self.b.writes,[]);self.assertEqual(self.b.closed,1)
    def test_timeout_is_bounded_and_does_not_write(self):
        self.b.timeout=True
        with self.assertRaisesRegex(ProtocolError,'timed out'):self.c.apply({2:Lighting()})
        self.assertEqual(self.b.writes,[]);self.assertLess(self.clock,4)
    def test_profile_change_rejected_before_first_output(self):
        self.b.change_profile=True
        with self.assertRaisesRegex(ProtocolError,'profile changed'):self.c.apply({2:Lighting()})
        self.assertEqual(self.b.writes,[])
    def test_mismatch_does_not_claim_success_or_rewrite(self):
        self.b.corrupt=True
        with self.assertRaisesRegex(ProtocolError,'readback does not match'):self.c.apply({2:Lighting()})
        self.assertEqual(len(self.b.writes),16);self.assertEqual(self.b.closed,1)
    def test_topology_rechecked_for_each_operation(self):
        self.c.load();self.c.load();self.assertEqual(self.pair_calls,2)
    def test_unsupported_12_zone_probe_is_cached_and_never_sends_0d(self):
        self.c.load();self.c.load()
        self.assertEqual(self.b.commands.count(0x8D),1)
        with self.assertRaisesRegex(ProtocolError,'did not provide 12-zone'):
            self.c.apply({2:Lighting()},'fine')
        self.assertEqual(self.b.writes,[])
        self.assertNotIn(0x0D,self.b.commands)
    def test_six_zone_and_global_commands_use_their_own_records(self):
        self.c.apply({0x2103:Lighting(color0=(10,20,30))},'zones')
        self.assertEqual(len(self.b.writes),12)
        self.assertEqual(int.from_bytes(self.b.writes[-1][15:17],'big'),0x1080)
        self.b.writes=[]
        self.c.apply({0xffff:Lighting(mode=10)},'all')
        self.assertEqual(len(self.b.writes),2)
        self.assertEqual(self.b.writes[0][3],10)
    def test_pairing_failure_does_not_open_device(self):
        def fail(*args):raise RuntimeError('different hub')
        self.c.resolver=fail
        with self.assertRaisesRegex(RuntimeError,'different hub'):self.c.load()
        self.assertEqual(self.b.commands,[]);self.assertEqual(self.b.closed,0)

if __name__=='__main__':unittest.main()
