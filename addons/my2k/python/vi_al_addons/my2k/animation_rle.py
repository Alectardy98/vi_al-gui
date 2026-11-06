# SPDX-License-Identifier: GPL-2.0-or-later
"""Lossless, bounded transport encoding; stored CRS pixels remain unchanged."""
def encode_python(raw):
 if len(raw)&1:return raw
 words=memoryview(raw).cast('H');out=bytearray();i=0;count=len(words)
 while i<count:
  run=1
  while run<128 and i+run<count and words[i+run]==words[i]:run+=1
  if run>=3:out.append(128|run-1);out+=raw[2*i:2*i+2];i+=run;continue
  start=i;i+=run
  while i<count and i-start<128:
   run=1
   while run<3 and i+run<count and words[i+run]==words[i]:run+=1
   if run>=3:break
   i+=min(run,128-(i-start))
  out.append(i-start-1);out+=raw[start*2:i*2]
 return bytes(out)

# Optional local accelerator; no network lookup or dependency installation.
# Identical opaque-byte encoding, bounded to the negotiated4KiB chunks.
_native=None
try:
 import ctypes
 from pathlib import Path
 import sys
 _suffix = '.dll' if sys.platform == 'win32' else '.dylib' if sys.platform == 'darwin' else '.so'
 _library=ctypes.CDLL(str(Path(__file__).with_name('_animation_rle'+_suffix)))
 _native=_library.my2k_rle565_encode
 _native.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
 _native.restype=ctypes.c_size_t
except (OSError,AttributeError):
 pass

def encode(raw):
 if _native is None or not raw or len(raw)&1 or len(raw)>4096:return encode_python(raw)
 raw=bytes(raw);out=ctypes.create_string_buffer(len(raw)+(len(raw)+255)//256)
 n=_native(raw,len(raw),out,len(out))
 if not n:raise RuntimeError('Bounded animation encoder failed; no transfer sent.')
 return out.raw[:n]
