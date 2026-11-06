# SPDX-License-Identifier: GPL-2.0-or-later
"""Current GUI settings validation; no external firmware/C-library dependency."""
import unittest
from vi_al_addons.my2k.touch_bar_protocol import defaults,encode,decode,valid_key
from vi_al_addons.my2k.touch_bar import key_filter
from keycodes.keycodes import Keycode

class Codec(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(decode(encode(**defaults())), defaults())
        self.assertEqual((defaults()['left'], defaults()['right'], defaults()['tap']), (0xaa, 0xa9, 0xa8))
        self.assertEqual(defaults()['mode'], 0)
    def test_crc_reserved_limits(self):
        raw = encode(**defaults())
        for i in range(16):
            bad = bytearray(raw); bad[i] ^= 1
            with self.assertRaises(ValueError): decode(bad)
        for field, values in [('sensitivity', (0, 101, True)), ('mode', (-1, 2, True)), ('tap_jitter', (-1, 101, True)), ('left', (1, 3, -1, 0x7c03, 0x5001, 65536))]:
            for v in values:
                data = defaults(); data[field] = v
                with self.assertRaises(ValueError): encode(**data)
        for key in (0, 4, 0xe1, 0xaa, 0xcd, 0x204, 0x1fff & 0x1f04):
            self.assertTrue(valid_key(key))
    def test_filter(self):
        Keycode.protocol = 6
        self.assertTrue(key_filter('KC_VOLD'))
        self.assertTrue(key_filter('KC_A'))
        self.assertTrue(key_filter('LSFT(KC_A)'))
        self.assertFalse(key_filter('EE_CLR'))
        self.assertFalse(key_filter('MO(1)'))
