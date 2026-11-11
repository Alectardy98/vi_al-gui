# SPDX-License-Identifier: GPL-3.0-or-later
"""Native utility capabilities, with one bounded HID worker and no disk logging."""
from collections import deque
import time
from PyQt5.QtCore import Qt, QObject, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QGroupBox, QComboBox, QSpinBox, QTableWidget,
                            QTableWidgetItem, QHeaderView, QMessageBox, QStackedWidget, QSlider)
from editor.basic_editor import BasicEditor
from util import KeycodeDisplay
from .protocol import Client, supported
from .widgets import SensorKeyboard, SignalGraph


def table(columns):
    widget = QTableWidget(0, len(columns))
    widget.setHorizontalHeaderLabels(columns)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    widget.setEditTriggers(QTableWidget.NoEditTriggers)
    return widget


def cell(text):
    item = QTableWidgetItem(str(text))
    item.setTextAlignment(Qt.AlignCenter)
    return item


class Page(BasicEditor):
    def __init__(self, controller, section):
        super().__init__()
        self.controller = self.addon_controller = controller
        self.section = section

    def valid(self):
        keyboard = getattr(self.device, 'keyboard', None)
        return keyboard is not None and supported(keyboard)

    def rebuild(self, device):
        super().rebuild(device)
        self.controller.bind(device)

    def activate(self):
        self.controller.activate(self.section)

    def deactivate(self):
        self.controller.deactivate()


class Job(QThread):
    def __init__(self, controller, operation, args):
        super().__init__(controller)
        self.client, self.keyboard = controller.client, controller.keyboard
        self.operation, self.args = operation, args
        self.result = self.error = None

    def run(self):
        try:
            if self.operation == 'connect':
                self.result = Client(self.keyboard).connect()
            elif self.operation in ('keys', 'levels'):
                levels = None
                if self.operation == 'levels':
                    levels = self.client.levels()
                    physical = self.client.physical_keypresses()
                    logical = {position for pad in physical
                               if (position := self.client.logical_position(pad)) is not None}
                else:
                    logical, physical = self.client.keypresses()
                self.result = logical, physical, levels
            else:
                self.result = getattr(self.client, self.operation)(*self.args)
        except Exception as error:
            self.error = error


class Controller(QObject):
    busy_changed = pyqtSignal(bool)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.device = self.keyboard = self.client = self.worker = None
        self.section = None
        self.closing = False
        self.pending = deque(maxlen=8)
        self.values, self.logical, self.physical = {}, set(), set()
        self.position = (0, 0)
        self.level_frames = 0
        self.last_level_time = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)
        self.general = Page(self, 'general')
        self.calibration = Page(self, 'calibration')
        self.sensors = Page(self, 'sensors')
        self.pages = (self.general, self.calibration, self.sensors)
        self.statuses, self.previews, self.views, self.matrices = [], {}, {}, {}
        self.build_general()
        self.build_calibration()
        self.build_monitor(self.sensors, 'sensors')
        for page in self.pages:
            status = QLabel('Select a Leyden Jar keyboard to read its native diagnostics.')
            status.setWordWrap(True)
            self.statuses.append(status)
            page.addWidget(status)
        window.layout_editor.changed.connect(self.refresh_layout)

    def build_general(self):
        self.information = table(['Property', 'Keyboard value'])
        self.general.addWidget(self.information, 1)
        row = QHBoxLayout()
        for title, operation in [('Reload information', 'refresh_bins'),
                                 ('Restart and recalibrate', 'reboot'),
                                 ('Enter bootloader', 'enter_bootloader'),
                                 ('Clear EEPROM', 'erase_eeprom')]:
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, op=operation: self.action(op))
            row.addWidget(button)
        self.general.addLayout(row)
        self.output = QPushButton('Keyboard output enabled')
        self.output.setCheckable(True)
        self.output.clicked.connect(self.change_output)
        self.output.setEnabled(False)
        self.general.addWidget(self.output)
        note = QLabel('Native startup calibration remains automatic. Clearing EEPROM resets QMK/Vial settings; '
                      'bootloader and restart actions intentionally disconnect the keyboard.')
        note.setWordWrap(True)
        self.general.addWidget(note)

    def preview(self, section):
        preview = SensorKeyboard(self.window.layout_editor)
        preview.clicked.connect(lambda: self.choose_preview(section))
        self.previews[section] = preview
        return preview

    def build_calibration(self):
        title = QLabel('Calibrate key sensitivity')
        title.setStyleSheet('font-size: 18px; font-weight: bold;')
        self.calibration.addWidget(title)
        intro = QLabel('The keyboard calibrates automatically at startup. Click a key below to inspect its live signal '
                       'and adjust the sensitivity group it belongs to. A group shares one trigger level across several keys.')
        intro.setWordWrap(True)
        self.calibration.addWidget(intro)
        live_row = QHBoxLayout()
        self.live_updates = QPushButton('Live readings on')
        self.live_updates.setCheckable(True)
        self.live_updates.setChecked(True)
        self.live_updates.toggled.connect(self.change_live_updates)
        self.live_state = QLabel('Waiting for the first live reading…')
        live_row.addWidget(self.live_updates)
        live_row.addWidget(self.live_state, 1)
        self.calibration.addLayout(live_row)
        layout = QHBoxLayout()
        layout.addWidget(self.preview('calibration'), 5)
        right = QVBoxLayout()
        right.addWidget(QLabel('Sensitivity groups · click a row to select'))
        self.bins = table(['Group', 'Rest', 'Trigger', 'Live', 'Keys'])
        self.bins.verticalHeader().hide()
        self.bins.setSelectionBehavior(QTableWidget.SelectRows)
        self.bins.setSelectionMode(QTableWidget.SingleSelection)
        self.bins.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.bins.cellClicked.connect(lambda row, col: self.bin_number.setValue(row))
        for col, text in enumerate(('Group ID, not a keyboard layer.', 'Startup median for this group. It stays fixed until recalibration.',
                                    'Signal level used to decide whether keys in this group are pressed.',
                                    'Current lowest–highest signal among the group’s keys.', 'Number of keys sharing this trigger.')):
            self.bins.horizontalHeaderItem(col).setToolTip(text)
        right.addWidget(self.bins)
        help_text = QLabel('Rest = the startup reference; it does not move while you type.\n'
                           'Live range = current readings, which change as keys move.\n'
                           'Trigger = the value you can change below.')
        help_text.setWordWrap(True)
        right.addWidget(help_text)
        right.addStretch(1)
        layout.addLayout(right, 2)
        self.calibration.addLayout(layout, 1)
        legend = QLabel('Green: pressed   ·   Blue: shares the selected group   ·   Amber: within 3 counts of the trigger')
        legend.setWordWrap(True)
        self.calibration.addWidget(legend)
        self.selected_signal = QLabel('Click a key to choose its sensitivity group.')
        self.selected_signal.setWordWrap(True)
        self.calibration.addWidget(self.selected_signal)
        settings = self.calibration_settings = QGroupBox('Tune the selected group · temporary until keyboard restart')
        box = QVBoxLayout(settings)
        row = QHBoxLayout()
        self.bin_number = QSpinBox()
        self.bin_number.setPrefix('Group ')
        self.bin_number.valueChanged.connect(self.select_bin)
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 1023)
        self.threshold.setSuffix(' signal counts')
        self.threshold.valueChanged.connect(self.edit_threshold)
        self.trigger_slider = QSlider(Qt.Horizontal)
        self.trigger_slider.setRange(0, 1023)
        self.trigger_slider.valueChanged.connect(self.threshold.setValue)
        self.trigger_slider.setMinimumWidth(180)
        self.apply_threshold = QPushButton('Apply to this group')
        self.apply_threshold.clicked.connect(lambda: self.submit('set_threshold', self.bin_number.value(), self.threshold.value()))
        recalibrate = QPushButton('Restart and recalibrate')
        recalibrate.clicked.connect(lambda: self.action('reboot'))
        row.addWidget(self.bin_number)
        row.addWidget(self.trigger_slider, 1)
        row.addWidget(self.threshold)
        row.addWidget(self.apply_threshold)
        row.addWidget(recalibrate)
        box.addLayout(row)
        self.sensitivity_help = QLabel()
        self.sensitivity_help.setWordWrap(True)
        box.addWidget(self.sensitivity_help)
        self.edit_state = QLabel('Select a connected keyboard first.')
        self.edit_state.setWordWrap(True)
        box.addWidget(self.edit_state)
        self.restore_calibration = QPushButton('Restore calibration defaults')
        self.restore_calibration.setToolTip('Clear saved calibration offsets only. Keymaps, macros and other QMK/Vial settings are preserved.')
        self.restore_calibration.clicked.connect(lambda: self.action('restore_defaults'))
        box.addWidget(self.restore_calibration, alignment=Qt.AlignHCenter)
        self.calibration.addWidget(settings)
        self.calibration_controls = (self.bin_number, self.threshold, self.trigger_slider, self.apply_threshold, recalibrate)
        self.enable_calibration(False)
        note = self.calibration_note = QLabel('Apply updates the selected group and checks readback. Changes are not saved: restart with all keys '
                      'released to restore automatic calibration. Live measurements briefly pause scanning; pause them before normal typing.')
        note.setWordWrap(True)
        self.calibration.addWidget(note)

    def build_monitor(self, page, section):
        row = QHBoxLayout()
        row.addWidget(QLabel('View'))
        view = QComboBox()
        view.addItems(['Keyboard layout', 'QMK matrix', 'Controller matrix'])
        view.setStyleSheet('QComboBox { combobox-popup: 0; }')
        view.setMaxVisibleItems(6)
        row.addWidget(view)
        if section == 'sensors':
            reset = QPushButton('Reset observed minimum / maximum')
            reset.clicked.connect(self.reset_extrema)
            row.addWidget(reset)
        row.addStretch(1)
        page.addLayout(row)
        if section == 'sensors':
            self.graph = SignalGraph()
            page.addWidget(self.graph, 1)
            self.signal_info = QLabel('Signal measurements use the native controller sweep, not physical distance.')
            self.signal_info.setWordWrap(True)
            page.addWidget(self.signal_info)
        stack = QStackedWidget()
        stack.addWidget(self.preview(section))
        for mode in ('logical', 'physical'):
            matrix = table([])
            matrix.cellClicked.connect(lambda row, col, m=mode: self.choose_matrix(m, row, col))
            self.matrices[section, mode] = matrix
            stack.addWidget(matrix)
        self.views[section] = stack
        view.currentIndexChanged.connect(stack.setCurrentIndex)
        page.addWidget(stack, 1)
        if section == 'sensors':
            label = QLabel('Each key shows its QMK row,column above the live signal reading. '
                           'Live levels measure electrical signal strength, not travel distance. Calibration and Live Sensors '
                           'sample while open; other pages stop the sweeps. History stays in RAM and is never logged to disk.')
            label.setWordWrap(True)
            page.addWidget(label)

    def status(self, message):
        for label in self.statuses:
            label.setText(message)

    def bind(self, device):
        keyboard = getattr(device, 'keyboard', None)
        if self.device is device and self.keyboard is keyboard:
            return
        self.deactivate()
        self.pending.clear()
        self.device, self.keyboard = device, keyboard if keyboard and supported(keyboard) else None
        self.client = None
        self.output.setEnabled(False)
        self.enable_calibration(False)
        self.level_frames = 0
        self.last_level_time = None
        self.live_state.setText('Waiting for the first live reading…')
        self.values.clear()
        self.logical.clear()
        self.physical.clear()
        self.graph.clear()
        self.information.setRowCount(0)
        self.bins.setRowCount(0)
        if self.keyboard:
            for preview in self.previews.values():
                preview.set_keys(self.keyboard.keys, self.keyboard.encoders)
            self.position = next(((k.row, k.col) for k in self.keyboard.keys
                                  if k.row is not None and k.col is not None and k.row >= 0 and k.col >= 0), (0, 0))
            self.refresh_layout()
        self.status('Open a diagnostic page to read controller information.')

    def activate(self, section):
        self.timer.stop()
        self.last_level_time = None
        self.section = section
        if self.client and section == 'calibration':
            self.ensure_group_position(self.bin_number.value())
        if self.keyboard and not self.client:
            self.submit('connect')
        elif self.client:
            self.poll()

    def deactivate(self):
        self.section = None
        self.timer.stop()

    def enable_calibration(self, enabled):
        for control in self.calibration_controls:
            control.setEnabled(enabled)
        self.restore_calibration.setEnabled(bool(enabled and self.client and self.client.has_persistence))

    def change_live_updates(self, enabled):
        self.last_level_time = None
        self.live_updates.setText('Live readings on' if enabled else 'Live readings paused')
        self.live_state.setText('Reading signals…' if enabled else 'Values frozen · press highlighting continues')
        if self.section == 'calibration':
            self.timer.stop()
            if not self.worker:
                self.poll()

    def action(self, operation):
        if operation == 'refresh_bins' and not self.client:
            self.submit('connect')
            return
        if operation in ('erase_eeprom', 'reboot', 'enter_bootloader', 'restore_defaults'):
            text = {'erase_eeprom': 'Clear all QMK/Vial EEPROM settings and restart?',
                    'reboot': 'Restart and perform automatic startup calibration? Release all keys first.',
                    'enter_bootloader': 'Enter the RP2040 UF2 bootloader? The keyboard will disconnect.',
                    'restore_defaults': 'Restore all calibration groups to their firmware defaults? Only saved sensitivity offsets are cleared; keymaps and macros are preserved.'}[operation]
            if QMessageBox.question(self.window, 'Leyden Jar', text) != QMessageBox.Yes:
                return
        self.submit(operation)

    def change_output(self, enabled):
        # The label always describes the last acknowledged state, even if a
        # transfer fails. Do not present a requested state as confirmed.
        self.output.setChecked(self.client.enabled if self.client else False)
        self.submit('set_enabled', enabled)

    def submit(self, operation, *args):
        if not self.keyboard or (operation != 'connect' and not self.client):
            return False
        if self.worker:
            if operation not in ('keys', 'levels', 'connect') and len(self.pending) < self.pending.maxlen:
                self.pending.append((operation, args))
            elif operation not in ('keys', 'levels', 'connect'):
                self.status('Controller is busy; wait for the current operation before trying again.')
            return False
        self.timer.stop()
        self.worker = Job(self, operation, args)
        self.worker.finished.connect(self.finished)
        self.busy_changed.emit(True)
        self.worker.start()
        return True

    def poll(self):
        if self.section == 'sensors' or (self.section == 'calibration' and self.live_updates.isChecked()):
            self.submit('levels')
        elif self.section == 'calibration':
            self.submit('keys')

    def finished(self):
        job, self.worker = self.worker, None
        try:
            if job.error:
                self.status(str(job.error) + ' Refresh the keyboard before retrying.')
                self.pending.clear()
                self.client = None
                self.output.setEnabled(False)
                self.enable_calibration(False)
                self.live_state.setText('Live readings stopped · reload the keyboard to reconnect')
                self.timer.stop()
            elif job.operation == 'connect':
                self.client = job.result
                self.output.setEnabled(True)
                self.enable_calibration(True)
                self.show_information()
                self.configure_matrices()
                self.show_bins()
                self.status('Connected. Select a key or a sensitivity group to tune.')
            elif job.operation in ('keys', 'levels'):
                previous = self.logical
                self.logical, self.physical, levels = job.result
                newly_pressed = self.logical - previous
                if newly_pressed and self.section != 'calibration':
                    self.choose(sorted(newly_pressed)[0])
                if levels is not None:
                    self.values = levels
                    now = time.monotonic()
                    interval = now - self.last_level_time if self.last_level_time is not None else None
                    self.last_level_time = now
                    self.level_frames += 1
                    if self.live_updates.isChecked():
                        self.live_state.setText('Live reading %s%s' %
                                                (self.level_frames, ' · %.1f updates/sec' % (1 / interval)
                                                 if interval else ' · values update automatically'))
                    self.update_bin_ranges()
                    self.show_signal()
                self.refresh_layout()
                self.update_matrices()
            elif job.operation in ('set_threshold', 'refresh_bins', 'restore_defaults'):
                self.show_bins(update_editor=job.operation != 'set_threshold' or job.args[0] == self.bin_number.value())
                if job.operation == 'set_threshold':
                    self.status('Trigger %s applied and verified for Group %s; %s.' %
                                (job.args[1], job.args[0], 'offset saved to EEPROM' if self.client.has_persistence
                                 else 'temporary until keyboard restart'))
                else:
                    self.status('Calibration defaults restored and verified; keymaps preserved.' if job.operation == 'restore_defaults'
                                else 'Sensitivity groups read from keyboard.')
            elif job.operation == 'set_enabled':
                self.show_information()
                self.status('Keyboard output state verified by readback.')
            else:
                self.deactivate()
                self.client = None
                self.output.setEnabled(False)
                self.enable_calibration(False)
                self.pending.clear()
                self.status('Command sent. The keyboard disconnects without a reply; reconnect/refresh after restart.')
        finally:
            job.deleteLater()
            self.busy_changed.emit(False)
            if not self.closing and self.client:
                if self.pending:
                    operation, args = self.pending.popleft()
                    self.submit(operation, *args)
                elif self.section in ('calibration', 'sensors'):
                    live = self.section == 'sensors' or (self.section == 'calibration' and self.live_updates.isChecked())
                    self.timer.start(0 if job.operation == 'connect' else 400 if live else 70)

    def show_information(self):
        c, d = self.client, self.client.details
        uid = self.keyboard.keyboard_id
        if isinstance(uid, int):
            uid = uid.to_bytes(8, 'little')
        data = [('Product', getattr(self.keyboard, 'name', 'Leyden Jar')),
                ('Native protocol', '.'.join(map(str, c.version))),
                ('Vial protocol', str(getattr(self.keyboard, 'vial_protocol', 'Unknown'))),
                ('Vial UID', uid.hex()),
                ('QMK matrix', '%s rows × %s columns' % (d.rows, d.cols)),
                ('Controller matrix', '%s rows × %s columns' % (d.physical_rows, d.physical_cols)),
                ('Switch technology', 'Beamspring' if d.technology else 'Model F'),
                ('Mapping', ('Leyden Jar', 'xwhatsit', 'wcass')[c.mapping_type]),
                ('Row mapping', ', '.join(map(str, c.row_map))),
                ('Column mapping', ', '.join('—' if n == 255 else str(n) for n in c.col_map)),
                ('Calibration bins', str(d.bins)), ('Split side', c.side or 'Not reported'),
                ('Persistence', 'QMK EEPROM; calibration offsets saved across restarts' if c.has_persistence
                 else 'Keymaps/settings: QMK EEPROM; thresholds: automatic at startup')]
        for name, value in getattr(self.keyboard, 'usb_descriptor', {}).items():
            data.append(('HID ' + name.replace('_', ' '), value.decode(errors='replace')
                         if isinstance(value, bytes) else str(value)))
        self.information.setRowCount(len(data))
        for row, (name, value) in enumerate(data):
            self.information.setItem(row, 0, cell(name))
            self.information.setItem(row, 1, cell(value))
        self.output.blockSignals(True)
        self.output.setChecked(c.enabled)
        self.output.setText('Keyboard output enabled' if c.enabled else 'Keyboard output disabled')
        self.output.blockSignals(False)

    def show_bins(self, update_editor=True):
        c = self.client
        self.calibration_settings.setTitle('Tune the selected group · ' +
                                          ('saved across restarts' if c.has_persistence else 'temporary until keyboard restart'))
        self.apply_threshold.setText('Apply and save' if c.has_persistence else 'Apply to this group')
        self.calibration_note.setText(
            'Apply and save stores the offset from Rest in EEPROM and verifies readback. Startup calibration still runs. '
            'Restore calibration defaults clears only those overrides. Editing alone sends no update. '
            'Pause live readings before normal typing.' if c.has_persistence else
            'Apply updates the selected group and checks readback. This older firmware keeps changes only until restart. '
            'Persistent settings and Restore defaults require updated firmware. Pause live readings before normal typing.')
        self.bins.setRowCount(c.details.bins)
        for row, threshold in enumerate(c.thresholds):
            for col, value in enumerate((row, c.references[row], threshold, '—',
                                         sum(n == row for n in c.bin_map.values()))):
                self.bins.setItem(row, col, cell(value))
        # Fit every group using the current Qt font/style metrics, rather than
        # capping the table at 300 px and hiding the final rows behind a scroll.
        self.bins.resizeRowsToContents()
        self.bins.setFixedHeight(max(self.bins.horizontalHeader().height(),
                                     self.bins.horizontalHeader().sizeHint().height())
                                 + self.bins.verticalHeader().length()
                                 + 2 * self.bins.frameWidth())
        self.bin_number.setMaximum(c.details.bins - 1)
        self.trigger_slider.setInvertedAppearance(bool(c.details.technology))
        self.sensitivity_help.setText(
            ('Model F: lower trigger = more sensitive; higher trigger = less sensitive. '
             if not c.details.technology else
             'Beamspring: higher trigger = more sensitive; lower trigger = less sensitive. ') +
            'This is an electrical threshold, not a travel distance or a percentage.')
        self.update_bin_ranges()
        if update_editor:
            self.select_bin(self.bin_number.value())

    def update_bin_ranges(self):
        if not self.client:
            return
        for number in range(self.client.details.bins):
            values = [value for pad, value in self.values.items() if self.client.bin_map.get(pad) == number]
            item = self.bins.item(number, 3)
            if item:
                item.setText('%s–%s' % (min(values), max(values)) if values else '—')

    def select_bin(self, number):
        if self.client and 0 <= number < len(self.client.thresholds):
            self.threshold.setValue(self.client.thresholds[number])
            self.edit_threshold(self.threshold.value())
            self.bins.selectRow(number)
            self.ensure_group_position(number)
            self.refresh_layout()

    def ensure_group_position(self, number):
        mapped = self.client.physical_position(self.position)
        if self.client.bin_map.get(mapped) != number:
            position = next(((key.row, key.col) for key in self.keyboard.keys
                             if key.row is not None and key.col is not None
                             and self.client.bin_map.get(self.client.physical_position((key.row, key.col))) == number), None)
            if position is not None:
                self.choose(position, select_group=False)

    def edit_threshold(self, value):
        self.trigger_slider.blockSignals(True)
        self.trigger_slider.setValue(value)
        self.trigger_slider.blockSignals(False)
        if self.client:
            number = self.bin_number.value()
            applied = self.client.thresholds[number]
            count = sum(n == number for n in self.client.bin_map.values())
            self.edit_state.setText(('Not applied yet · click Apply to this group. ' if value != applied else 'Current applied setting. ') +
                                    'Group %s affects %s key%s.' %
                                    (number, count, '' if count == 1 else 's'))
            unsaved_offset = (self.client.has_persistence and
                              value - self.client.references[number] != self.client.offsets[number])
            self.apply_threshold.setEnabled(value != applied or unsaved_offset)

    def configure_matrices(self):
        d = self.client.details
        for (section, mode), widget in self.matrices.items():
            rows, cols = (d.rows, d.cols) if mode == 'logical' else (d.physical_rows, d.physical_cols)
            widget.setRowCount(rows)
            widget.setColumnCount(cols)
            widget.setHorizontalHeaderLabels(list(map(str, range(cols))))
            widget.setVerticalHeaderLabels(list(map(str, range(rows))))
            for row in range(rows):
                for col in range(cols):
                    widget.setItem(row, col, cell('—'))

    def update_matrices(self):
        for (section, mode), widget in self.matrices.items():
            pressed = self.logical if mode == 'logical' else self.physical
            for row in range(widget.rowCount()):
                for col in range(widget.columnCount()):
                    physical = self.client.physical_position((row, col)) if mode == 'logical' else (row, col)
                    value = self.values.get(physical, '—')
                    item = widget.item(row, col)
                    number = self.client.bin_map.get(physical, 255)
                    if number == 255:
                        value = 'unused'
                    item.setText(str(value) if section == 'sensors' else '●' if (row, col) in pressed else '·')
                    item.setBackground(QBrush(QColor('#278e54')) if (row, col) in pressed else QBrush())
                    item.setToolTip(self.signal_description(physical))

    def refresh_layout(self):
        if not self.keyboard:
            return
        for section, preview in self.previews.items():
            preview.update_layout()
            preview.active_key = None
            group, near = set(), set()
            for key in preview.widgets:
                position = key.desc.row, key.desc.col
                if None in position or min(position) < 0:
                    continue
                mapped = self.client.physical_position(position) if self.client else None
                coordinates = '%s,%s' % position
                value = self.values.get(mapped, '—')
                key.setText('%s\n%s' % (coordinates, value) if section == 'sensors'
                            else str(self.values.get(mapped, coordinates)))
                key.setPressed(position in self.logical)
                if position == self.position:
                    preview.active_key = key
                if self.client:
                    number = self.client.bin_map.get(mapped, 255)
                    if number == self.bin_number.value():
                        group.add(position)
                    if number != 255 and mapped in self.values and abs(self.values[mapped] - self.client.thresholds[number]) <= 3:
                        near.add(position)
                key.setToolTip('QMK %s,%s · controller %s\n%s' %
                               (*position, mapped, self.signal_description(mapped)))
            preview.group_positions = group if preview is self.previews['calibration'] else frozenset()
            preview.near_threshold_positions = near
            preview.update()
        self.show_selected_signal()

    def choose_preview(self, section):
        key = self.previews[section].active_key
        if key and key.desc.row is not None and key.desc.col is not None:
            self.choose((key.desc.row, key.desc.col))

    def choose_matrix(self, mode, row, col):
        if not self.client:
            return
        position = self.client.logical_position((row, col)) if mode == 'physical' else (row, col)
        if position is not None:
            self.choose(position)

    def choose(self, position, select_group=True):
        if position != self.position:
            self.position = position
            self.graph.clear()
        if select_group and self.client and self.section == 'calibration':
            number = self.client.bin_map.get(self.client.physical_position(position), 255)
            if number != 255:
                self.bin_number.setValue(number)
        self.refresh_layout()

    def show_selected_signal(self):
        if not self.client:
            return
        mapped = self.client.physical_position(self.position)
        number = self.client.bin_map.get(mapped, 255)
        name = 'Key %s,%s' % self.position
        code = getattr(self.keyboard, 'layout', {}).get((0, *self.position))
        if code:
            name = KeycodeDisplay.get_label(code) or name
        direct = self.client.details.direct_key
        if direct and self.position == direct[:2]:
            self.selected_signal.setText('%s · digital switch GPIO%s · %s' %
                                         (name, direct[2], 'pressed' if self.position in self.logical else 'released'))
        elif number == 255:
            self.selected_signal.setText('%s · unused controller pad' % name)
        else:
            self.selected_signal.setText('%s · Group %s · signal %s · trigger %s · %s' %
                                         (name, number, self.values.get(mapped, '—'), self.client.thresholds[number],
                                          'pressed' if self.position in self.logical else 'released'))

    def show_signal(self):
        mapped = self.client.physical_position(self.position)
        direct = self.client.details.direct_key
        if direct and self.position == direct[:2]:
            self.graph.clear()
            self.signal_info.setText('Digital switch · GPIO%s · %s · no capacitive signal or threshold' %
                                     (direct[2], 'pressed' if self.position in self.logical else 'released'))
            return
        if mapped not in self.values:
            return
        number = self.client.bin_map[mapped]
        threshold = self.client.thresholds[number] if number != 255 else None
        value = self.values[mapped]
        self.graph.feed(value, threshold)
        self.signal_info.setText('QMK %s,%s → controller %s,%s · signal %s · min %s · max %s · bin %s' %
                                 (*self.position, *mapped, value, self.client.minimum.get(mapped, '—'),
                                  self.client.maximum.get(mapped, '—'), number if number != 255 else 'unused'))
        self.signal_info.setText(self.signal_info.text() + '\n' + self.signal_description(mapped))

    def signal_description(self, physical):
        if not self.client or physical is None:
            return 'No controller mapping.'
        number = self.client.bin_map.get(physical, 255)
        if number == 255:
            return 'Unused controller pad; excluded from calibration.'
        threshold = self.client.thresholds[number]
        value = self.values.get(physical)
        margin = abs(value - threshold) if value is not None else None
        return ('Bin %s · threshold %s · distance from threshold %s counts%s\n'
                'Three-sample stable low / high: %s / %s' %
                (number, threshold, margin if margin is not None else '—',
                 ' (within 3 counts)' if margin is not None and margin <= 3 else '',
                 self.client.stable_low.get(physical, '—'), self.client.stable_high.get(physical, '—')))

    def reset_extrema(self):
        if self.client:
            self.client.reset_extrema()
        self.graph.clear()
