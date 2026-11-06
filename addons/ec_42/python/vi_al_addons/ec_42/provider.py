# SPDX-License-Identifier: GPL-3.0-or-later
"""EC42 add-on provider. Its selected HID handle remains exclusively owned."""
from collections import deque
from PyQt5 import sip
from PyQt5.QtCore import Qt, QCoreApplication, QTimer, QEvent
from PyQt5.QtGui import QMouseEvent, QKeyEvent, QWheelEvent, QContextMenuEvent, QShortcutEvent
from PyQt5.QtWidgets import QAction
from addon_runtime import Addon, Page, Session
from .editor import ECEditor


class EC42Session(Session):
    def __init__(self, window, appctx):
        self.window = window
        self.ec_editor = ECEditor(window.layout_editor)
        self.ec_hid_busy = False
        self.ec_deferred_input = deque(maxlen=64)
        self.ec_closing = False
        self.ec_tab_press_pending = None
        self.ec_editor.busy_changed.connect(self.ec_transport_busy)
        self.pages = (Page(self.ec_editor, 'Calibration', 240),
                      Page(self.ec_editor.actuation_page, 'Actuation', 250),
                      Page(self.ec_editor.sensors_page, 'Live Sensors', 260))
        for page in self.pages:
            page.editor.addon_controller = self.ec_editor
        window.ec_editor = self.ec_editor  # Public editor handle for diagnostics.

    def __getattr__(self, name):
        # Navigation widgets belong to the host window; transport state above
        # belongs to this session and never becomes a core-window special case.
        return getattr(self.window, name)

    def before_close(self):
        self.ec_closing = True
        self.ec_deferred_input.clear()
        self.ec_tab_press_pending = None
        if self.ec_editor.worker:
            self.ec_editor.deactivate()
            self.ec_editor.worker.finished.connect(self.window.close)
            return False
        self.ec_editor.deactivate()
        return True

    def ec_transport_busy(self, busy):
        # EC42 uses the selected Vial connection, never a competing HID handle.
        # Sensor polling must not toggle QWidget enabled state: doing so repaints
        # the entire navigation area twice per snapshot and visibly flashes it.
        # Hold conflicting user input in eventFilter instead; discovery is paused
        # so it cannot replace/close the handle while the worker is using it.
        self.ec_hid_busy = busy
        if busy:
            self.autorefresh._lock()
        else:
            self.autorefresh._unlock()
            # Replay actual user input only after the HID worker releases its
            # handle. Do not silently discard clicks on a frequently polled page.
            events = list(self.ec_deferred_input)
            self.ec_deferred_input.clear()
            if not self.ec_closing:
                for target, event in events:
                    if target is not None and not sip.isdeleted(target):
                        if isinstance(event,tuple):
                            QTimer.singleShot(0,lambda index=event[1]: self.apply_ec_tab(index))
                        else:
                            QCoreApplication.postEvent(target, event)
    def apply_ec_tab(self, index):
        if self.ec_closing:
            return
        if self.ec_hid_busy and not self.shared_ec_tab(index):
            self.ec_deferred_input.append((self.tabs.tabBar(),('tab',index)))
        elif 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)
    def shared_ec_tab(self, index):
        """All EC views share one worker; changing that view needs no HID I/O."""
        current = self.tabs.currentWidget()
        target = self.tabs.widget(index) if 0 <= index < self.tabs.count() else None
        controller = getattr(self, 'ec_editor', None)
        return (controller is not None and current is not None and target is not None and
                getattr(getattr(current, 'editor', None), 'ec_controller', None) is controller and
                getattr(getattr(target, 'editor', None), 'ec_controller', None) is controller)
    def defer_ec_input(self, watched, event):
        if watched is self.tabs.tabBar() and event.type() in (QEvent.MouseButtonPress,QEvent.MouseButtonRelease) and event.button()==Qt.LeftButton:
            if self.shared_ec_tab(self.tabs.tabBar().tabAt(event.pos())):
                return False
            if event.type()==QEvent.MouseButtonPress:
                self.ec_tab_press_pending = self.tabs.tabBar().tabAt(event.pos())
            return True
        copies = {QEvent.MouseButtonPress: QMouseEvent, QEvent.MouseButtonRelease: QMouseEvent,
                  QEvent.MouseButtonDblClick: QMouseEvent, QEvent.KeyPress: QKeyEvent,
                  QEvent.KeyRelease: QKeyEvent, QEvent.Wheel: QWheelEvent,
                  QEvent.ContextMenu: QContextMenuEvent, QEvent.Shortcut: QShortcutEvent}
        if len(self.ec_deferred_input) < self.ec_deferred_input.maxlen:
            if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
                # Preserve independent position data for deferred delivery.
                copied = QMouseEvent(event.type(), event.localPos(), event.windowPos(),
                                     event.screenPos(), event.button(), event.buttons(),
                                     event.modifiers(), event.source())
                copied.setTimestamp(event.timestamp())
            else:
                copied = copies[event.type()](event)
            self.ec_deferred_input.append((watched, copied))
        return True
    def filter_event(self, watched, event):
        if event.type()==QEvent.MouseButtonRelease and getattr(self,'ec_tab_press_pending',None) is not None:
            index,self.ec_tab_press_pending = self.ec_tab_press_pending,None
            if watched is self.tabs.tabBar() and event.button()==Qt.LeftButton:
                self.apply_ec_tab(index)
                return True
        if self.ec_hid_busy:
            # Actions may also be invoked by shortcuts while their menu is closed.
            if event.type() == QEvent.Shortcut and isinstance(watched, QAction):
                return self.defer_ec_input(watched, event)
            if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                                QEvent.MouseButtonDblClick, QEvent.KeyPress,
                                QEvent.KeyRelease, QEvent.Wheel, QEvent.ContextMenu):
                # Include popup children of the device selector and menus. Local
                # EC controls remain interactive and can queue the next operation.
                protected = (self.tabs.tabBar(), self.combobox_devices,
                             self.btn_refresh_devices, self.menuBar())
                obj = watched
                while obj is not None:
                    if obj in protected:
                        return self.defer_ec_input(watched, event)
                    obj = obj.parent()
        return False

ADDON = Addon('ec_42', create_session=EC42Session)
