# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibrated ADC motion cannot masquerade as a firmware press."""
import unittest
from vi_al_addons.ec_42.presentation import held,calibration_color,follow_updated,GRAY,GREEN,BLUE,RED

class ActivityTests(unittest.TestCase):
    def sample(self, **kw):
        return dict(dict(sampled=True,enabled=True,raw=263,baseline=120,bottom=1020,
                         press=839,release=795,active=False,debounced=False,capture=0),**kw)
    def test_recorded_0413_noise_remains_gray_and_does_not_steal_sensor_focus(self):
        # Values from actual 2.9g read-only capture: +143 ADC, still far below 839.
        sample=self.sample()
        self.assertFalse(held(sample));self.assertEqual(calibration_color(sample),GRAY)
        self.assertEqual(follow_updated([sample],set(),0,{0}),(0,set()))
    def test_firmware_active_or_debounced_always_takes_precedence(self):
        for flag in ('active','debounced'):
            sample=self.sample(**{flag:True})
            self.assertTrue(held(sample));self.assertEqual(calibration_color(sample),GREEN)
    def test_manual_capture_uses_existing_press_threshold_when_typing_suppressed(self):
        self.assertFalse(held(self.sample(),capturing=True))
        self.assertFalse(held(self.sample(raw=839),capturing=True))
        sample=self.sample(raw=840)
        self.assertTrue(held(sample,capturing=True))
        self.assertEqual(calibration_color(sample,capturing=True),GREEN)
        self.assertFalse(held(sample)) # Idle honors firmware flags, not raw travel.
    def test_capture_and_retry_colors_not_hidden_by_idle_noise(self):
        self.assertEqual(calibration_color(self.sample(capture=1)),BLUE)
        self.assertEqual(calibration_color(self.sample(capture=2)),RED)
    def test_disabled_capture_and_unsampled_keys_remain_supported(self):
        self.assertTrue(held(self.sample(enabled=False,raw=900)))
        self.assertFalse(held(self.sample(enabled=False,raw=125)))
        self.assertFalse(held(self.sample(sampled=False,active=True)))

if __name__=='__main__':unittest.main()
