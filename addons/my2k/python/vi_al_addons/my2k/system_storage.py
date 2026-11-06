# SPDX-License-Identifier: GPL-2.0-or-later
"""Use the desktop's storage API directly; no findmnt/udisksctl executable."""
from pathlib import Path

SERVICE = 'org.freedesktop.UDisks2'
BLOCK = SERVICE + '.Block'
FILESYSTEM = SERVICE + '.Filesystem'


def _node(partition):
    path = Path(partition)
    if path.parent != Path('/dev') or not path.name:
        raise ValueError('Expected a discovered /dev partition.')
    # UDisks encodes every non-ASCII-alphanumeric byte as _xx.
    suffix = ''.join(chr(c) if chr(c).isascii() and chr(c).isalnum()
                     else f'_{c:02x}' for c in path.name.encode())
    return '/org/freedesktop/UDisks2/block_devices/' + suffix


def _call(partition, interface, method, arguments=(), timeout=5000):
    from PyQt5.QtDBus import QDBusConnection, QDBusMessage, QDBus
    bus = QDBusConnection.systemBus()
    if not bus.isConnected():
        raise RuntimeError('The operating system storage service is unavailable.')
    message = QDBusMessage.createMethodCall(SERVICE, _node(partition), interface, method)
    message.setArguments(list(arguments))
    reply = bus.call(message, QDBus.Block, timeout)
    if reply.type() == QDBusMessage.ErrorMessage:
        raise RuntimeError(reply.errorMessage() or reply.errorName())
    return reply.arguments()


def filesystem_ready(partition):
    from PyQt5.QtDBus import QDBusVariant
    try:
        values = _call(partition, 'org.freedesktop.DBus.Properties', 'Get', (BLOCK, 'IdType'))
        value = values[0] if values else None
        if isinstance(value, QDBusVariant):
            value = value.variant()
        if value != 'vfat':
            return False
        # Existence of an IdType string alone does not prove a Filesystem interface.
        _call(partition, 'org.freedesktop.DBus.Properties', 'Get', (FILESYSTEM, 'MountPoints'))
        return True
    except RuntimeError:
        return False


def mount_partition(partition):
    if not filesystem_ready(partition):
        raise RuntimeError('The MY-2K FAT filesystem is not ready; no mount was requested.')
    values = _call(partition, FILESYSTEM, 'Mount', ({},), timeout=30000)
    if len(values) != 1 or not isinstance(values[0], str) or not values[0].startswith('/'):
        raise RuntimeError('The system returned no valid mount path.')
    return values[0]
