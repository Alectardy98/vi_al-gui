# SPDX-License-Identifier: GPL-2.0-or-later
"""Current GUI settings validation; no external firmware/C-library dependency."""
import unittest
from vi_al_addons.my2k.sleep_mode_protocol import encode,decode

class Codec(unittest.TestCase):
 def test_valid(self):
  for enabled in (False,True):
   for minutes in (5,15,60,120):self.assertEqual(decode(encode(enabled,minutes)),dict(enabled=enabled,minutes=minutes))
 def test_invalid(self):
  for minutes in (0,4,121,65535,True,5.5):
   with self.assertRaises(ValueError):encode(True,minutes)
  for enabled in (0,1,'yes'):
   with self.assertRaises(ValueError):encode(enabled,15)
  for i in range(16):
   r=bytearray(encode(True,5));r[i]^=1
   with self.assertRaises(ValueError):decode(r)
