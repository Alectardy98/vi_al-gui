# SPDX-License-Identifier: GPL-2.0-or-later
"""Device-free smoke checks or an explicitly supplied local Qt test bridge."""
import os
import sys

if sys.platform.startswith('linux'):
    # Avoid Qt's fatal Wayland fractional-buffer mismatch on affected desktops.
    os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')
    os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '0')
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '0')

if os.environ.get('VI_AL_HID_READ_GUARD'):
    import runpy
    runpy.run_path(os.environ['VI_AL_HID_READ_GUARD'])

if os.environ.get('VI_AL_SMOKE_TEST'):
    import hid
    def forbidden(*args, **kwargs):
        raise RuntimeError('Hardware access disabled during Vi_al smoke test')
    hid.enumerate = lambda *a, **kw: []
    hid.device = forbidden
    try:
        import hidraw
        hidraw.enumerate = hid.enumerate; hidraw.device = forbidden
    except ImportError:
        pass
    import usb.core
    usb.core.find = forbidden

if os.environ.get('VI_AL_SMOKE_TEST') or os.environ.get('VI_AL_TEST_BRIDGE'):
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox
    original_exec = QApplication.exec_
    def checked_exec(app):
        def verify():
            try:
                windows=[w for w in app.topLevelWidgets() if isinstance(w,QMainWindow) and w.isVisible()]
                errors=[w.text() for w in app.topLevelWidgets() if isinstance(w,QMessageBox) and w.isVisible()]
                assert len(windows)==1 and not errors, (len(windows), errors)
                window=windows[0]
                if os.environ.get('VI_AL_TEST_BRIDGE'):
                    import runpy
                    runpy.run_path(os.environ['VI_AL_TEST_BRIDGE'],init_globals={'APP':app,'WINDOW':window})
                    return
                from addon_runtime.loader import load_errors
                assert not load_errors(), load_errors()
                assert not window.addon_manager.errors, window.addon_manager.errors
                expected=int(os.environ.get('VI_AL_EXPECT_ADDONS','0'))
                assert len(window.addon_manager.sessions)==expected, len(window.addon_manager.sessions)
                icon=app.windowIcon();assert not icon.isNull()
                if os.environ.get('VI_AL_SCREENSHOT'):
                    assert window.grab().save(os.environ['VI_AL_SCREENSHOT'])
                print('SMOKE PASS: Vi_al; add-ons={}; editors={}; size={}x{}'.format(expected,len(window.editors),window.width(),window.height()),flush=True)
                app.exit(0)
            except Exception as error:
                import traceback
                traceback.print_exc(); print('SMOKE FAIL: '+str(error),flush=True);app.exit(1)
        QTimer.singleShot(2500,verify)
        return original_exec()
    QApplication.exec_=checked_exec
