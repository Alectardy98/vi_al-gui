# SPDX-License-Identifier: GPL-2.0-or-later
"""Unsupported animation editors never create standalone upload windows."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src/main/python'))
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton
from vi_al_addons.my2k.animation import Animation
from vial_device import VialKeyboard
from widgets.editor_container import EditorContainer

APP = QApplication.instance() or QApplication([])


def device(my2k=False):
    d = VialKeyboard({'vendor_id': 0, 'product_id': 0})
    d.keyboard = SimpleNamespace(animations={'format': []})
    if my2k:
        d.keyboard.amk_rgb_strip = {'strips': [{'count': n} for n in [19,19,8,1,8,4,2]]}
    return d


class WindowOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.before = {id(w) for w in APP.topLevelWidgets() if w.isVisible()}
        self.editor = Animation()
        self.host = None

    def tearDown(self):
        self.editor.deactivate()
        self.editor.library_page.cache.cleanup()
        if self.host:
            self.host.close()
            self.host.deleteLater()
        else:
            for w in (getattr(self.editor, 'content', None), self.editor.legacy_page, self.editor.library_page):
                if w is not None:
                    w.close()
                    w.deleteLater()
        APP.processEvents()

    def visible_new_windows(self):
        APP.processEvents()
        return [w for w in APP.topLevelWidgets() if w.isVisible() and id(w) not in self.before]

    def test_initial_ec_rebuild_without_tab_container_does_not_show_upload_window(self):
        self.editor.rebuild(device())
        self.assertFalse(self.editor.valid())
        self.assertFalse(self.editor.legacy_page.isVisible())
        self.assertEqual(self.visible_new_windows(), [])
        self.assertIsNone(self.editor.keyboard)
        self.assertIsNone(self.editor.library_page.keyboard)

    def test_my2k_rebuild_before_embedding_does_not_show_a_separate_window(self):
        self.editor.rebuild(device(True))
        self.assertTrue(self.editor.valid())
        self.assertEqual(self.visible_new_windows(), [])
        self.host = EditorContainer(self.editor)
        self.host.show()
        APP.processEvents()
        self.assertTrue(self.editor.library_page.isVisible())
        self.assertFalse(self.editor.library_page.isWindow())
        self.assertFalse(self.editor.legacy_page.isVisible())
        self.assertEqual(self.visible_new_windows(), [self.host])

    def test_switching_my2k_to_ec_and_disconnect_keeps_legacy_controls_hidden(self):
        self.editor.rebuild(device(True))
        self.host = EditorContainer(self.editor)
        self.host.show()
        for d in (device(), None, device(True), device()):
            self.editor.rebuild(d)
            APP.processEvents()
            self.assertFalse(self.editor.legacy_page.isVisible())
            self.assertEqual(self.visible_new_windows(), [self.host])
        self.assertIsNone(self.editor.keyboard)
        for button in self.host.findChildren(QPushButton):
            if button.text().startswith('Upload ('):
                self.assertFalse(button.isVisible())


if __name__ == '__main__':
    unittest.main()
