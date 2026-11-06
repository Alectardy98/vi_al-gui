from pathlib import Path
import sys,random,unittest,ctypes
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src/main/python'))
from vi_al_addons.my2k import animation_rle as codec
class NativeEncoder(unittest.TestCase):
 @unittest.skipIf(codec._native is None,'Optional local encoder unavailable')
 def test_exact_python_encoding_and_guard_bytes(self):
  rng=random.Random(0x133)
  for i in range(2000):
   n=2*rng.randrange(1,2049);raw=bytearray()
   while len(raw)<n:raw+=rng.randbytes(2)*rng.randrange(1,180)
   raw=bytes(raw[:n]);out=ctypes.create_string_buffer(b'\xa5'*4160);size=codec._native(raw,n,out,4112);self.assertEqual(out.raw[:size],codec.encode_python(raw));self.assertEqual(out.raw[4112:4160],b'\xa5'*48)
   self.assertEqual(codec.encode(raw),codec.encode_python(raw))
 @unittest.skipIf(codec._native is None,'Optional local encoder unavailable')
 def test_invalid_native_sizes_do_not_write(self):
  for n in[0,1,3,4097,4098]:
   out=ctypes.create_string_buffer(b'\xa5'*4200);self.assertEqual(codec._native(bytes(4200),n,out,4112),0);self.assertEqual(out.raw[:4200],b'\xa5'*4200)
  out=ctypes.create_string_buffer(b'\xa5'*4200);self.assertEqual(codec._native(bytes(4096),4096,out,4096),0);self.assertEqual(out.raw[:4200],b'\xa5'*4200)
 def test_fallback_and_odd_input_unchanged(self):
  from unittest.mock import patch
  for raw in[b'',b'x',bytes(4098)]:self.assertEqual(codec.encode(raw),codec.encode_python(raw))
  with patch.object(codec,'_native',None):self.assertEqual(codec.encode(b'\x12\x34'*200),codec.encode_python(b'\x12\x34'*200))
if __name__=='__main__':unittest.main()
