from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import pyqtSignal


class EditorContainer(QWidget):

    clicked = pyqtSignal()

    def __init__(self, editor, parent=None):
        super().__init__(parent)

        self.editor = editor

        self.setLayout(editor)
        self.clicked.connect(editor.on_container_clicked)

    def mousePressEvent(self, ev):
        self.clicked.emit()
