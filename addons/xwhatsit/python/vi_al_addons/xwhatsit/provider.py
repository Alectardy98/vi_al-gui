# SPDX-License-Identifier: GPL-2.0-or-later
"""Optional xwhatsit pages, using only the selected Vial connection."""
from collections import deque

from PyQt5 import sip
from PyQt5.QtCore import Qt, QEvent, QCoreApplication, QTimer
from PyQt5.QtGui import QMouseEvent, QKeyEvent, QWheelEvent
from PyQt5.QtWidgets import QAction

from addon_runtime import Addon, Page, Session
from .editor import Controller


class XwhatsitSession(Session):
    def __init__(self, window, appctx):
        self.window = window
        self.controller = Controller(window)
        self.busy = self.closing = False
        self.close_requested = False
        self.close_timer = QTimer(self.controller)
        self.close_timer.setSingleShot(True)
        self.close_timer.setInterval(600)
        self.close_timer.timeout.connect(window.close)
        self.deferred = deque(maxlen=32)
        self.controller.busy_changed.connect(self.busy_changed)
        self.pages = (Page(self.controller.calibration, 'Calibration', 240),
                      Page(self.controller.sensors, 'Live Sensors', 260),
                      Page(self.controller.general, 'General', 140))
        window.xwhatsit = self.controller

    def busy_changed(self, busy):
        self.busy = busy
        if busy:
            self.window.autorefresh._lock()
        else:
            self.window.autorefresh._unlock()
            if self.close_requested:
                self.close_timer.start()
            elif not self.closing and self.controller.pending is None:
                events = list(self.deferred)
                self.deferred.clear()
                for target, event in events:
                    if not sip.isdeleted(target):
                        QCoreApplication.postEvent(target, event)

    def filter_event(self, watched, event):
        if not self.busy and self.controller.pending is None:
            return False
        if event.type() == QEvent.Shortcut and isinstance(watched, QAction):
            return True
        if event.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick,
                                QEvent.KeyPress, QEvent.KeyRelease, QEvent.Wheel):
            return False
        protected = (self.window.combobox_devices, self.window.btn_refresh_devices,
                     self.window.tabs.tabBar(), self.window.menuBar())
        target = watched
        while target is not None:
            if target in protected:
                if not self.busy:
                    self.controller.save_pending()
                # Keep the active handle alive until its bounded operation is
                # complete. Replay user navigation; never swallow a selection.
                if len(self.deferred) < self.deferred.maxlen:
                    if isinstance(event, QMouseEvent):
                        copy = QMouseEvent(event.type(), event.localPos(), event.windowPos(), event.screenPos(),
                                           event.button(), event.buttons(), event.modifiers(), event.source())
                    elif isinstance(event, QKeyEvent):
                        copy = QKeyEvent(event)
                    elif isinstance(event, QWheelEvent):
                        copy = QWheelEvent(event)
                    else:
                        return True
                    self.deferred.append((watched, copy))
                return True
            target = target.parent()
        return False

    def before_close(self):
        if self.controller.worker is not None or self.controller.pending is not None:
            self.close_requested = True
            self.controller.deactivate()
            self.deferred.clear()
            if self.controller.worker is None and not self.controller.save_timer.isActive():
                self.controller.save_timer.start(1)
            self.close_timer.start()
            return False
        self.close_timer.stop()
        self.closing = self.controller.closing = True
        self.deferred.clear()
        self.controller.deactivate()
        return True


ADDON = Addon('xwhatsit', create_session=XwhatsitSession)
