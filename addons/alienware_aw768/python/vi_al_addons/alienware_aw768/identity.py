# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the custom AW768 Vial keyboard to its original lighting PCB.

The RP2040 and original PCB are different USB devices. A matching product name
or the original PCB's all-zero serial is not sufficient to pair them. On Linux
we require exact interface identities and the same immediate, non-root USB hub.
This module enumerates no devices, opens no HID handles and sends no commands.
"""
from dataclasses import dataclass
from collections.abc import Mapping
import os
from pathlib import Path
import re


VIAL_USB_ID = (0x7281, 0x0092)
LIGHTING_USB_ID = (0x04F2, 0x1666)
# From keyboards/alectardy98_mcuswap/alienware/keymaps/{vial,vial_alec}/config.h.
VIAL_UIDS = frozenset((bytes.fromhex('2945ce03248c2c0c'),
                      bytes.fromhex('a9ea250d225daaab')))


class PairingError(RuntimeError):
    """An unambiguous, physically related lighting interface was not proven."""


@dataclass(frozen=True)
class UsbLocation:
    usb_device: str
    hub: str
    vendor_id: int
    product_id: int
    interface_number: int
    interface_class: int = 0x03


@dataclass(frozen=True)
class Companion:
    descriptor: dict
    selected_location: UsbLocation
    lighting_location: UsbLocation

    @property
    def path(self):
        return self.descriptor['path']


def _path(value):
    if not isinstance(value, (str, bytes)) or not value:
        raise PairingError('Missing HID interface path; refresh devices.')
    return os.fsdecode(value)


def _interface_matches(desc, usb_id, interface, usage_page, usage):
    if not isinstance(desc, Mapping):
        return False
    expected = dict(vendor_id=usb_id[0], product_id=usb_id[1],
                    interface_number=interface, usage_page=usage_page, usage=usage)
    return all(type(desc.get(key)) is int and desc[key] == value
               for key, value in expected.items())


def _uid_bytes(uid):
    if type(uid) is int and 0 <= uid < 1 << 64:
        return uid.to_bytes(8, 'little')
    if isinstance(uid, (bytes, bytearray)) and len(uid) == 8:
        return bytes(uid)
    raise PairingError('Invalid AW768 Vial keyboard identity.')


def is_supported_keyboard(descriptor, vial_uid):
    """Pure tab-visibility gate; native companion absence does not hide the tab."""
    try:
        return (_interface_matches(descriptor, VIAL_USB_ID, 1, 0xFF60, 0x61) and
                _uid_bytes(vial_uid) in VIAL_UIDS)
    except PairingError:
        return False


def linux_usb_location(hid_path, *, sys_class_hidraw=Path('/sys/class/hidraw')):
    """Resolve a HIDAPI hidraw path through sysfs, without opening the device.

    The sysfs root is injectable for tests. The returned node/hub paths are
    canonical paths, not string prefixes or host-controller approximations.
    """
    path = _path(hid_path)
    if not re.fullmatch(r'/dev/hidraw[0-9]+', path):
        raise PairingError('AW768 companion pairing requires a Linux hidraw path.')
    try:
        hid = (Path(sys_class_hidraw)/Path(path).name/'device').resolve(strict=True)
        interface = next((p for p in (hid, *hid.parents)
                          if (p/'bInterfaceNumber').is_file()), None)
        if interface is None:
            raise PairingError('Cannot resolve the HID USB interface; refresh devices.')
        device = interface.parent
        hub = device.parent
        if (not (hub/'idVendor').is_file() or
                int((hub/'bDeviceClass').read_text().strip(), 16) != 0x09 or
                re.fullmatch(r'usb[0-9]+', hub.name)):
            raise PairingError('AW768 boards must share an identifiable internal USB hub.')
        def value(p, name):
            return int((p/name).read_text().strip(), 16)
        return UsbLocation(str(device.resolve()), str(hub.resolve()),
                           value(device, 'idVendor'), value(device, 'idProduct'),
                           value(interface, 'bInterfaceNumber'),
                           value(interface, 'bInterfaceClass'))
    except (OSError, ValueError) as error:
        raise PairingError('Cannot verify AW768 USB topology; refresh devices.') from error


def _verify_location(location, usb_id, interface):
    if (not isinstance(location, UsbLocation) or
            (location.vendor_id, location.product_id) != usb_id or
            location.interface_number != interface or location.interface_class != 0x03):
        raise PairingError('HID enumeration and USB interface identity disagree; refresh devices.')
    if not location.usb_device or not location.hub or re.fullmatch(r'usb[0-9]+', Path(location.hub).name):
        raise PairingError('AW768 boards must share an identifiable internal USB hub.')


def native_usb_location(hid_path):
    import sys
    if sys.platform.startswith('linux'):
        return linux_usb_location(hid_path)
    from .native_topology import windows_location, macos_location
    if sys.platform == 'win32':
        return windows_location(_path(hid_path))
    if sys.platform == 'darwin':
        return macos_location(_path(hid_path))
    raise PairingError('This operating system has no native USB topology adapter.')


def resolve_companion(selected_descriptor, vial_uid, enumerated_descriptors, *,
                      locate_usb=None):
    """Return exactly one original lighting interface for a known Vial AW768.

    ``vial_uid`` accepts the keyboard's little-endian integer or eight wire bytes.
    ``locate_usb(path)`` is injectable and must return a verified UsbLocation.
    Duplicate HIDAPI rows for one path count once; distinct matching paths are
    ambiguous. A missing, changed or unresolvable eligible interface fails closed.
    No Vial or lighting protocol query is performed here.
    """
    if not is_supported_keyboard(selected_descriptor, vial_uid):
        raise PairingError('Select the supported RP2040 AW768 Vial keyboard first.')
    locate_usb = locate_usb or native_usb_location
    selected_location = locate_usb(_path(selected_descriptor.get('path')))
    _verify_location(selected_location, VIAL_USB_ID, 1)
    candidates = {}
    for desc in enumerated_descriptors:
        # Excludes native keyboard/consumer interfaces and the DFU interface.
        if not _interface_matches(desc, LIGHTING_USB_ID, 2, 0xFF00, 1):
            continue
        path = _path(desc.get('path'))
        if path in candidates:
            continue
        location = locate_usb(path)
        _verify_location(location, LIGHTING_USB_ID, 2)
        if location.hub == selected_location.hub:
            candidates[path] = (dict(desc), location)
    if not candidates:
        raise PairingError('No original AW768 lighting interface found on this keyboard’s USB hub.')
    if len(candidates) != 1:
        raise PairingError('Multiple AW768 lighting interfaces share this USB hub; pairing is ambiguous.')
    descriptor, location = next(iter(candidates.values()))
    return Companion(descriptor, selected_location, location)
