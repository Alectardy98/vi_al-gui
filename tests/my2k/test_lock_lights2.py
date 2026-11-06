# SPDX-License-Identifier: GPL-2.0-or-later
"""Current GUI settings validation; no external firmware/C-library dependency."""
import unittest
from vi_al_addons.my2k.lock_lights2_protocol import defaults,encode_rules,decode_rules,TRIGGERS

class Codec(unittest.TestCase):
    def test_defaults_and_independent_items(self):
        values = defaults()
        self.assertEqual(decode_rules(encode_rules(**values)), values)
        for i in range(5):
            values['fixed'][i] = dict(enabled=bool(i % 2), effect=i, speed=i+1, color=(i*20, 70, 90))
        self.assertEqual(decode_rules(encode_rules(**values)), values)
        self.assertNotIn('Active layer', TRIGGERS)
        self.assertEqual(TRIGGERS[4:], ('Layer 1', 'Layer 2', 'Layer 3'))

    def test_rules_limits_crc_and_reserved(self):
        values = defaults()
        values['rules'] = [dict(enabled=True, trigger=4, layer=i % 3+1, effect=i % 5, speed=i, color=(10, 30, 50)) for i in range(8)]
        raw = encode_rules(**values)
        self.assertEqual(decode_rules(raw), values)
        for at in range(128):
            bad = bytearray(raw)
            bad[at] ^= 1
            with self.assertRaises(ValueError):
                decode_rules(bad)
        for layer in (0, 4):
            values['rules'][0]['layer'] = layer
            with self.assertRaises(ValueError):
                encode_rules(**values)
