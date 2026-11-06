# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os,sys
from PyInstaller.utils.hooks import collect_all, collect_submodules
root=Path(SPECPATH).parents[1]
sys.path.insert(0,str(root/"src/main/python"))
usb_data,usb_binaries,usb_hidden=collect_all('libusb_package')
data=[(str(root/'src/main/resources/base'),'.'),
      (str(root/'src/main/icons/Icon.ico'),'.'),
      (str(root/'COPYING'),'.')]
# The frozen application context reads this explicitly named file.
settings=Path(os.environ['VI_AL_BUILD_SETTINGS']);data.append((str(settings),'.'))
if os.environ.get('VI_AL_BUNDLE_ADDONS'):
    data.append((str(root/'dist/addons'),'bundled-addons'))
a=Analysis([str(root/'src/main/python/main.py')],pathex=[str(root/'src/main/python')],
    binaries=usb_binaries,datas=usb_data+data,
    hiddenimports=usb_hidden+collect_submodules('addon_runtime')+collect_submodules('usb.backend')+collect_submodules('keymap')+
      ['backports.tarfile','hid','hidraw' if sys.platform.startswith('linux') else 'hid','argparse','statistics',
       'array','dataclasses','secrets','ctypes','threading','PyQt5.QtSvg','PyQt5.QtNetwork','PyQt5.QtDBus'],
    runtime_hooks=[str(root/'util/packaging/runtime_hook.py')],
    excludes=['vi_al_addons','PyQt5.QtWebEngine','PyQt5.QtWebEngineWidgets'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Vi_al',
        icon=str(root/'src/main/icons/Icon.ico'),debug=False,strip=False,upx=False,
        console=not sys.platform.startswith('win'),contents_directory='.')
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Vi_al')
if sys.platform=='darwin':
    app=BUNDLE(coll,name='Vi_al.app',icon=str(root/'src/main/icons/Icon.icns'),
      bundle_identifier='io.alectardy98.vi-al',info_plist={'CFBundleDisplayName':'Vi_al',
      'NSHighResolutionCapable':True,'NSHumanReadableCopyright':'Vi_al contributors; based on Vial (GPL-2.0-or-later)'})
