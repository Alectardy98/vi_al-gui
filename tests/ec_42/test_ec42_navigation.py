# SPDX-License-Identifier: GPL-3.0-or-later
"""Polling keeps navigation visually stable while excluding competing HID input."""
import os
from collections import deque
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src/main/python'))
from PyQt5.QtCore import Qt, QEvent, QObject
from PyQt5.QtGui import QKeySequence, QShortcutEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget,
                            QComboBox, QToolButton, QLineEdit, QAction, QVBoxLayout)
from main_window import MainWindow
from vi_al_addons.my2k.animation import Animation
from vial_device import VialKeyboard

APP = QApplication.instance() or QApplication([])


from vi_al_addons.ec_42.provider import EC42Session

class Window(QMainWindow):
    ec_transport_busy = EC42Session.ec_transport_busy
    apply_ec_tab = EC42Session.apply_ec_tab
    shared_ec_tab = EC42Session.shared_ec_tab
    defer_ec_input = EC42Session.defer_ec_input
    eventFilter = EC42Session.filter_event
    """Exercise production navigation code without starting discovery or HID."""
    def __init__(self):
        QMainWindow.__init__(self)
        self.ec_hid_busy = False
        self.ec_deferred_input = deque(maxlen=64)
        self.ec_closing = False
        self.locks = []
        self.autorefresh = SimpleNamespace(_lock=lambda: self.locks.append(True),
                                          _unlock=lambda: self.locks.append(False))
        root = QWidget()
        body = QVBoxLayout(root)
        self.combobox_devices = QComboBox()
        self.combobox_devices.addItems(['ME EC Kit', 'MY-2K'])
        self.btn_refresh_devices = QToolButton()
        self.btn_refresh_devices.setText('Refresh')
        self.tabs = QTabWidget()
        page = QWidget()
        row = QVBoxLayout(page)
        self.local_edit = QLineEdit()
        row.addWidget(self.local_edit)
        self.tabs.addTab(page, 'EC Calibration')
        self.tabs.addTab(QWidget(), 'Keymap')
        self.action = QAction('Refresh', self)
        self.action.setShortcut(QKeySequence('Ctrl+R'))
        self.menuBar().addMenu('File').addAction(self.action)
        for w in (self.combobox_devices, self.btn_refresh_devices, self.tabs):
            body.addWidget(w)
        self.setCentralWidget(root)
        APP.installEventFilter(self)
        self.resize(700, 400)
        self.show()
        QTest.qWait(20)
        APP.processEvents()

    def closeEvent(self, event):
        APP.removeEventFilter(self)
        event.accept()


class EnabledChanges(QObject):
    def __init__(self):
        super().__init__()
        self.events = 0

    def eventFilter(self, target, event):
        if event.type() == QEvent.EnabledChange:
            self.events += 1
        return False


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.window = Window()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()

    def test_repeated_poll_lock_does_not_change_enabled_state_or_pixels(self):
        w = self.window
        watched = (w.tabs.tabBar(), w.combobox_devices, w.btn_refresh_devices, w.menuBar())
        counter = EnabledChanges()
        for target in watched:
            target.installEventFilter(counter)
        for _ in range(30):
            w.ec_transport_busy(True)
            APP.processEvents()
            self.assertTrue(all(x.isEnabled() for x in watched))
            w.ec_transport_busy(False)
        self.assertEqual(counter.events, 0)
        self.assertEqual(w.locks, [True, False]*30)
        baseline = w.tabs.tabBar().grab().toImage()
        w.ec_transport_busy(True)
        self.assertEqual(w.tabs.tabBar().grab().toImage(), baseline)

    def test_navigation_click_blocked_during_exchange_then_works(self):
        w = self.window
        point = w.tabs.tabBar().tabRect(1).center()
        w.ec_transport_busy(True)
        QTest.mouseClick(w.tabs.tabBar(), Qt.LeftButton, pos=point)
        self.assertEqual(w.tabs.currentIndex(), 0)
        w.ec_transport_busy(False)
        QTest.qWait(10)
        APP.processEvents()
        self.assertEqual(w.tabs.currentIndex(), 1)

    def test_refresh_and_device_wheel_do_not_interrupt_exchange(self):
        w = self.window
        clicked = []
        w.btn_refresh_devices.clicked.connect(lambda: clicked.append(True))
        w.ec_transport_busy(True)
        QTest.mouseClick(w.btn_refresh_devices, Qt.LeftButton)
        QTest.keyClick(w.combobox_devices, Qt.Key_Down)
        self.assertFalse(clicked)
        self.assertEqual(w.combobox_devices.currentIndex(), 0)
        w.ec_transport_busy(False)
        QTest.qWait(10)
        APP.processEvents()
        self.assertEqual(clicked, [True])
        self.assertEqual(w.combobox_devices.currentIndex(), 1)

    def test_local_ec_editing_remains_interactive_during_poll(self):
        w = self.window
        w.ec_transport_busy(True)
        QTest.keyClicks(w.local_edit, 'hello')
        self.assertEqual(w.local_edit.text(), 'hello')

    def test_hid_menu_shortcut_blocked_until_exchange_finishes(self):
        w = self.window
        triggered = []
        w.action.triggered.connect(lambda: triggered.append(True))
        w.ec_transport_busy(True)
        APP.sendEvent(w.action, QShortcutEvent(QKeySequence('Ctrl+R'), 1))
        self.assertFalse(triggered)
        w.ec_transport_busy(False)
        QTest.qWait(10)
        APP.processEvents()
        self.assertEqual(triggered, [True])


class AnimationCapabilityTests(unittest.TestCase):
    def valid(self, keyboard):
        device = VialKeyboard({'vendor_id': 0, 'product_id': 0})
        device.keyboard = keyboard
        return Animation.valid(SimpleNamespace(device=device))

    def test_me_ec_and_generic_vial_do_not_have_animations(self):
        self.assertFalse(self.valid(SimpleNamespace(animations={'format': []})))
        self.assertFalse(self.valid(SimpleNamespace()))

    def test_my2k_keeps_its_animation_library(self):
        strips = {'strips': [{'count': n} for n in [19,19,8,1,8,4,2]]}
        self.assertTrue(self.valid(SimpleNamespace(amk_rgb_strip=strips)))

    def test_other_boards_with_animation_formats_are_hidden(self):
        self.assertFalse(self.valid(SimpleNamespace(animations={'format': [{'name':'legacy'}]})))

    def test_missing_keyboard_is_hidden(self):
        self.assertFalse(self.valid(None))


if __name__ == '__main__':
    unittest.main()
