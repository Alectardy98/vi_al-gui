import sys,struct,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from vi_al_addons.my2k.nes_library_protocol import decode,encode_name,NesLibraryClient

def catalogue(selected=False,error=0):
    data=bytearray(128);data[:8]=b'NRL1'+bytes((1,24,1,0))
    struct.pack_into('<IIIHBB',data,16,262160,262144,0,2,error,selected)
    data[32:40]=b'Game.nes'
    return bytes(data)

class FakeFiles:
    def __init__(self,*args):self.fast=type('F',(),{'rom_library':True,'close':lambda self:None})();self.calls=[];self.saved=False;self.bad=False
    def capabilities(self):pass
    def request(self,op,**kwargs):
        self.calls.append((op,kwargs))
        if op==12:self.saved=True;return bytes(32)+b'NRS1'+bytes(4)
        return bytes(32)+catalogue(self.saved and not self.bad)

class NesLibraryTests(unittest.TestCase):
    def test_decode_metadata(self):
        rows,truncated=decode(catalogue());self.assertFalse(truncated);self.assertEqual(rows[0]['mapper'],2);self.assertEqual(rows[0]['name'],'Game.nes');self.assertFalse(rows[0]['selected'])
    def test_bad_response(self):
        for raw in (b'',catalogue()[:-1],b'BAD!'+catalogue()[4:]):
            with self.subTest(raw=raw[:8]),self.assertRaises(ValueError):decode(raw)
    def test_name_bounds_and_paths(self):
        self.assertEqual(encode_name('Game.nes'),b'Game.nes\0')
        self.assertEqual(len(encode_name('a'*91+'.nes')),96)
        for name in ('a'*92+'.nes','../Game.nes','A/B.nes','C:Game.nes','A\0.nes','Game.gif'):
            with self.subTest(name=name),self.assertRaises(ValueError):encode_name(name)
    def test_capability_gate_read_only_list_and_verified_selection(self):
        with patch('vi_al_addons.my2k.nes_library_protocol.AnimationFilesClient',FakeFiles):
            c=NesLibraryClient(object());c.catalogue();self.assertEqual([x[0]for x in c.files.calls],[11]);rows,_=c.select('Game.nes');self.assertTrue(rows[0]['selected']);self.assertEqual([x[0]for x in c.files.calls],[11,12,11])
    def test_readback_mismatch_never_replays(self):
        with patch('vi_al_addons.my2k.nes_library_protocol.AnimationFilesClient',FakeFiles):
            c=NesLibraryClient(object());c.files.bad=True
            with self.assertRaises(RuntimeError):c.select('Game.nes')
            self.assertEqual([x[0]for x in c.files.calls],[12,11])
    def test_old_firmware_rejected(self):
        with patch('vi_al_addons.my2k.nes_library_protocol.AnimationFilesClient',FakeFiles):
            old=FakeFiles();old.fast.rom_library=False
            with patch('vi_al_addons.my2k.nes_library_protocol.AnimationFilesClient',return_value=old),self.assertRaises(ValueError):NesLibraryClient(object())
    def test_pagination_and_cursor_validation(self):
        with patch('vi_al_addons.my2k.nes_library_protocol.AnimationFilesClient',FakeFiles):
            c=NesLibraryClient(object());calls=[]
            def request(op,**kwargs):
                calls.append(kwargs.get('offset',0));data=bytearray(catalogue())
                if calls[-1]==0:data[7]=1;struct.pack_into('<I',data,12,24)
                else:data[32:41]=b'Other.nes'
                return bytes(32)+data
            c.files.request=request;rows,truncated=c.catalogue();self.assertEqual(calls,[0,24]);self.assertEqual(len(rows),2);self.assertFalse(truncated)
            def bad_cursor(op,**kwargs):
                data=bytearray(catalogue());data[7]=1
                return bytes(32)+data
            c.files.request=bad_cursor
            with self.assertRaises(RuntimeError):c.catalogue()
