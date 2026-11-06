"""Installer boundaries and the optional core/add-on contract; no USB access."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from addon_runtime.packages import (PackageError, inspect_package, install_package,
                                    read_index, set_enabled)


def package(path, *, version='1.0.0', api=1, extra=None, source=None):
    meta={'id':'example_keyboard','name':'Example keyboard','version':version,'api':api}
    items={'addon.json':json.dumps(meta), 'python/vi_al_addons/example_keyboard/__init__.py':'',
           'python/vi_al_addons/example_keyboard/provider.py':source or
           "from addon_runtime import Addon\nADDON=Addon('example_keyboard')\n"}
    items.update(extra or {})
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,value in items.items():archive.writestr(name,value)
    return path


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=self.root/'installed'
        self.zip=package(self.root/'example.zip')

    def test_inspection_does_not_execute_or_create_state(self):
        marker=self.root/'executed'
        package(self.zip,source=f"open({str(marker)!r},'w').write('oops')\n")
        self.assertEqual(inspect_package(self.zip)['id'],'example_keyboard')
        self.assertFalse(marker.exists());self.assertFalse(self.store.exists())

    def test_install_enable_disable_and_immutable_update(self):
        install_package(self.zip,self.store)
        old=read_index(self.store)['example_keyboard']['directory']
        original=(self.store/'packages'/old/'addon.json').read_bytes()
        set_enabled('example_keyboard',False,self.store)
        self.assertFalse(read_index(self.store)['example_keyboard']['enabled'])
        set_enabled('example_keyboard',True,self.store)
        package(self.zip,version='1.1.0');install_package(self.zip,self.store)
        row=read_index(self.store)['example_keyboard']
        self.assertTrue(row['enabled']);self.assertEqual(row['previous'],old)
        self.assertEqual((self.store/'packages'/old/'addon.json').read_bytes(),original)
        self.assertNotEqual(row['directory'],old)

    def test_failed_activation_preserves_previous_index(self):
        install_package(self.zip,self.store);before=(self.store/'index.json').read_bytes()
        package(self.zip,version='1.1.0')
        with patch('addon_runtime.packages._write_index',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):install_package(self.zip,self.store)
        self.assertEqual((self.store/'index.json').read_bytes(),before)

    def test_validation_failure_never_changes_existing_index(self):
        install_package(self.zip,self.store);before=(self.store/'index.json').read_bytes()
        package(self.zip,api=2)
        with self.assertRaises(PackageError):install_package(self.zip,self.store)
        self.assertEqual((self.store/'index.json').read_bytes(),before)

    def test_traversal_windows_devices_and_foreign_packages_rejected(self):
        for name in ('../escape.py','/tmp/escape','C:/escape','resources/../escape',
                     'resources/CON','resources/file.','resources/file ',
                     'python/vi_al_addons/another/provider.py','python/main_window.py',
                     'resources/a\\b','resources/a\x01b'):
            with self.subTest(name=name):
                package(self.zip,extra={name:'no'})
                with self.assertRaises(PackageError):inspect_package(self.zip)

    def test_symlink_and_case_duplicate_rejected(self):
        for linked in (False,True):
            package(self.zip)
            with zipfile.ZipFile(self.zip,'a') as archive:
                if linked:
                    item=zipfile.ZipInfo('resources/link');item.create_system=3;item.external_attr=0o120777<<16
                    archive.writestr(item,'/tmp/elsewhere')
                else:archive.writestr('ADDON.JSON','{}')
            with self.assertRaises(PackageError):inspect_package(self.zip)

    def test_unknown_api_invalid_json_missing_entry_and_expansion_limits(self):
        for api in (0,2,True,'1'):
            package(self.zip,api=api)
            with self.assertRaises(PackageError):inspect_package(self.zip)
        package(self.zip,extra={'resources/large':'x'*8192})
        with patch('addon_runtime.packages.MAX_BYTES',4096):
            with self.assertRaises(PackageError):inspect_package(self.zip)
        package(self.zip)
        with patch('addon_runtime.packages.MAX_FILES',2):
            with self.assertRaises(PackageError):inspect_package(self.zip)
        self.zip.write_bytes(b'not a ZIP')
        with self.assertRaises(PackageError):inspect_package(self.zip)

    def test_corrupt_index_not_silently_overwritten(self):
        self.store.mkdir();(self.store/'index.json').write_text('{broken')
        with self.assertRaises(PackageError):install_package(self.zip,self.store)
        self.assertEqual((self.store/'index.json').read_text(),'{broken')

    def test_restart_loads_new_package_without_repository_addons(self):
        install_package(self.zip,self.store)
        import os
        env=dict(os.environ,VI_AL_ADDON_DIR=str(self.store),PYTHONPATH=str(Path(__file__).parents[2]/'src/main/python'))
        script="from addon_runtime.loader import installed_addons,load_errors; assert [a.id for a in installed_addons()]==['example_keyboard']; assert not load_errors()"
        subprocess.run([sys.executable,'-c',script],env=env,check=True)
        set_enabled('example_keyboard',False,self.store)
        subprocess.run([sys.executable,'-c',"from addon_runtime.loader import installed_addons; assert installed_addons()==[]"],env=env,check=True)


if __name__=='__main__':unittest.main()
