"""A transient Show event is a bug even if the final screenshot looks correct."""
from types import SimpleNamespace
from PyQt5.QtCore import QObject,QEvent
from PyQt5.QtWidgets import QApplication,QMainWindow,QTabWidget,QPushButton
from editor.basic_editor import BasicEditor
from main_window import MainWindow
from widgets.editor_container import EditorContainer


class Page(BasicEditor):
    def __init__(self):
        super().__init__()
        self.button=QPushButton('Control shown during rebuild')
        self.addWidget(self.button)
        self.supported=False

    def valid(self):
        return self.supported

    def rebuild(self,device):
        self.supported=bool(device)
        self.button.setVisible(self.supported)


class Host(QMainWindow):
    _create_editor_containers=MainWindow._create_editor_containers
    refresh_tabs=MainWindow.refresh_tabs

    def __init__(self):
        super().__init__()
        self.tabs=QTabWidget(self);self.setCentralWidget(self.tabs)
        self.editors=[(Page(),'First'),(Page(),'Second')]
        self._create_editor_containers()
        self.refresh_tabs()


class WindowShows(QObject):
    def __init__(self,host):
        super().__init__();self.host=host;self.unexpected=[]

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Show and isinstance(obj,QPushButton)and obj.isWindow():
            self.unexpected.append(obj.text())
        return False


def test_rebuild_never_shows_an_unattached_control(qtbot):
    host=Host();qtbot.addWidget(host);host.show()
    app=QApplication.instance();watch=WindowShows(host);app.installEventFilter(watch)
    try:
        for first,second in [(False,True),(True,False),(True,True),(False,False)]*3:
            for(editor,_),supported in zip(host.editors,(first,second)):
                editor.rebuild(supported)
            host.refresh_tabs();app.processEvents()
            for editor,_ in host.editors:
                assert editor.parentWidget()is host.editor_containers[editor]
                assert not editor.button.isWindow()
        assert watch.unexpected==[]
    finally:app.removeEventFilter(watch)


def test_refresh_reuses_containers_without_leaking_wrappers(qtbot):
    host=Host();qtbot.addWidget(host)
    original={editor:id(container)for editor,container in host.editor_containers.items()}
    for _ in range(10):
        for editor,_ in host.editors:editor.rebuild(True)
        host.refresh_tabs()
        assert host.tabs.count()==2
        assert len(host.findChildren(EditorContainer))==2
        assert {editor:id(container)for editor,container in host.editor_containers.items()}==original
