# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import Qt
from addon_runtime import Addon, Page, Session
from .editor import AW768Lighting


class AW768Session(Session):
    def __init__(self, window, appctx):
        self.window = window
        self.editor = AW768Lighting()
        self.pages = (Page(self.editor, 'AW768 Lighting', 235),)
        window.aw768_lighting = self.editor

    def before_close(self):
        if self.editor.shutdown():
            return True
        try:
            self.editor.worker.finished.connect(self.window.close, Qt.UniqueConnection)
        except TypeError:
            pass
        return False


ADDON = Addon('alienware_aw768', create_session=AW768Session)
