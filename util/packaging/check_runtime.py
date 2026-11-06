"""Packaged, device-free icon/runtime checks, including an empty executable PATH."""
import json,os,sys
from pathlib import Path
from PyQt5.QtGui import QImageReader
from PyQt5.QtCore import QStorageInfo
from PyQt5 import QtSvg,QtNetwork
import hid
import usb.backend.libusb1
import libusb_package
import keyboard

root=Path(os.environ['VI_AL_VALIDATION_DIR']);root.mkdir(parents=True,exist_ok=True)
try:
    assert WINDOW.windowTitle()=='Vi_al 1.0',WINDOW.windowTitle()
    assert APP.applicationDisplayName()=='Vi_al 1.0',APP.applicationDisplayName()
    image=APP.windowIcon().pixmap(256,256).toImage()
    color=image.pixelColor(128,64)
    assert color.blue()>color.red()+30 and color.red()>color.green()+15,color.name()
    assert image.save(str(root/'purple-window-icon.png'))
    formats=[bytes(x).decode()for x in QImageReader.supportedImageFormats()]
    assert {'gif','png','jpeg','webp'}<=set(formats),formats
    backend=usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
    assert backend is not None,'Bundled libusb backend unavailable'
    if sys.platform.startswith('linux'):
        from PyQt5 import QtDBus
        mounts=[]
        if WINDOW.addon_manager.sessions:
            from vi_al_addons.my2k.animation_library_protocol import available_mounts
            mounts=[str(p)for p in available_mounts()]
    elif sys.platform=='win32':
        import ctypes
        cfg=ctypes.WinDLL('cfgmgr32')
        assert all(hasattr(cfg,n)for n in ['CM_Get_Parent','CM_Get_Device_IDW','CM_Locate_DevNodeW'])
        mounts=[]
    else:mounts=[]
    result={'passed':True,'platform':sys.platform,'version':APP.applicationVersion(),
            'display_name':APP.applicationDisplayName(),'window_title':WINDOW.windowTitle(),
            'purple_sample':color.name(),'addons':len(WINDOW.addon_manager.sessions),
            'image_formats':formats,'verified_mounts':mounts,'path':os.environ.get('PATH'),
            'frozen':bool(getattr(sys,'frozen',False)),'python_paths':sys.path}
    (root/'icon-dependencies.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: packaged purple icon, image codecs, Qt, HID and bundled libusb',flush=True)
    APP.exit(0)
except Exception as error:
    import traceback;traceback.print_exc()
    (root/'icon-dependencies.json').write_text(json.dumps({'passed':False,'error':str(error)},indent=2)+'\n')
    APP.exit(1)
