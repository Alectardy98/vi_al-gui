# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit maintenance mounting through the OS API; simulated devices only."""
import unittest
from pathlib import Path
from unittest.mock import patch

class MaintenanceTests(unittest.TestCase):
    def test_mount_is_explicit_and_uses_discovered_partition(self):
        from vi_al_addons.my2k.animation_maintenance import mount_maintenance
        with patch('vi_al_addons.my2k.animation_maintenance.available_mounts',side_effect=[[],[Path('/mock/MY2K')]]),patch('vi_al_addons.my2k.animation_maintenance.asset_partitions',return_value=[Path('/dev/actual-partition')]),patch('vi_al_addons.my2k.animation_maintenance.filesystem_ready',return_value=True),patch('vi_al_addons.my2k.animation_maintenance.AnimationFilesClient')as client,patch('vi_al_addons.my2k.animation_maintenance.mount_partition')as run:
            self.assertEqual(mount_maintenance(object()),'/mock/MY2K');client.return_value.maintenance.assert_called_once_with()
            run.assert_called_once_with(Path('/dev/actual-partition'))
    def test_partition_waits_for_filesystem_without_mount_retry(self):
        from vi_al_addons.my2k.animation_maintenance import mount_maintenance
        now=[0]
        def sleep(n):now[0]+=n
        with patch('vi_al_addons.my2k.animation_maintenance.available_mounts',side_effect=[[],[Path('/mock/MY2K')]]),patch('vi_al_addons.my2k.animation_maintenance.asset_partitions',return_value=[Path('/dev/actual-partition')]),patch('vi_al_addons.my2k.animation_maintenance.filesystem_ready',side_effect=[False,False,True])as ready,patch('vi_al_addons.my2k.animation_maintenance.AnimationFilesClient')as client,patch('vi_al_addons.my2k.animation_maintenance.mount_partition')as run:
            self.assertEqual(mount_maintenance(object(),clock=lambda:now[0],sleep=sleep),'/mock/MY2K')
            self.assertEqual(ready.call_count,3);self.assertEqual(now[0],.5)
            client.return_value.maintenance.assert_called_once_with();self.assertEqual(run.call_count,1)
    def test_filesystem_probe_requires_real_vfat_interface(self):
        from vi_al_addons.my2k.system_storage import filesystem_ready
        for values,wanted in [(['ext4'],False),(['vfat'],True),([],False)]:
            with patch('vi_al_addons.my2k.system_storage._call',return_value=values)as call:
                self.assertEqual(filesystem_ready(Path('/dev/mock')),wanted)
                self.assertEqual(call.call_count,2 if wanted else 1)
        with patch('vi_al_addons.my2k.system_storage._call',side_effect=[['vfat'],RuntimeError('No Filesystem interface')]):
            self.assertFalse(filesystem_ready(Path('/dev/mock')))
    def test_native_mount_uses_dbus_once_and_validates_reply(self):
        from vi_al_addons.my2k.system_storage import mount_partition,FILESYSTEM
        with patch('vi_al_addons.my2k.system_storage.filesystem_ready',return_value=True),patch('vi_al_addons.my2k.system_storage._call',return_value=['/media/MY2K'])as call:
            self.assertEqual(mount_partition(Path('/dev/mock')),'/media/MY2K')
            call.assert_called_once_with(Path('/dev/mock'),FILESYSTEM,'Mount',({},),timeout=30000)
        with patch('vi_al_addons.my2k.system_storage.filesystem_ready',return_value=False),patch('vi_al_addons.my2k.system_storage._call')as call:
            with self.assertRaises(RuntimeError):mount_partition(Path('/dev/mock'))
            call.assert_not_called()
    def test_existing_mount_does_not_reset_or_remount(self):
        from vi_al_addons.my2k.animation_maintenance import mount_maintenance
        with patch('vi_al_addons.my2k.animation_maintenance.available_mounts',return_value=[Path('/mock/MY2K')]),patch('vi_al_addons.my2k.animation_maintenance.AnimationFilesClient')as client,patch('vi_al_addons.my2k.animation_maintenance.mount_partition')as run:
            self.assertEqual(mount_maintenance(object()),'/mock/MY2K');client.assert_not_called();run.assert_not_called()
    def test_zero_or_multiple_devices_never_mount(self):
        from vi_al_addons.my2k.animation_maintenance import mount_maintenance
        with patch('vi_al_addons.my2k.animation_maintenance.available_mounts',return_value=[]),patch('vi_al_addons.my2k.animation_maintenance.AnimationFilesClient'),patch('vi_al_addons.my2k.animation_maintenance.asset_partitions',return_value=[Path('/dev/a'),Path('/dev/b')]),patch('vi_al_addons.my2k.animation_maintenance.mount_partition')as run:
            with self.assertRaises(RuntimeError):mount_maintenance(object())
            run.assert_not_called()
