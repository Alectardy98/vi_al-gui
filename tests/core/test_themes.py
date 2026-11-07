"""Default selection, live switching and add-on styling isolation."""
from types import SimpleNamespace
import pytest
from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication, QPushButton
from main_window import MainWindow
from themes import DEFAULT_THEME, PURPLE_DEFAULT_APPLIED, Theme, palettes


@pytest.fixture
def appearance(monkeypatch):
    app = QApplication.instance() or QApplication([])
    palette, stylesheet, style, name = QPalette(app.palette()), app.styleSheet(), app.style().objectName(), Theme.theme
    monkeypatch.setattr(Theme, '_system_palette', None)
    monkeypatch.setattr(Theme, '_system_style', None)
    monkeypatch.setattr(Theme, '_system_stylesheet', None)
    monkeypatch.setattr(Theme, '_applied_palette_key', None)
    yield app
    app.setStyleSheet('')
    if style:
        app.setStyle(style)
    app.setPalette(palette)
    app.setStyleSheet(stylesheet)
    Theme.theme = name


def test_purple_is_the_fresh_profile_default_then_preserves_saved_choices(tmp_path):
    settings = QSettings(str(tmp_path / 'theme.ini'), QSettings.IniFormat)
    window = SimpleNamespace(settings=settings)
    assert MainWindow.get_theme(window) == DEFAULT_THEME
    assert settings.value('theme') == DEFAULT_THEME
    assert settings.value(PURPLE_DEFAULT_APPLIED, False, bool)
    for name in ('Light', 'Dark', 'System', 'Nord'):
        settings.setValue('theme', name)
        assert MainWindow.get_theme(window) == name
    settings.setValue('theme', 'Unavailable theme')
    assert MainWindow.get_theme(window) == DEFAULT_THEME
    assert settings.value('theme') == 'Unavailable theme'


@pytest.mark.parametrize('previous', ['Light', 'Dark', 'System', 'Nord', DEFAULT_THEME])
def test_upgrade_selects_purple_once_without_changing_other_preferences(tmp_path, previous):
    path = str(tmp_path / 'theme.ini')
    settings = QSettings(path, QSettings.IniFormat)
    settings.setValue('theme', previous)
    settings.setValue('keymap', 'US')
    assert Theme.saved_theme(settings) == DEFAULT_THEME
    assert settings.value('keymap') == 'US'
    settings.setValue('theme', 'Light')
    settings.sync()
    assert Theme.saved_theme(QSettings(path, QSettings.IniFormat)) == 'Light'


def test_purple_palette_matches_web_and_switching_clears_only_its_own_styles(appearance):
    app = appearance
    original = QPalette(app.palette())
    font = app.font().toString()
    Theme.set_theme(DEFAULT_THEME)
    assert app.palette().color(QPalette.Window).name() == '#17151b'
    assert app.palette().color(QPalette.Highlight).name() == '#b392f4'
    assert app.palette().color(QPalette.Button).name() == '#342e3d'
    assert app.palette().color(QPalette.Text).name() == '#e9e5ef'
    assert '#614879' in app.styleSheet()
    assert app.font().toString() == font
    Theme.set_theme('Light')
    assert '#614879' not in app.styleSheet()
    assert app.palette().color(QPalette.Window) == palettes['Light'].color(QPalette.Window)
    Theme.set_theme('System')
    assert app.palette().color(QPalette.Window) == original.color(QPalette.Window)


def test_live_menu_selection_persists_without_restart_popup(appearance, tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, 'exec_', lambda *args: pytest.fail('Theme selection opened a restart popup'))
    settings = QSettings(str(tmp_path / 'theme.ini'), QSettings.IniFormat)
    MainWindow.set_theme(SimpleNamespace(settings=settings), DEFAULT_THEME)
    settings.sync()
    assert QSettings(str(tmp_path / 'theme.ini'), QSettings.IniFormat).value('theme') == DEFAULT_THEME
    assert Theme.get_theme() == DEFAULT_THEME
    MainWindow.set_theme(SimpleNamespace(settings=settings), 'Nord')
    assert Theme.saved_theme(settings) == 'Nord'


def test_addon_specific_status_and_rgb_styles_are_preserved(appearance):
    button = QPushButton('LED preview')
    specific = 'QPushButton { background: #00ff00; color: #000000; }'
    button.setStyleSheet(specific)
    Theme.set_theme(DEFAULT_THEME)
    assert button.styleSheet() == specific
    Theme.set_theme('Dark')
    assert button.styleSheet() == specific
    button.deleteLater()


def test_reapplying_current_theme_does_not_repolish_every_widget(appearance, monkeypatch):
    Theme.set_theme(DEFAULT_THEME)
    with monkeypatch.context() as patch:
        patch.setattr(appearance, 'setStyleSheet', lambda *args: pytest.fail('Unchanged theme repolished the application'))
        Theme.set_theme(DEFAULT_THEME)
