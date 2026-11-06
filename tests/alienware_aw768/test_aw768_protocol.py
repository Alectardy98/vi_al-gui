# SPDX-License-Identifier: GPL-2.0-or-later
"""Golden vendor reports and actual legacy readback; no hardware access."""
import json
from dataclasses import replace
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src/main/python'))
from vi_al_addons.alienware_aw768.protocol import (Lighting, ProtocolError, parse_snapshot, parse_status,
                            selector, named_batch, lighting_save_batch, GROUPS)

FIXTURE = Path(__file__).parent/'fixtures/legacy-lighting.json'
def baseline():
    d = json.loads(FIXTURE.read_text())
    return parse_snapshot(d['profile'], [bytes.fromhex(s) for s in d['frames']])

class CodecTests(unittest.TestCase):
    def test_known_read_selectors_and_closed_command_allowlist(self):
        self.assertEqual(selector(0x85, 1), bytes((0, 0x85, 1)) + bytes(62))
        self.assertEqual(selector(0x88), bytes((0, 0x88)) + bytes(63))
        for cmd in (0x12, 0x8, 0x9, -1, 0x100):
            with self.assertRaises(ProtocolError): selector(cmd, 1)
        for profile in (0, 4, True, -1):
            with self.assertRaises(ProtocolError): selector(5, profile)
    def test_status_uses_active_profile_at_vendor_offset(self):
        self.assertEqual(parse_status(bytes.fromhex('008800010100020000')+bytes(56)), 1)
        for r in (b'', bytes(65), bytes((0, 0x88))+bytes(63)):
            with self.assertRaises(ProtocolError): parse_status(r)
    def test_actual_legacy_readback_and_speed_conversion(self):
        s = baseline()
        self.assertEqual(s.variant, 'legacy-readback')
        self.assertEqual(s.named_settings[2], Lighting(0, (209,255,0), (0,0,0),3,10))
        self.assertEqual(len(s.records),30)
    def test_v0039_layout_uses_reported_channel_and_uninverted_speed(self):
        s = baseline(); frames = [bytearray(r.raw) for r in s.records]
        channels = (1,2)+(1,)*6+(2,)*6+(1,)*8+(2,)*8
        for raw, channel in zip(frames, channels): raw[12:14] = bytes((channel, 1))
        v = parse_snapshot(1, frames)
        self.assertEqual(v.variant, 'v0039-readback')
        self.assertEqual(v.named_settings[2].tempo, 0)
    def test_reject_incomplete_reordered_wrong_profile_or_trailing_data(self):
        frames=[r.raw for r in baseline().records]
        cases=[frames[:-1],list(reversed(frames))]
        for offset,val in ((0,0),(1,2),(14,2),(20,1),(12,9),(9,9)):
            altered=[bytearray(r) for r in frames];altered[14][offset]=val;cases.append(altered)
        for f in cases:
            with self.assertRaises(ProtocolError): parse_snapshot(1,f)
    def test_vendor_golden_set_packet_and_complete_eight_group_sequence(self):
        p = named_batch(baseline(), {2:Lighting(0,(0,128,255),(0,0,0),2,8)})
        self.assertEqual(len(p),8)
        self.assertEqual(p[0], bytes.fromhex('000501000080ff00000002080001010002')+bytes(48))
        self.assertEqual([int.from_bytes(x[15:17],'big') for x in p],[m for m,_ in GROUPS])
        self.assertTrue(all(len(x)==65 and x[11]==8 for x in p))
        self.assertEqual(p[-1][15:17],bytes.fromhex('004d'))
    def test_complete_save_matches_original_dll_red_packets_byte_for_byte(self):
        golden=json.loads((FIXTURE.parent/'vendor-two-pass-red.json').read_text())
        for scheme in ('groups','all'):
            state=baseline()
            changes={r.mask:Lighting(0,(255,0,0),(0,0,0),2,10)
                     for r in state.records_for(scheme)}
            packets=lighting_save_batch(state,changes,scheme)
            self.assertEqual([p.hex() for p in packets],golden[scheme])
            self.assertEqual([p[13] for p in packets],[1]*(len(packets)//2)+[2]*(len(packets)//2))

    def test_unchanged_colors_effects_and_speed_retained(self):
        s = baseline();p=named_batch(s,{2:Lighting()})
        for record,packet in zip(s.records[15:22],p[1:]):
            self.assertEqual(packet[3:10],record.raw[2:9])
            self.assertEqual(packet[10],3-record.raw[9])
    def test_bounds_and_unknown_group_rejected(self):
        for setting in (Lighting(mode=5),Lighting(tempo=4),Lighting(brightness=0),
                        Lighting(brightness=11),Lighting(color0=(256,0,0)),Lighting(color0=(True,0,0))):
            with self.assertRaises(ProtocolError):named_batch(baseline(),{2:setting})
        for changes in ({},{0xffff:Lighting()},{2:Lighting(brightness=8),16:Lighting(brightness=9)}):
            with self.assertRaises(ProtocolError):named_batch(baseline(),changes)
    def test_effects_use_autonomous_channel_without_keypress_timeout(self):
        for mode,color_mode in ((0,1),(1,1),(2,1),(3,2),(4,3)):
            p=named_batch(baseline(),{2:Lighting(mode=mode)})[0]
            self.assertEqual(p[12:15],bytes((0,1,color_mode)))

if __name__=='__main__':unittest.main()
