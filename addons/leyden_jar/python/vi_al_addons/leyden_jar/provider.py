# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional native Leyden Jar pages; preserve exclusive selected-handle ownership."""
from collections import deque
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QCoreApplication, QTimer
from PyQt5.QtGui import QMouseEvent, QKeyEvent, QWheelEvent
from PyQt5.QtWidgets import QAction
from addon_runtime import Addon, Page, Session
from .editor import Controller


class LeydenJarSession(Session):
    def __init__(self, window, appctx):
        self.window = window
        self.controller = Controller(window)
        self.busy = self.closing = False
        self.deferred = deque(maxlen=32)
        self.controller.busy_changed.connect(self.busy_changed)
        self.pages = (Page(self.controller.general, 'General', 140),
                      Page(self.controller.calibration, 'Calibration', 240),
                      Page(self.controller.sensors, 'Live Sensors', 260))
        window.leyden_jar = self.controller

    def busy_changed(self, busy):
        self.busy = busy
        if busy:
            self.window.autorefresh._lock()
        else:
            self.window.autorefresh._unlock()
            events = list(self.deferred)
            self.deferred.clear()
            if not self.closing:
                for target, event in events:
                    if not sip.isdeleted(target):
                        QCoreApplication.postEvent(target, event)

    def filter_event(self, watched, event):
        if not self.busy:
            return False
        if event.type() == QEvent.Shortcut and isinstance(watched, QAction):
            return True
        if event.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                                QEvent.MouseButtonDblClick, QEvent.KeyPress,
                                QEvent.KeyRelease, QEvent.Wheel):
            return False
        protected = (self.window.combobox_devices, self.window.btn_refresh_devices,
                     self.window.tabs.tabBar(), self.window.menuBar())
        target = watched
        while target is not None:
            if target in protected:
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
        self.closing = self.controller.closing = True
        self.deferred.clear()
        self.controller.pending.clear()
        self.controller.deactivate()
        if self.controller.worker is not None:
            self.controller.worker.finished.connect(lambda: QTimer.singleShot(0, self.window.close))
            return False
        return True


ADDON = Addon('leyden_jar', create_session=LeydenJarSession)
