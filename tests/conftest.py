"""Test current add-on sources in a temporary profile; never discover USB devices."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/main/python'))
if os.environ.get('VI_AL_TEST_ADDONS','1')=='1':
    profile=tempfile.TemporaryDirectory(prefix='vi-al-tests-')
    packages=Path(profile.name)/'packages'
    subprocess.run([sys.executable,str(ROOT/'util/packaging/build_addons.py'),'--output',str(packages)],
                   check=True,capture_output=True,text=True)
    os.environ['VI_AL_ADDON_DIR']=str(Path(profile.name)/'installed')
    from addon_runtime.packages import install_package
    for package in sorted(packages.glob('*.zip')):
        install_package(package)
    from addon_runtime.loader import installed_addons,load_errors
    installed_addons()
    assert not load_errors(),load_errors()


@pytest.fixture(autouse=True)
def isolated_addon_preferences(monkeypatch,tmp_path):
    if os.environ.get('VI_AL_TEST_ADDONS','1')=='1':
        from PyQt5.QtCore import QSettings
        from vi_al_addons.my2k import aux_display
        monkeypatch.setattr(aux_display,'QSettings',
                            lambda *a,**kw:QSettings(str(tmp_path/'oled.ini'),QSettings.IniFormat))
