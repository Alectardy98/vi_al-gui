# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, QLabel, QPushButton, QButtonGroup, QSlider, QScrollArea
from editor.basic_editor import BasicEditor
from vial_device import VialKeyboard
from keycodes.keycodes import Keycode
from widgets.key_widget import KeyWidget
from vi_al_addons.my2k.touch_bar_protocol import TouchBarClient, valid_key


def key_filter(key):
    try:
        return valid_key(Keycode.deserialize(key.replace('(kc)', '(KC_A)'), reraise=True))
    except Exception:
        # Unknown/firmware-only key names are not selectable touch actions.
        return False


class TouchBar(BasicEditor):
    def __init__(self, layout_editor):
        super().__init__()
        self.keyboard = self.client = None
        self.loading = True
        self.modified = False
        self.revision = 0
        self.hold_jitter_supported = False
        self.apply_timer = QTimer(self)
        self.apply_timer.setSingleShot(True)
        self.apply_timer.timeout.connect(self.apply_live)
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(300)
        self.save_timer.timeout.connect(self.poll_save)
        page = QWidget()
        body = QVBoxLayout(page)
        body.setSpacing(14)
        intro = QLabel('Assign the actions for each direction and a tap. Changes apply live and save automatically.')
        intro.setWordWrap(True)
        body.addWidget(intro)
        self.controls = QGroupBox('Touch Bar')
        grid = QGridLayout(self.controls)
        self.keys = {}
        for col, (name, label) in enumerate((('left', 'Left / swipe left'), ('tap', 'Tap'), ('right', 'Right / swipe right'))):
            title = QLabel(label)
            title.setAlignment(Qt.AlignCenter)
            grid.addWidget(title, 0, col)
            key = KeyWidget(key_filter)
            key.setMinimumSize(100, 90)
            key.changed.connect(self.mark_dirty)
            grid.addWidget(key, 1, col, Qt.AlignCenter)
            self.keys[name] = key
            grid.setColumnStretch(col, 1)
        note = QLabel('Click an action to choose a key. Keyboard, modifier, media and mouse keys are supported; None disables that action.')
        note.setWordWrap(True)
        grid.addWidget(note, 2, 0, 1, 3)
        modes = QHBoxLayout()
        self.mode_group = QButtonGroup(page)
        self.mode_group.setExclusive(True)
        self.hold = QPushButton('Hold Mode')
        self.slider = QPushButton('Slider Mode')
        for i, button in enumerate((self.hold, self.slider)):
            button.setCheckable(True)
            button.setMinimumHeight(48)
            button.setStyleSheet('QPushButton { padding: 10px 18px; font-weight: 600; } QPushButton:checked { background-color: #336b8f; color: white; border: 2px solid #66b5e7; }')
            self.mode_group.addButton(button, i)
            button.toggled.connect(self.mark_dirty)
            modes.addWidget(button, 1)
        grid.addLayout(modes, 3, 0, 1, 3)
        self.mode_hint = QLabel()
        self.mode_hint.setWordWrap(True)
        grid.addWidget(self.mode_hint, 4, 0, 1, 3)
        grid.setRowMinimumHeight(5, 20)
        self.sensitivity_group = QGroupBox('Sensitivity')
        sensitivity_body = QVBoxLayout(self.sensitivity_group)
        sensitivity_body.setSpacing(10)
        sensitivity = QHBoxLayout()
        self.sensitivity = QSlider(Qt.Horizontal)
        self.sensitivity.setRange(1, 100)
        self.sensitivity.valueChanged.connect(self.mark_dirty)
        self.sensitivity_value = QLabel()
        sensitivity.addWidget(self.sensitivity, 1)
        sensitivity.addWidget(self.sensitivity_value)
        sensitivity_body.addLayout(sensitivity)
        sensitivity_hint = QLabel('Higher sensitivity recognizes lighter touches and produces more steps per swipe. Default: 50. No sensor calibration is changed.')
        sensitivity_hint.setWordWrap(True)
        sensitivity_body.addWidget(sensitivity_hint)
        grid.addWidget(self.sensitivity_group, 6, 0, 1, 3)
        grid.setRowMinimumHeight(7, 16)
        self.jitter_group = QGroupBox('Tap Jitter Threshold')
        jitter_body = QVBoxLayout(self.jitter_group)
        jitter_body.setSpacing(10)
        jitter_row = QHBoxLayout()
        self.tap_jitter = QSlider(Qt.Horizontal)
        self.tap_jitter.setRange(0, 100)
        self.tap_jitter.valueChanged.connect(self.mark_dirty)
        self.tap_jitter_value = QLabel()
        jitter_row.addWidget(self.tap_jitter, 1)
        jitter_row.addWidget(self.tap_jitter_value)
        jitter_body.addLayout(jitter_row)
        self.jitter_hint = QLabel('Slider mode only. Higher values allow more movement during a tap; lower values start swipes sooner. Default: 50. Zero restores the original immediate swipe detection.')
        self.jitter_hint.setWordWrap(True)
        jitter_body.addWidget(self.jitter_hint)
        grid.addWidget(self.jitter_group, 8, 0, 1, 3)
        for slider, value in ((self.sensitivity, self.sensitivity_value), (self.tap_jitter, self.tap_jitter_value)):
            slider.setMinimumHeight(38)
            slider.setStyleSheet('QSlider::groove:horizontal { height: 7px; border-radius: 3px; background: palette(mid); } QSlider::handle:horizontal { width: 22px; margin: -7px 0; border-radius: 10px; background: palette(highlight); }')
            value.setMinimumWidth(46)
            font = value.font()
            font.setPointSizeF(font.pointSizeF() + 2)
            value.setFont(font)
        for group in (self.sensitivity_group, self.jitter_group):
            font = group.font()
            font.setPointSizeF(font.pointSizeF() + 1)
            group.setFont(font)
        body.addWidget(self.controls)
        self.status = QLabel('Connect a supported Release 1 Touch keyboard.')
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        body.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(page)
        self.addWidget(scroll)
        self.loading = False
        self.controls.setEnabled(False)

    def valid(self):
        return bool(isinstance(self.device, VialKeyboard) and self.device.keyboard and
                    self.device.keyboard.amk_rgb_indicator and
                    tuple(i.get('index') for i in self.device.keyboard.amk_rgb_indicator.get('indicators', [])) == (125, 126, 112, 64, 65, 127))

    def rebuild(self, device):
        self.apply_timer.stop()
        self.save_timer.stop()
        self.client = self.keyboard = None
        self.controls.setEnabled(False)
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.reload()

    def activate(self):
        if self.keyboard:
            self.reload()

    def deactivate(self):
        if self.modified and self.client:
            self.apply_timer.stop()
            self.apply_live()
        self.save_timer.stop()

    def refresh_labels(self):
        self.sensitivity_value.setText(str(self.sensitivity.value()))
        self.tap_jitter_value.setText(str(self.tap_jitter.value()))
        jitter_available = self.slider.isChecked() or self.hold_jitter_supported
        self.tap_jitter.setEnabled(jitter_available)
        self.tap_jitter_value.setEnabled(jitter_available)
        self.jitter_hint.setEnabled(jitter_available)
        self.jitter_hint.setText('Both modes: higher values ignore more finger-position jitter. Hold mode filters unintended direction changes while preserving end holds and taps; Slider mode preserves its tap-versus-swipe threshold. Default: 50. Zero disables filtering.' if self.hold_jitter_supported else 'Slider mode only on this firmware. Higher values allow more movement during a tap; lower values start swipes sooner. Default: 50. Hold-mode support requires the newer Main firmware.')
        self.mode_hint.setText('Hold: keep the existing one-second end hold and centre-tap behavior. Moving across the bar holds the selected direction until release.' if self.hold.isChecked() else
                               'Slider: swipe left or right for repeated presses. Holding still does not repeat. Small movement remains a tap. Borderline swipes require confirmation; clear swipes keep the current stepping.')

    def set_values(self, values):
        was_loading = self.loading
        self.loading = True
        for name, key in self.keys.items():
            key.set_keycode(Keycode.serialize(values[name]))
        (self.hold, self.slider)[values['mode']].setChecked(True)
        self.sensitivity.setValue(values['sensitivity'])
        self.tap_jitter.setValue(values['tap_jitter'])
        self.refresh_labels()
        self.loading = was_loading

    def values(self):
        return dict(mode=self.mode_group.checkedId(), sensitivity=self.sensitivity.value(), tap_jitter=self.tap_jitter.value(),
                    **{name: Keycode.deserialize(key.keycode, reraise=True) for name, key in self.keys.items()})

    def reload(self):
        self.apply_timer.stop()
        self.save_timer.stop()
        self.client = None
        self.loading = True
        try:
            client = TouchBarClient(self.keyboard)
            caps = client.capabilities()
            self.hold_jitter_supported = caps.get('hold_jitter', False)
            values, self.revision = client.read()
            self.set_values(values)
            self.modified = False
            if caps['error']:
                raise RuntimeError('Main settings storage error; edits disabled.')
            self.client = client
            self.poll_save()
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(str(error))
        finally:
            self.loading = False
            self.controls.setEnabled(self.client is not None)

    def mark_dirty(self, *args):
        self.refresh_labels()
        if self.loading or not self.client:
            return
        self.modified = True
        self.status.setText('Applying live…')
        self.apply_timer.start(180)

    def report_status(self, status):
        if status['error']:
            self.status.setText('Persistence failed. Live settings may not survive reconnection.')
        elif status['pending']:
            self.status.setText('Applied live; saving. Pause typing briefly and keep connected until Saved appears.')
        else:
            self.status.setText('Saved — keyboard acknowledgement and readback verified.')

    def apply_live(self):
        if not self.client or not self.modified:
            return False
        try:
            status = self.client.apply_live(self.revision, **self.values())
            self.revision = status['revision']
            self.modified = False
            self.report_status(status)
            if status['pending']:
                self.save_timer.start()
            return True
        except (OSError, RuntimeError, ValueError) as error:
            self.apply_timer.stop()
            self.save_timer.stop()
            self.client = None
            self.controls.setEnabled(False)
            self.status.setText(str(error) + ' Switch away and reopen this tab before editing; no change was retried.')
            return False

    def poll_save(self):
        if not self.client or self.modified:
            return
        try:
            status = self.client.status()
            self.report_status(status)
            if status['pending']:
                self.save_timer.start()
            else:
                self.save_timer.stop()
        except (OSError, RuntimeError, ValueError) as error:
            self.save_timer.stop()
            self.status.setText(str(error))
