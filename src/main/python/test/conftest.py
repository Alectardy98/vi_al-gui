"""Keep GUI tests independent of the user's real window/preferences."""
import pytest
from PyQt5.QtCore import QSettings


@pytest.fixture(autouse=True)
def isolated_gui_preferences(monkeypatch,tmp_path):
    import main_window
    # The explicit organization/application constructor uses native settings,
    # regardless of QSettings.setDefaultFormat(). Use an isolated INI directly.
    monkeypatch.setattr(main_window,'QSettings',
                        lambda *args,**kwargs:QSettings(str(tmp_path/'preferences.ini'),QSettings.IniFormat))
