# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QFormLayout, QCheckBox, QSpinBox, QLabel
from editor.basic_editor import BasicEditor
from vial_device import VialKeyboard
from vi_al_addons.my2k.sleep_mode_protocol import SleepModeClient


class SleepMode(BasicEditor):
    def __init__(self, layout_editor):
        super().__init__()
        self.keyboard = self.client = None
        self.loading = False
        self.revision = 0
        self.modified = False
        self.apply_timer = QTimer(self)
        self.apply_timer.setSingleShot(True)
        self.apply_timer.timeout.connect(self.apply_live)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self.poll)
        page = QWidget()
        layout = QVBoxLayout(page)
        self.controls = QGroupBox('Sleep Mode')
        form = QFormLayout(self.controls)
        self.enabled = QCheckBox('Enable sleep for RGB and both displays')
        self.minutes = QSpinBox()
        self.minutes.setRange(5, 120)
        self.minutes.setSuffix(' minutes')
        self.minutes.setValue(15)
        self.minutes.setKeyboardTracking(False)
        form.addRow(self.enabled)
        form.addRow('Sleep after inactivity', self.minutes)
        self.enabled.toggled.connect(self.changed)
        self.minutes.valueChanged.connect(self.changed)
        layout.addWidget(self.controls)
        note = QLabel('Keyboard input always stays active. Any key wakes the lights and both screens, and types normally. Changes apply and save automatically.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel('Connect a supported MY-2K keyboard.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.addWidget(page)
        self.controls.setEnabled(False)

    def valid(self):
        return bool(isinstance(self.device, VialKeyboard) and self.device.keyboard and
                    getattr(self.device.keyboard, 'amk_rgb_indicator', None) and
                    tuple(i.get('index') for i in self.device.keyboard.amk_rgb_indicator.get('indicators', [])) == (125, 126, 112, 64, 65, 127))

    def rebuild(self, device):
        self.apply_timer.stop()
        self.poll_timer.stop()
        self.client = self.keyboard = None
        self.controls.setEnabled(False)
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

    def activate(self):
        if not self.keyboard:
            return
        self.loading = True
        self.controls.setEnabled(False)
        self.client = None
        try:
            c = SleepModeClient(self.keyboard)
            caps = c.capabilities()
            values, self.revision = c.read()
            self.enabled.setChecked(values['enabled'])
            self.minutes.setValue(values['minutes'])
            self.modified = False
            if not caps['aux_supported']:
                raise RuntimeError('Matching Sleep AUX firmware is not ready. Saved settings are unchanged.')
            self.client = c
            self.controls.setEnabled(True)
            self.poll()
            self.poll_timer.start()
        except (OSError, RuntimeError, ValueError) as e:
            self.status.setText(str(e))
        finally:
            self.loading = False

    def deactivate(self):
        self.apply_timer.stop()
        if self.modified:
            self.apply_live()
        self.poll_timer.stop()

    def changed(self, *args):
        if self.loading or not self.client:
            return
        self.modified = True
        self.status.setText('Applying…')
        self.apply_timer.start(200)

    def apply_live(self):
        if not self.client or not self.modified:
            return
        try:
            s = self.client.apply(self.revision, enabled=self.enabled.isChecked(), minutes=self.minutes.value())
            self.revision = s['revision']
            self.modified = False
            self.poll()
        except (OSError, RuntimeError, ValueError) as e:
            self.apply_timer.stop()
            self.poll_timer.stop()
            self.client = None
            self.controls.setEnabled(False)
            self.status.setText(str(e))

    def poll(self):
        if not self.client or self.modified:
            return
        try:
            s = self.client.status()
            if s['save_error']:
                self.status.setText('Settings save failed; keep connected and inspect diagnostics.')
            elif s['aux_error']:
                self.status.setText('Display sleep/wake failed; keyboard typing remains active. Check diagnostics.')
            elif s['save_pending']:
                self.status.setText('Applied and read back; saving. Pause typing briefly until Saved appears.')
            elif s['command_pending']:
                self.status.setText('Saved — changing display state…')
            else:
                self.status.setText('Saved — ' + ('lights and displays asleep.' if s['actual'] == 1 else 'keyboard, lights and displays awake.'))
        except (OSError, RuntimeError, ValueError) as e:
            self.poll_timer.stop()
            self.status.setText(str(e))
