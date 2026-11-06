# SPDX-License-Identifier: GPL-2.0-or-later
"""Pure identity/topology checks; never opens a HID handle or writes hardware."""
import sys
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src/main/python'))
from vi_al_addons.alienware_aw768.identity import (Companion, PairingError, UsbLocation, VIAL_UIDS,
                            is_supported_keyboard, linux_usb_location, resolve_companion)


def descriptor(path, native=False, **changes):
    result = dict(path=path, vendor_id=0x04F2 if native else 0x7281,
                  product_id=0x1666 if native else 0x0092,
                  interface_number=2 if native else 1,
                  usage_page=0xFF00 if native else 0xFF60,
                  usage=1 if native else 0x61,
                  serial_number='000000000000' if native else 'vial:f64c2b3c')
    return dict(result, **changes)


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.selected = descriptor(b'/dev/hidraw11')
        self.native = descriptor(b'/dev/hidraw8', native=True)
        self.uid = bytes.fromhex('2945ce03248c2c0c')
        self.locations = {
            '/dev/hidraw11': UsbLocation('/sys/usb1/1-4.3', '/sys/usb1/1-4', 0x7281, 0x0092, 1),
            '/dev/hidraw8': UsbLocation('/sys/usb1/1-4.2', '/sys/usb1/1-4', 0x04F2, 0x1666, 2),
        }
        self.calls = []
    def locate(self, path):
        self.calls.append(path)
        return self.locations[path]
    def pair(self, candidates=None):
        return resolve_companion(self.selected, self.uid,
                                 [self.native] if candidates is None else candidates,
                                 locate_usb=self.locate)
    def test_exact_known_pair_returns_detached_descriptor(self):
        result = self.pair()
        self.assertIsInstance(result, Companion)
        self.assertEqual(result.path, b'/dev/hidraw8')
        self.assertIsNot(result.descriptor, self.native)
        self.assertEqual(result.selected_location.hub, result.lighting_location.hub)
    def test_both_source_uids_and_little_endian_integer_are_supported(self):
        for uid in VIAL_UIDS:
            for value in (uid, int.from_bytes(uid, 'little')):
                self.uid = value
                self.assertEqual(self.pair().path, b'/dev/hidraw8')
    def test_tab_visibility_gate_needs_no_companion_or_topology(self):
        self.assertTrue(is_supported_keyboard(self.selected, self.uid))
        self.assertFalse(is_supported_keyboard(self.native, self.uid))
        self.assertFalse(is_supported_keyboard(None, self.uid))
        self.assertFalse(is_supported_keyboard(self.selected, 'bad uid'))
        self.assertEqual(self.calls, [])
    def test_wrong_selected_identity_is_rejected_before_topology_reads(self):
        for key, value in (('vendor_id', 0x04F2), ('product_id', 0x1666),
                           ('interface_number', 0), ('usage_page', 0xFF00), ('usage', 1)):
            with self.subTest(key=key):
                selected = dict(self.selected, **{key: value})
                with self.assertRaises(PairingError):
                    resolve_companion(selected, self.uid, [self.native], locate_usb=self.locate)
        self.assertEqual(self.calls, [])
    def test_unknown_or_malformed_uid_is_rejected_before_topology_reads(self):
        for uid in (bytes(8), b'bad', '2945ce03248c2c0c', -1, True):
            with self.subTest(uid=uid), self.assertRaises(PairingError):
                resolve_companion(self.selected, uid, [self.native], locate_usb=self.locate)
        self.assertEqual(self.calls, [])
    def test_native_keyboard_consumer_dfu_and_wrong_usage_are_not_candidates(self):
        rows = [dict(self.native, interface_number=number) for number in (0, 1, 3)]
        rows += [dict(self.native, usage_page=0xFF60, usage=0x61),
                 dict(self.native, product_id=0x1665)]
        with self.assertRaisesRegex(PairingError, 'No original'):
            self.pair(rows)
        self.assertEqual(self.calls, ['/dev/hidraw11'])
    def test_shared_host_root_is_not_a_shared_immediate_hub(self):
        self.locations['/dev/hidraw8'] = replace(self.locations['/dev/hidraw8'],
                                                hub='/sys/usb1/1-5')
        with self.assertRaisesRegex(PairingError, 'No original'):
            self.pair()
    def test_root_hub_pairing_is_rejected(self):
        for path, location in list(self.locations.items()):
            self.locations[path] = replace(location, hub='/sys/usb1')
        with self.assertRaisesRegex(PairingError, 'internal USB hub'):
            self.pair()
    def test_absent_and_multiple_matches_fail_closed(self):
        with self.assertRaisesRegex(PairingError, 'No original'):
            self.pair([])
        other = descriptor('/dev/hidraw18', native=True)
        self.locations['/dev/hidraw18'] = replace(self.locations['/dev/hidraw8'],
                                                 usb_device='/sys/usb1/1-4.4')
        with self.assertRaisesRegex(PairingError, 'Multiple'):
            self.pair([self.native, other])
    def test_duplicate_rows_of_one_hid_path_count_once(self):
        result = self.pair([self.native, dict(self.native, path='/dev/hidraw8')])
        self.assertEqual(result.path, b'/dev/hidraw8')
        self.assertEqual(self.calls.count('/dev/hidraw8'), 1)
    def test_zero_serial_is_not_used_to_pair_different_hubs(self):
        self.locations['/dev/hidraw8'] = replace(self.locations['/dev/hidraw8'], hub='/sys/usb1/1-5')
        with self.assertRaises(PairingError):
            self.pair()
    def test_sysfs_and_enumeration_identity_must_agree(self):
        for path in ('/dev/hidraw11', '/dev/hidraw8'):
            original = self.locations[path]
            for changes in (dict(vendor_id=0), dict(interface_number=0), dict(interface_class=0xFE)):
                with self.subTest(path=path, changes=changes):
                    self.locations[path] = replace(original, **changes)
                    with self.assertRaisesRegex(PairingError, 'disagree'):
                        self.pair()
            self.locations[path] = original
    def test_missing_path_is_not_accepted(self):
        self.native['path'] = b''
        with self.assertRaisesRegex(PairingError, 'Missing HID'):
            self.pair()


class LinuxTopologyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.hub = self.root/'devices'/'usb1'/'1-4'
        self.usb = self.hub/'1-4.3'
        self.interface = self.usb/'1-4.3:1.1'
        hid = self.interface/'0003:7281:0092.000C'
        node = hid/'hidraw'/'hidraw11'
        node.mkdir(parents=True)
        (node/'device').symlink_to(hid)
        self.sysfs = self.root/'class'/'hidraw'
        self.sysfs.mkdir(parents=True)
        (self.sysfs/'hidraw11').symlink_to(node)
        for p, name, value in ((self.hub, 'idVendor', '214b'), (self.hub, 'bDeviceClass', '09'),
                                (self.usb, 'idVendor', '7281'), (self.usb, 'idProduct', '0092'),
                                (self.interface, 'bInterfaceNumber', '01'),
                                (self.interface, 'bInterfaceClass', '03')):
            (p/name).write_text(value+'\n')
    def tearDown(self): self.temp.cleanup()
    def resolve(self, path='/dev/hidraw11'):
        return linux_usb_location(path, sys_class_hidraw=self.sysfs)
    def test_symlinks_resolve_to_exact_usb_node_and_parent(self):
        result = self.resolve(b'/dev/hidraw11')
        self.assertEqual(result, UsbLocation(str(self.usb), str(self.hub), 0x7281, 0x0092, 1))
    def test_missing_or_non_hidraw_path_fails(self):
        for path in ('/dev/hidraw12', 'hidraw11', '/tmp/hidraw11', '/dev/hidraw11\0'):
            with self.subTest(path=path), self.assertRaises(PairingError): self.resolve(path)
    def test_non_hub_parent_is_not_guessed(self):
        (self.hub/'bDeviceClass').write_text('00\n')
        with self.assertRaisesRegex(PairingError, 'internal USB hub'): self.resolve()
    def test_unreadable_or_malformed_topology_fails(self):
        (self.interface/'bInterfaceNumber').write_text('bad-hex\n')
        with self.assertRaises(PairingError): self.resolve()


if __name__ == '__main__': unittest.main()
