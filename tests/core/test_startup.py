"""First paint, eager page readiness and cancellation without USB access."""
from pathlib import Path
import sys

import pytest
from PyQt5.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication, QLabel

import main_window
from themes import Theme


class Resources:
    def get_resource(self, name):
        return str(Path(__file__).resolve().parents[2] / 'src/main/resources/base' / name)


@pytest.fixture
def startup(qtbot, monkeypatch, tmp_path):
    calls = []
    windows = []
    app = QApplication.instance()
    palette, stylesheet, style = QPalette(app.palette()), app.styleSheet(), app.style().objectName()
    saved_theme = {name: getattr(Theme, name) for name in
                   ('theme', '_system_palette', '_system_style', '_system_stylesheet', '_applied_palette_key')}

    class Discovery(QObject):
        devices_updated = pyqtSignal(object, bool)

        def __init__(self):
            super().__init__()
            self.current_device = None
            calls.append('discovery')

        def update(self, **kwargs):
            calls.append('refresh')

        def load_via_stack(self, data):
            pass

    monkeypatch.setattr(main_window, 'Autorefresh', Discovery)
    monkeypatch.setattr(main_window, 'QSettings', lambda *args: QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))

    def create(show=True):
        window = main_window.MainWindow(Resources(), staged_startup=True)
        windows.append(window)
        qtbot.addWidget(window)
        if show:
            window.show()
        return window

    yield create, calls
    for window in windows:
        window.close()
    app.setStyleSheet('')
    app.setStyle(style)
    app.setPalette(palette)
    app.setStyleSheet(stylesheet)
    for name, value in saved_theme.items():
        setattr(Theme, name, value)


def test_window_is_visible_before_editors_or_discovery_then_all_pages_are_ready(startup, qtbot, monkeypatch):
    create, calls = startup
    window = create()
    assert window.isVisible()
    assert not window.startup_ready
    assert not hasattr(window, 'layout_editor')
    assert not calls
    panel = window.centralWidget()
    assert 'No devices detected.' in window.lbl_no_devices.text()
    assert not any('Loading keyboard support' in label.text() for label in window.findChildren(QLabel))
    assert window.combobox_devices.count() == 0
    assert not window.combobox_devices.isEnabled()
    assert not window.btn_refresh_devices.isEnabled()
    assert not window.tabs.isVisible()
    assert window.menuBar().actions()
    first_turn = []
    QTimer.singleShot(0, lambda: first_turn.append((window.isVisible(), hasattr(window, 'layout_editor'))))
    qtbot.waitUntil(lambda: window.startup_ready, timeout=20000)
    assert first_turn == [(True, False)], 'Page construction started before showing the loading window'
    expected = ['discovery', 'refresh'] if sys.platform.startswith('win') or sys.platform == 'emscripten' else ['discovery']
    assert calls == expected
    assert window.centralWidget().isVisible()
    assert window.centralWidget() is panel, 'Startup replaced the normal interface'
    assert window.combobox_devices.isEnabled()
    assert window.btn_refresh_devices.isEnabled()
    assert window.menuBar().isEnabled()
    assert not window.addon_manager.errors
    assert len(window.editors) == len(window.editor_containers)
    assert all(window.editor_containers[editor].layout() is editor for editor, _ in window.editors)
    assert not window._startup_timer.isActive()
    # Every page already exists; no startup work remains for a tab click.
    editors = tuple(editor for editor, _ in window.editors)
    monkeypatch.setattr(window, '_build_interface', lambda: pytest.fail('Prepared pages were rebuilt'))
    window._initialize_interface()
    qtbot.wait(20)
    assert tuple(editor for editor, _ in window.editors) == editors


def test_closing_loading_window_cancels_pending_work(startup, qtbot):
    create, calls = startup
    window = create()
    window.close()
    qtbot.wait(50)
    assert not calls
    assert not window.startup_ready
    assert window._startup_closed
    assert not window._startup_timer.isActive()


def test_preparation_waits_for_a_painted_window(startup, qtbot):
    create, calls = startup
    window = create(show=False)
    qtbot.wait(150)
    assert not calls
    assert not window._startup_timer.isActive()
    assert not hasattr(window, 'layout_editor')
    window.show()
    qtbot.waitUntil(lambda: window._startup_timer.isActive(), timeout=2000)
    assert not hasattr(window, 'layout_editor')
    window.close()
