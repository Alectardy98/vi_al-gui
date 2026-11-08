# SPDX-License-Identifier: GPL-3.0-or-later
"""Native utility capabilities, with one bounded HID worker and no disk logging."""
from collections import deque
from PyQt5.QtCore import Qt, QObject, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QGroupBox, QComboBox, QSpinBox, QTableWidget,
                            QTableWidgetItem, QHeaderView, QMessageBox, QStackedWidget)
from editor.basic_editor import BasicEditor
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
                logical, physical = self.client.keypresses()
                levels = self.client.levels() if self.operation == 'levels' else None
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
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)
        self.general = Page(self, 'general')
        self.calibration = Page(self, 'calibration')
        self.sensors = Page(self, 'sensors')
        self.keypress = Page(self, 'keypress')
        self.pages = (self.general, self.calibration, self.sensors, self.keypress)
        self.statuses, self.previews, self.views, self.matrices = [], {}, {}, {}
        self.build_general()
        self.build_calibration()
        self.build_monitor(self.sensors, 'sensors')
        self.build_monitor(self.keypress, 'keypress')
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
        layout = QHBoxLayout()
        layout.addWidget(self.preview('calibration'), 3)
        self.bins = table(['Bin', 'Reference', 'Threshold', 'Pads'])
        layout.addWidget(self.bins, 2)
        self.calibration.addLayout(layout, 1)
        settings = QGroupBox('Calibration bins · session-only threshold override')
        row = QHBoxLayout(settings)
        self.bin_number = QSpinBox()
        self.bin_number.setPrefix('Bin ')
        self.bin_number.valueChanged.connect(self.select_bin)
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 1023)
        self.threshold.setSuffix(' DAC counts')
        apply = QPushButton('Apply threshold')
        apply.clicked.connect(lambda: self.submit('set_threshold', self.bin_number.value(), self.threshold.value()))
        refresh = QPushButton('Read signal levels')
        refresh.clicked.connect(lambda: self.submit('levels'))
        row.addWidget(self.bin_number)
        row.addWidget(self.threshold)
        row.addWidget(apply)
        row.addWidget(refresh)
        self.calibration.addWidget(settings)
        note = QLabel('Signal values appear on the keys. Physical variants follow the Layout tab. '
                      'Threshold changes are verified by readback and reset to automatic calibration at restart. '
                      'No unsupported persistent calibration settings are exposed.')
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
            label = QLabel('Live levels perform full native DAC sweeps. Only this page samples continuously; '
                           'leave it to stop sampling. History stays in a bounded RAM buffer and is never logged to disk.')
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
        self.section = section
        if self.keyboard and not self.client:
            self.submit('connect')
        elif self.client:
            self.poll()

    def deactivate(self):
        self.section = None
        self.timer.stop()

    def action(self, operation):
        if operation == 'refresh_bins' and not self.client:
            self.submit('connect')
            return
        if operation in ('erase_eeprom', 'reboot', 'enter_bootloader'):
            text = {'erase_eeprom': 'Clear all QMK/Vial EEPROM settings and restart?',
                    'reboot': 'Restart and perform automatic startup calibration? Release all keys first.',
                    'enter_bootloader': 'Enter the RP2040 UF2 bootloader? The keyboard will disconnect.'}[operation]
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
        if self.section == 'sensors':
            self.submit('levels')
        elif self.section in ('calibration', 'keypress'):
            self.submit('keys')

    def finished(self):
        job, self.worker = self.worker, None
        try:
            if job.error:
                self.status(str(job.error) + ' Refresh the keyboard before retrying.')
                self.pending.clear()
                self.client = None
                self.output.setEnabled(False)
                self.timer.stop()
            elif job.operation == 'connect':
                self.client = job.result
                self.output.setEnabled(True)
                self.show_information()
                self.configure_matrices()
                self.show_bins()
                self.status('Native Leyden Jar diagnostics connected. Calibration thresholds are session-only.')
            elif job.operation in ('keys', 'levels'):
                previous = self.logical
                self.logical, self.physical, levels = job.result
                newly_pressed = self.logical - previous
                if newly_pressed:
                    self.choose(sorted(newly_pressed)[0])
                if levels is not None:
                    self.values = levels
                    self.show_signal()
                self.refresh_layout()
                self.update_matrices()
            elif job.operation in ('set_threshold', 'refresh_bins'):
                self.show_bins()
                self.status('Threshold applied and verified; automatic startup calibration remains unchanged.'
                            if job.operation == 'set_threshold' else 'Calibration bins read from keyboard.')
            elif job.operation == 'set_enabled':
                self.show_information()
                self.status('Keyboard output state verified by readback.')
            else:
                self.deactivate()
                self.client = None
                self.output.setEnabled(False)
                self.pending.clear()
                self.status('Command sent. The keyboard disconnects without a reply; reconnect/refresh after restart.')
        finally:
            job.deleteLater()
            self.busy_changed.emit(False)
            if not self.closing and self.client:
                if self.pending:
                    operation, args = self.pending.popleft()
                    self.submit(operation, *args)
                elif self.section in ('calibration', 'sensors', 'keypress'):
                    self.timer.start(400 if self.section == 'sensors' else 70)

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
                ('Persistence', 'Keymaps/settings: QMK EEPROM; thresholds: automatic at startup')]
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

    def show_bins(self):
        c = self.client
        self.bins.setRowCount(c.details.bins)
        for row, threshold in enumerate(c.thresholds):
            for col, value in enumerate((row, c.references[row], threshold,
                                         sum(n == row for n in c.bin_map.values()))):
                self.bins.setItem(row, col, cell(value))
        self.bin_number.setMaximum(c.details.bins - 1)
        self.select_bin(self.bin_number.value())

    def select_bin(self, number):
        if self.client and 0 <= number < len(self.client.thresholds):
            self.threshold.setValue(self.client.thresholds[number])

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
        for preview in self.previews.values():
            preview.update_layout()
            for key in preview.widgets:
                position = key.desc.row, key.desc.col
                if None in position or min(position) < 0:
                    continue
                mapped = self.client.physical_position(position) if self.client else None
                key.setText(str(self.values.get(mapped, '%s,%s' % position)))
                key.setPressed(position in self.logical)
                key.setToolTip('QMK %s,%s · controller %s\n%s' %
                               (*position, mapped, self.signal_description(mapped)))
            preview.update()

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

    def choose(self, position):
        if position != self.position:
            self.position = position
            self.graph.clear()

    def show_signal(self):
        mapped = self.client.physical_position(self.position)
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
