"""Preserve names, tooltips and wire IDs while avoiding repeated Qt styling."""
from types import SimpleNamespace

from PyQt5.QtWidgets import QPushButton

from keycodes.keycodes import Keycode
from tabbed_keycodes import AlternativeDisplay
from util import KeycodeDisplay


def test_normal_buttons_inherit_theme_and_overrides_only_restyle_when_changed(qtbot, monkeypatch):
    button = QPushButton()
    qtbot.addWidget(button)
    button.keycode = SimpleNamespace(qmk_id='KC_A', label='A')
    monkeypatch.setattr(KeycodeDisplay, 'keymap_override', {})
    assignments = []
    original = button.setStyleSheet
    def set_style(style):
        assignments.append(style)
        original(style)
    monkeypatch.setattr(button, 'setStyleSheet', set_style)
    for _ in range(3):
        KeycodeDisplay.relabel_buttons([button])
    assert not assignments
    assert button.text() == 'A'
    KeycodeDisplay.keymap_override['KC_A'] = 'A&B'
    KeycodeDisplay.relabel_buttons([button])
    KeycodeDisplay.relabel_buttons([button])
    assert len(assignments) == 1
    assert button.text() == 'A&&B'
    KeycodeDisplay.keymap_override.clear()
    KeycodeDisplay.relabel_buttons([button])
    assert assignments[-1] == ''
    assert button.text() == 'A'


def test_reused_buttons_receive_current_labels_tooltips_and_filtering(qtbot, monkeypatch):
    monkeypatch.setattr(KeycodeDisplay, 'keymap_override', {})
    descriptions = {'KC_A': 'First description', 'KC_B': 'B description'}
    monkeypatch.setattr(Keycode, 'tooltip', lambda code: descriptions[code])
    first = SimpleNamespace(qmk_id='KC_A', label='First name', hidden=False)
    second = SimpleNamespace(qmk_id='KC_B', label='Second name', hidden=False)
    display = AlternativeDisplay(None, [first, second], None)
    qtbot.addWidget(display)
    display.recreate_buttons(lambda code: True)
    buttons = tuple(display.buttons)
    renamed = SimpleNamespace(qmk_id='KC_A', label='New keyboard name', hidden=False)
    display.keycodes = [renamed, second]
    descriptions['KC_A'] = 'New keyboard description'
    display.recreate_buttons(lambda code: True)
    assert tuple(display.buttons) == buttons
    assert buttons[0].keycode is renamed
    assert buttons[0].text == 'New keyboard name'
    assert buttons[0].toolTip() == 'New keyboard description'
    sent = []
    display.keycode_changed.connect(sent.append)
    buttons[0].click()
    assert sent == ['KC_A']
    display.recreate_buttons(lambda code: code == 'KC_B')
    assert [button.keycode.qmk_id for button in display.buttons] == ['KC_B']
