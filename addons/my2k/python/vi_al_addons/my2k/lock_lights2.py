# SPDX-License-Identifier: GPL-2.0-or-later
"""Live Lock Lights UI. No HID mutations during loading or device readback."""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
    QLabel, QCheckBox, QPushButton, QColorDialog, QHeaderView, QComboBox, QSpinBox,
    QScrollArea, QAbstractItemView)
from editor.basic_editor import BasicEditor
from vial_device import VialKeyboard
from vi_al_addons.my2k.lock_lights import RuleTable, color_button
from vi_al_addons.my2k.lock_lights2_protocol import LockLightsClient, TRIGGERS, EFFECTS

FIXED = (('Under Cap', ((1, 'Scroll Lock'), (0, 'Caps Lock'), (5, 'Num Lock'))),
         ('100NG', ((3, 'Caps Lock'), (4, 'Num Lock'))))


class LockLights(BasicEditor):
    def __init__(self, layout_editor):
        super().__init__()
        self.keyboard = self.client = None
        self.loading = True
        self.revision = 0
        self.modified = False
        self.fixed = {}
        self.apply_timer = QTimer(self)
        self.apply_timer.setSingleShot(True)
        self.apply_timer.timeout.connect(self.apply_live)
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(300)
        self.save_timer.timeout.connect(self.poll_save)
        page = QWidget()
        body = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(page)
        self.addWidget(scroll)
        hint = QLabel('Changes apply live and save automatically. No Sync or Update is needed. '
                      'Pause typing briefly to let a pending settings save finish.')
        hint.setWordWrap(True)
        body.addWidget(hint)
        groups = QHBoxLayout()
        for title, indicators in FIXED:
            group = QGroupBox(title)
            grid = QGridLayout(group)
            grid.addWidget(QLabel('Enabled / indicator'), 0, 1)
            grid.addWidget(QLabel('Color'), 0, 2)
            grid.addWidget(QLabel('Effect'), 0, 3)
            grid.addWidget(QLabel('Speed'), 0, 4)
            for row, (index, name) in enumerate(indicators, 1):
                marker = QLabel('●')
                marker.setStyleSheet('font-size:22px;color:%s;' % ('white' if title == 'Under Cap' else 'red'))
                enabled = QCheckBox(name)
                enabled.toggled.connect(self.mark_dirty)
                color = QPushButton()
                color.clicked.connect(lambda checked=False, b=color: self.choose_color(b, 'Lock light color'))
                effect = QComboBox()
                effect.addItems(EFFECTS)
                effect.currentIndexChanged.connect(self.mark_dirty)
                speed = self.speed_control()
                effect.currentIndexChanged.connect(lambda value, s=speed: s.setEnabled(value != 0))
                for col, widget in enumerate((marker, enabled, color, effect, speed)):
                    grid.addWidget(widget, row, col)
                self.fixed[index] = (enabled, color, effect, speed)
            grid.setColumnStretch(1, 1)
            groups.addWidget(group, 1)
        body.addLayout(groups)
        self.square = QGroupBox('LED Square')
        box = QVBoxLayout(self.square)
        label = QLabel('First matching enabled rule wins. Layer 1–3 rules follow actual QMK layer state immediately. '
                       'RGB Strips retains its separate active-layer controls.')
        label.setWordWrap(True)
        box.addWidget(label)
        self.table = RuleTable(0, 6)
        self.table.setHorizontalHeaderLabels(['Enabled', 'Trigger', 'Color', 'Effect', 'Speed', 'Priority'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setMinimumHeight(150)
        self.table.setMaximumHeight(340)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        box.addWidget(self.table)
        buttons = QHBoxLayout()
        self.add_btn = QPushButton('Add rule')
        self.remove_btn = QPushButton('Remove')
        self.up_btn = QPushButton('Move up')
        self.down_btn = QPushButton('Move down')
        for button, slot in ((self.add_btn, self.add_rule), (self.remove_btn, self.remove_rule),
                             (self.up_btn, lambda: self.move_rule(-1)), (self.down_btn, lambda: self.move_rule(1))):
            button.clicked.connect(slot)
            buttons.addWidget(button)
        box.addLayout(buttons)
        row = QHBoxLayout()
        self.fallback = QCheckBox('Fallback color when no rule matches')
        self.fallback.toggled.connect(self.mark_dirty)
        self.fallback_btn = QPushButton()
        self.fallback_btn.clicked.connect(lambda: self.choose_color(self.fallback_btn, 'Fallback color'))
        row.addWidget(self.fallback, 1)
        row.addWidget(self.fallback_btn)
        box.addLayout(row)
        body.addWidget(self.square)
        self.status = QLabel('Reading keyboard configuration…')
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        body.addStretch(1)
        self.loading = False

    def speed_control(self):
        speed = QSpinBox()
        speed.setRange(0, 15)
        speed.setToolTip('0: 4-second cycle; 15: 250-ms cycle. Solid ignores speed.')
        speed.valueChanged.connect(self.mark_dirty)
        return speed

    def valid(self):
        if not isinstance(self.device, VialKeyboard) or not self.device.keyboard:
            return False
        data = self.device.keyboard.amk_rgb_indicator
        return bool(data and tuple(i.get('index') for i in data.get('indicators', [])) == (125, 126, 112, 64, 65, 127))

    def rebuild(self, device):
        self.apply_timer.stop()
        self.save_timer.stop()
        self.keyboard = self.client = None
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.reload()

    def activate(self):
        if self.keyboard:
            self.reload()

    def deactivate(self):
        # An already edited value must not be silently discarded on tab change.
        if self.modified and self.client:
            self.apply_timer.stop()
            self.apply_live()
        self.save_timer.stop()

    def reload(self):
        self.apply_timer.stop()
        self.save_timer.stop()
        self.client = None
        self.loading = True
        try:
            client = LockLightsClient(self.keyboard)
            caps = client.capabilities()
            self.set_values(client.read())
            self.revision = caps['revision']
            self.client = client
            self.modified = False
            self.status.setText('Settings read from keyboard. Changes apply live and save automatically.')
            if caps['error']:
                self.status.setText('Settings read, but Main reports a storage error. Further writes are disabled.')
                self.client = None
            else:
                self.poll_save()
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(str(error))
        finally:
            self.loading = False
            for widget in (self.square, *[w for widgets in self.fixed.values() for w in widgets]):
                widget.setEnabled(self.client is not None)
            if self.client:
                self.refresh_speed_controls()

    def mark_dirty(self, *args):
        if self.loading or not self.client:
            return
        self.modified = True
        self.status.setText('Applying live…')
        self.apply_timer.start(180)

    def set_color(self, button, color):
        button.setProperty('rgb', tuple(color))
        color_button(button, color)

    def choose_color(self, button, title):
        chosen = QColorDialog.getColor(QColor(*button.property('rgb')), None, title)
        if chosen.isValid():
            self.set_color(button, (chosen.red(), chosen.green(), chosen.blue()))
            self.mark_dirty()

    def set_values(self, values):
        was_loading = self.loading
        self.loading = True
        for item, index in zip(values['fixed'], (1, 0, 5, 3, 4)):
            enabled, color, effect, speed = self.fixed[index]
            enabled.setChecked(item['enabled'])
            self.set_color(color, item['color'])
            effect.setCurrentIndex(item['effect'])
            speed.setValue(item['speed'])
        self.table.setRowCount(0)
        for rule in values['rules']:
            self.insert_rule(rule)
        self.fallback.setChecked(values['fallback_enabled'])
        self.set_color(self.fallback_btn, values['fallback'])
        self.loading = was_loading
        self.refresh_speed_controls()

    def refresh_speed_controls(self):
        for enabled, color, effect, speed in self.fixed.values():
            speed.setEnabled(effect.currentIndex() != 0)
        self.add_btn.setEnabled(self.table.rowCount() < 8)

    def values(self):
        fixed = []
        for index in (1, 0, 5, 3, 4):
            enabled, color, effect, speed = self.fixed[index]
            fixed.append(dict(enabled=enabled.isChecked(), color=tuple(color.property('rgb')),
                              effect=effect.currentIndex(), speed=speed.value()))
        rules = []
        for row in range(self.table.rowCount()):
            enabled, trigger, color, effect, speed, _ = [self.table.cellWidget(row, col) for col in range(6)]
            choice = trigger.currentIndex()
            rules.append(dict(enabled=enabled.isChecked(), trigger=min(choice, 4), layer=choice-3 if choice >= 4 else 0,
                              color=tuple(color.property('rgb')), effect=effect.currentIndex(), speed=speed.value()))
        return dict(rules=rules, fixed=fixed, fallback_enabled=self.fallback.isChecked(),
                    fallback=tuple(self.fallback_btn.property('rgb')))

    def insert_rule(self, rule):
        row = self.table.rowCount()
        self.table.insertRow(row)
        enabled = QCheckBox()
        enabled.setChecked(rule['enabled'])
        enabled.toggled.connect(self.mark_dirty)
        trigger = QComboBox()
        trigger.addItems(TRIGGERS)
        trigger.setCurrentIndex(rule['layer']+3 if rule['trigger'] == 4 else rule['trigger'])
        trigger.currentIndexChanged.connect(self.mark_dirty)
        color = QPushButton()
        self.set_color(color, rule['color'])
        color.clicked.connect(lambda checked=False, b=color: self.choose_color(b, 'LED Square color'))
        effect = QComboBox()
        effect.addItems(EFFECTS)
        effect.setCurrentIndex(rule['effect'])
        effect.currentIndexChanged.connect(self.mark_dirty)
        speed = self.speed_control()
        speed.setValue(rule['speed'])
        speed.setEnabled(rule['effect'] != 0)
        effect.currentIndexChanged.connect(lambda value: speed.setEnabled(value != 0))
        for col, widget in enumerate((enabled, trigger, color, effect, speed, QLabel(str(row+1)))):
            widget.setProperty('ruleRow', row)
            widget.installEventFilter(self.table)
            self.table.setCellWidget(row, col, widget)
        self.add_btn.setEnabled(self.table.rowCount() < 8)

    def add_rule(self):
        if self.table.rowCount() >= 8:
            return
        self.insert_rule(dict(trigger=0, layer=0, enabled=True, color=(0, 255, 0), effect=0, speed=8))
        self.table.selectRow(self.table.rowCount()-1)
        self.mark_dirty()

    def remove_rule(self):
        row = self.table.currentRow()
        if row < 0:
            return
        values = self.values()
        values['rules'].pop(row)
        self.set_values(values)
        self.mark_dirty()

    def move_rule(self, delta):
        row = self.table.currentRow()
        other = row+delta
        if row < 0 or not 0 <= other < self.table.rowCount():
            return
        values = self.values()
        values['rules'][row], values['rules'][other] = values['rules'][other], values['rules'][row]
        self.set_values(values)
        self.table.selectRow(other)
        self.mark_dirty()

    def apply_live(self):
        if not self.client or not self.modified:
            return False
        try:
            status = self.client.apply_live(self.revision, **self.values())
            self.revision = status['revision']
            self.modified = False
            # Do not rebuild widgets here: preserve editing focus/selection.
            self.report_status(status)
            if status['pending']:
                self.save_timer.start()
            return True
        except (OSError, RuntimeError, ValueError) as error:
            self.apply_timer.stop()
            self.save_timer.stop()
            self.status.setText(str(error)+' Switch away and reopen this tab before another attempt; no change was retried.')
            self.client = None
            return False

    def report_status(self, status):
        if status['flash_error'] or status['state'] == 3:
            self.status.setText('Live settings are active, but persistence failed. Do not disconnect expecting them to survive.')
        elif status['pending']:
            self.status.setText('Applied live; saving in background. Pause typing briefly; keep connected until Saved appears.')
        else:
            self.status.setText('Saved — acknowledged configuration readback matches Main settings.')

    def poll_save(self):
        if not self.client or self.modified:
            return
        try:
            status = self.client.status()
            self.report_status(status)
            if not status['pending']:
                self.save_timer.stop()
            elif not self.save_timer.isActive():
                self.save_timer.start()
        except (OSError, RuntimeError, ValueError) as error:
            self.save_timer.stop()
            self.status.setText(str(error))
