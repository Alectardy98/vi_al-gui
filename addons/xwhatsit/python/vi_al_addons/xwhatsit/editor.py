# SPDX-License-Identifier: GPL-2.0-or-later
"""xwhatsit pages. Qt renders on the GUI thread; one worker owns HID at a time."""
from collections import deque
import time

from PyQt5.QtCore import Qt, QObject, QTimer, QThread, pyqtSignal, QSignalBlocker, QRectF, QSize, QPointF
from PyQt5.QtGui import QColor, QPainter, QPen, QPainterPath, QPalette
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                            QPushButton, QSlider, QGroupBox, QTableWidget,
                            QTableWidgetItem, QHeaderView, QMessageBox, QScrollArea, QFrame, QSizePolicy, QCheckBox)

from editor.basic_editor import BasicEditor
from widgets.keyboard_widget import KeyboardWidget
from .protocol import Client, Settings, KeysHeld, supported


class SignalGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(230)
        self.values = deque(maxlen=180)
        self.threshold = None
        self.lines = {'raw'}

    def clear(self):
        self.values.clear()
        self.update()

    def feed(self, value, threshold):
        self.values.append(value)
        self.threshold = threshold
        self.update()

    def set_line(self, name, enabled):
        if enabled:
            self.lines.add(name)
        else:
            self.lines.discard(name)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#15212d'))
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(50, 20, -15, -35)
        painter.setPen(QColor('#deebff'))
        painter.drawText(10, self.height()-10, 'Recent live signal · DAC counts')
        if not self.values:
            painter.drawText(bounds, Qt.AlignCenter, 'Press a key or click the keyboard to inspect its signal.')
            return
        values = list(self.values)
        limits = values + ([self.threshold] if self.threshold is not None else [])
        low, high = min(limits)-8, max(limits)+8
        def y(value):
            return bounds.bottom() - (value-low)/(high-low)*bounds.height()
        painter.setPen(QPen(QColor('#344354'), 1))
        for step in range(5):
            value = low + (high-low)*step/4
            line_y = y(value)
            painter.drawLine(round(bounds.left()), round(line_y), round(bounds.right()), round(line_y))
            painter.drawText(0, round(line_y)+4, str(round(value)))
        if self.threshold is not None:
            painter.setPen(QPen(QColor('#ffbd33'), 3, Qt.DashLine))
            painter.drawLine(round(bounds.left()), round(y(self.threshold)), round(bounds.right()), round(y(self.threshold)))
            painter.drawText(round(bounds.left()+5), round(y(self.threshold))-5, 'Calibration threshold')
        path = QPainterPath()
        for index, value in enumerate(values):
            x = bounds.left() + index/max(1, len(values)-1)*bounds.width()
            if index:
                path.lineTo(x, y(value))
            else:
                path.moveTo(x, y(value))
        if 'raw' in self.lines:
            painter.setPen(QPen(QColor('#2ee7ff'), 3))
            painter.drawPath(path)
        for name, value, color in (('minimum', min(values), '#c4d3ed'),
                                   ('maximum', max(values), '#fff09a')):
            if name in self.lines:
                painter.setPen(QPen(QColor(color), 2, Qt.DashLine))
                painter.drawLine(round(bounds.left()), round(y(value)), round(bounds.right()), round(y(value)))


class SensorKeyboard(KeyboardWidget):
    """Native Vial geometry, with the same centered sensor-key style as EC42."""
    def __init__(self, layout_editor):
        super().__init__(layout_editor)
        self.pressed_positions = set()
        self.setAutoFillBackground(False)

    def sizeHint(self):
        return QSize(1100, 300)

    def minimumSizeHint(self):
        return QSize(280, 140)

    def content_offset(self):
        return max(0., (QWidget.width(self)-self.width*self.scale)/2)

    def hit_test(self, pos):
        return super().hit_test(QPointF(pos)-QPointF(self.content_offset(), 0))

    def update_layout(self):
        self.scale = 1
        super().update_layout()
        self.scale = min(1.1, max(.1, QWidget.width(self)/max(1, self.width)))
        wanted = round(self.height*self.scale)+2
        if self.minimumHeight() != wanted:
            self.setFixedHeight(wanted)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.content_offset(), 0)
        for key in self.widgets:
            painter.save()
            painter.scale(self.scale, self.scale)
            painter.translate(key.shift_x, key.shift_y)
            painter.translate(key.rotation_x, key.rotation_y)
            painter.rotate(key.rotation_angle)
            painter.translate(-key.rotation_x, -key.rotation_y)
            held = (key.desc.row, key.desc.col) in self.pressed_positions
            color = QColor('#45ae70') if held else self.palette().color(QPalette.Button)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color.darker(120) if held else color)
            painter.drawPath(key.background_draw_path)
            painter.setPen(QPen(self.palette().color(QPalette.Highlight), 2)
                           if key is self.active_key else Qt.NoPen)
            painter.setBrush(color if held else color.lighter(120))
            painter.drawPath(key.foreground_draw_path)
            painter.setPen(self.palette().color(QPalette.ButtonText))
            painter.drawText(key.text_rect, Qt.AlignCenter, key.text)
            painter.restore()


class Job(QThread):
    def __init__(self, controller, operation, value):
        super().__init__(controller)
        self.client, self.keyboard = controller.client, controller.keyboard
        self.operation, self.value = operation, value
        self.result = self.error = None

    def run(self):
        try:
            if self.operation == 'connect':
                self.result = Client(self.keyboard).connect()
            elif self.operation == 'snapshot':
                self.result = self.client.snapshot(self.value)
            elif self.operation == 'frame':
                self.result = self.client.frame(*self.value)
            elif self.operation == 'apply':
                self.result = self.client.apply(self.value)
            elif self.operation == 'defaults':
                self.result = self.client.reset_defaults()
            elif self.operation == 'calibrate':
                self.result = self.client.recalibrate()
            elif self.operation == 'boot':
                self.client.enter_bootloader()
            elif self.operation == 'erase':
                self.client.erase_eeprom()
        except Exception as error:
            self.error = error


FIELDS = (
    ('settle', 'DAC settling time', 'µs', 1, 32,
     'Wait after changing the sensing threshold. More settling time can help unstable readings, but each scan takes longer.'),
    ('sample', 'Sample timing', 'steps', 1, 32,
     'Controls when each capacitive signal is sampled. Changing it can shift the readings; the keyboard recalibrates when saved. These are sampling steps, not milliseconds.'),
    ('initial', 'Startup averaging', 'samples', 0, 5,
     'Repeated measurements used to find the starting signal range. More samples can reduce noise, but startup calibration takes longer.'),
    ('per_key', 'Per-key averaging', 'samples', 0, 5,
     'Repeated measurements for each key during automatic calibration. More samples can stabilize the result, but calibration takes longer.'),
    ('groups', 'Calibration groups', 'groups', 1, 15,
     'Keys with similar released signals share a threshold. More groups can account for differences between keys, with extra scan work. The maximum is fixed by this firmware.'),
    ('margin', 'Threshold margin', 'DAC counts', 0, 4095,
     'Gap between the released signal and activation threshold. A larger margin needs more signal change and can reduce false triggers; too large can miss presses. It is not a distance in millimeters.'),
)


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


class Controller(QObject):
    busy_changed = pyqtSignal(bool)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.device = self.keyboard = self.client = self.worker = None
        self.section = None
        self.closing = self.loading = False
        self.pending = None
        self.position = (0, 0)
        self.pressed = set()
        self.last_samples = {}
        self.sampled_at = {}
        self.scan_index = 0
        self.released = deque(maxlen=32)
        self.last_held = None
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save_pending)
        self.calibration = Page(self, 'calibration')
        self.sensors = Page(self, 'sensors')
        self.general = Page(self, 'general')
        self.build_calibration()
        self.build_sensors()
        self.build_general()
        window.layout_editor.changed.connect(self.refresh_layout)

    @staticmethod
    def page_body(page):
        root = QWidget()
        body = QVBoxLayout(root)
        body.setSpacing(14)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(root)
        root.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        page.addWidget(scroll)
        return root, body

    def build_calibration(self):
        self.calibration_root, self.calibration_body = self.page_body(self.calibration)
        body = self.calibration_body
        self.info = QLabel('Open Calibration to read the keyboard’s sensing capabilities.')
        self.info.setWordWrap(True)
        body.addWidget(self.info)
        self.status = QLabel('No keyboard connected.')
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        hint = QLabel('Numbers on the keys are measured signal levels. Green = held; '
                      'click a key to follow it. Other keys refresh during idle time.')
        hint.setWordWrap(True)
        body.addWidget(hint)
        columns = QHBoxLayout()
        left = QVBoxLayout()
        self.preview = SensorKeyboard(self.window.layout_editor)
        self.preview.clicked.connect(self.select_key)
        left.addWidget(self.preview)
        self.summary = QLabel('Reading calibration values…')
        self.summary.setWordWrap(True)
        left.addWidget(self.summary)
        self.selection_label = QLabel('Click a key to follow its live signal.')
        self.selection_label.setWordWrap(True)
        left.addWidget(self.selection_label)
        self.calibration_controls = QGroupBox('Automatic calibration · saved automatically')
        self.calibration_controls.setObjectName('xwhatsitCalibrationActions')
        self.calibration_controls.setStyleSheet('QGroupBox#xwhatsitCalibrationActions { border: 2px solid #000000; border-radius: 5px; margin-top: 10px; padding: 12px; } QGroupBox#xwhatsitCalibrationActions::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }')
        grid = QGridLayout(self.calibration_controls)
        grid.setVerticalSpacing(10)
        self.defaults = QPushButton('Restore calibration defaults')
        self.defaults.setMinimumHeight(32)
        self.defaults.setMinimumWidth(260)
        self.defaults.clicked.connect(lambda: self.submit('defaults'))
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.defaults)
        actions.addStretch()
        grid.addLayout(actions, 0, 0, 1, 3)
        self.sliders, self.readouts = {}, {}
        self.explanations = {}
        for index, (name, title, unit, minimum, maximum, explanation) in enumerate(FIELDS):
            row = 1 + index*3
            slider = QSlider(Qt.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setMinimumWidth(180)
            slider.setEnabled(False)
            slider.setToolTip(explanation)
            value = QLabel('Not reported')
            value.setMinimumWidth(110)
            grid.addWidget(QLabel(title), row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value, row, 2)
            description = QLabel(explanation)
            description.setWordWrap(True)
            grid.addWidget(description, row+1, 0, 1, 3)
            if index < len(FIELDS)-1:
                grid.setRowMinimumHeight(row+2, 8)
            self.explanations[name] = description
            self.sliders[name], self.readouts[name] = slider, value
            slider.valueChanged.connect(self.edited)
        grid.setColumnStretch(1, 1)
        left.addWidget(self.calibration_controls)
        note = QLabel('Release all keys while calibration applies. Changes save after a short pause. '
                      'Automatic calibration still runs at startup using saved settings.')
        note.setWordWrap(True)
        left.addWidget(note)
        left.addStretch(1)
        columns.addLayout(left, 13)
        self.position_panel = QWidget(self.calibration_root)
        self.position_panel.setMinimumWidth(290)
        position = QVBoxLayout(self.position_panel)
        position.setContentsMargins(0, 0, 0, 0)
        position.addWidget(QLabel('Position / calibration values'))
        self.table_source = QLabel('Reading threshold groups from the keyboard…')
        self.table_source.setWordWrap(True)
        position.addWidget(self.table_source)
        self.values = QTableWidget(0, 4)
        self.values.setHorizontalHeaderLabels(['Position', 'Signal', 'Threshold', 'Group'])
        self.values.verticalHeader().setVisible(False)
        self.values.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.values.setMinimumHeight(390)
        self.values.setEditTriggers(QTableWidget.NoEditTriggers)
        self.values.cellClicked.connect(self.select_table)
        position.addWidget(self.values, 1)
        columns.addWidget(self.position_panel, 4)
        body.addLayout(columns, 1)

    def build_sensors(self):
        self.sensors_root, self.sensors_body = self.page_body(self.sensors)
        body = self.sensors_body
        body.setSpacing(8)
        self.sensor_info = QLabel('xwhatsit sensing utility')
        self.sensor_info.setWordWrap(True)
        body.addWidget(self.sensor_info)
        self.sensor_status = QLabel('Reading keyboard state…')
        self.sensor_status.setWordWrap(True)
        body.addWidget(self.sensor_status)
        intro = QLabel('Press a key to inspect it. The graph follows the newest detected key activity '
                       'and keeps showing that key after release. Green matrix cells show held keys.')
        intro.setWordWrap(True)
        body.addWidget(intro)
        self.sensor_summary = QLabel('Press a key to begin.')
        self.sensor_summary.setWordWrap(True)
        body.addWidget(self.sensor_summary)
        self.graph = SignalGraph()
        self.graph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        body.addWidget(self.graph, 1)
        legend = QLabel('Live signal: cyan • Calibration threshold: dashed amber. '
                        'Minimum/maximum are measured extremes in the visible history, not firmware actuation settings.')
        legend.setWordWrap(True)
        body.addWidget(legend)
        overlays = QHBoxLayout()
        for name in ('raw', 'minimum', 'maximum'):
            check = QCheckBox(name.capitalize())
            check.setChecked(name == 'raw')
            check.toggled.connect(lambda on, name=name: self.graph.set_line(name, on))
            overlays.addWidget(check)
        overlays.addStretch()
        body.addLayout(overlays)
        self.matrix = QTableWidget()
        self.matrix.setMinimumHeight(220)
        self.matrix.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.matrix.setEditTriggers(QTableWidget.NoEditTriggers)
        self.matrix.setSelectionMode(QTableWidget.SingleSelection)
        self.matrix.cellClicked.connect(self.select_matrix)
        self.matrix.horizontalHeader().setMinimumSectionSize(16)
        self.matrix.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.matrix.verticalHeader().setMinimumSectionSize(18)
        self.matrix.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        body.addWidget(self.matrix, 1)
        self.live_status = QLabel('Rows and columns are electrical matrix positions. Gray = sampled; green = held; '
                                 'dark = not sampled. Background reads pause during typing. USB snapshots can miss short taps. '
                                 'History stays in RAM only; GUI sensor refresh is separate from keyboard USB polling.')
        self.live_status.setWordWrap(True)
        body.addWidget(self.live_status)

    def build_general(self):
        self.general_info = QLabel('xwhatsit sensing utility')
        self.general_info.setWordWrap(True)
        self.general.addWidget(self.general_info)
        self.general_status = QLabel('Open a calibration page to connect.')
        self.general_status.setWordWrap(True)
        self.general.addWidget(self.general_status)
        self.boot = QPushButton('Enter bootloader')
        self.erase = QPushButton('Erase all EEPROM')
        self.boot.clicked.connect(lambda: self.submit('boot'))
        self.erase.clicked.connect(self.confirm_erase)
        self.general.addWidget(self.boot)
        self.general.addWidget(self.erase)
        text = QLabel('Erase all EEPROM removes Vial keymaps, macros and calibration overrides. '
                      'Reconnect afterward to initialize defaults. Restore calibration defaults on the Calibration page preserves keymaps.')
        text.setWordWrap(True)
        self.general.addWidget(text)
        self.general.addStretch(1)

    def set_status(self, text):
        self.status.setText(text)
        self.general_status.setText(text)
        self.sensor_status.setText(text)

    def bind(self, device):
        keyboard = getattr(device, 'keyboard', None)
        if self.device is device and self.keyboard is keyboard:
            return
        self.deactivate()
        self.device = device
        self.keyboard = keyboard if keyboard and supported(keyboard) else None
        self.save_timer.stop()
        self.client = None
        self.pending = None
        self.last_samples.clear()
        self.sampled_at.clear()
        self.scan_index = 0
        self.pressed.clear()
        self.graph.clear()
        self.values.setRowCount(0)
        for label in self.readouts.values():
            label.setText('Not reported')
        self.set_actions(False)
        if self.keyboard:
            self.preview.set_keys(self.keyboard.keys, self.keyboard.encoders)
            self.position = next(((key.row, key.col) for key in self.keyboard.keys if key.row is not None and key.row >= 0 and key.col >= 0), (0, 0))
            self.matrix.setRowCount(self.keyboard.rows)
            self.matrix.setColumnCount(self.keyboard.cols)
            self.matrix.setHorizontalHeaderLabels([str(i) for i in range(self.keyboard.cols)])
            self.matrix.setVerticalHeaderLabels([str(i) for i in range(self.keyboard.rows)])
            for row in range(self.keyboard.rows):
                for col in range(self.keyboard.cols):
                    item = QTableWidgetItem('—')
                    item.setTextAlignment(Qt.AlignCenter)
                    self.matrix.setItem(row, col, item)
            self.refresh_layout()

    def refresh_layout(self):
        if not self.keyboard:
            return
        self.preview.update_layout()
        visible = {(key.desc.row, key.desc.col) for key in self.preview.widgets if key.desc.row is not None and key.desc.row >= 0 and key.desc.col >= 0}
        if visible and self.position not in visible:
            self.choose(sorted(visible)[0])
        for key in self.preview.widgets:
            if key.desc.row is not None and key.desc.row >= 0:
                pos = (key.desc.row, key.desc.col)
                key.setText(str(self.last_samples.get(pos, '—')))
                key.tooltip = 'Matrix %s,%s · Measured signal in DAC counts; other keys refresh in rotation.' % pos
        self.preview.pressed_positions = self.pressed
        self.preview.update()

    def activate(self, section):
        self.section = section
        if not self.keyboard:
            return
        if self.client is None:
            self.submit('connect')
        if section in ('calibration', 'sensors'):
            self.timer.start()
        else:
            self.timer.stop()

    def deactivate(self):
        self.section = None
        self.timer.stop()
        if self.closing:
            self.save_timer.stop()

    def set_actions(self, online):
        extended = online and self.client and self.client.extension
        for slider in self.sliders.values():
            slider.setEnabled(bool(extended))
        self.defaults.setEnabled(bool(extended))
        self.boot.setEnabled(bool(online))
        self.erase.setEnabled(bool(online))

    def submit(self, operation, value=None):
        if self.worker is not None:
            if operation in ('calibrate', 'defaults'):
                self.pending = (operation, value)
                self.save_timer.start(1)
                self.set_status('Waiting for the current sensor read before applying calibration.')
            return False
        if not self.keyboard or (operation != 'connect' and self.client is None):
            return False
        if operation in ('defaults', 'erase'):
            # An explicit reset supersedes an older, debounced slider edit.
            self.pending = None
            self.save_timer.stop()
        job = Job(self, operation, value)
        self.worker = job
        self.busy_changed.emit(True)
        job.finished.connect(self.finished)
        job.start()
        return True

    def finished(self):
        job = self.worker
        self.worker = None
        try:
            if job.error:
                self.set_status(str(job.error))
                self.live_status.setText(str(job.error))
                if isinstance(job.error, KeysHeld) and job.operation in ('apply', 'defaults', 'calibrate'):
                    if self.pending is None:
                        self.pending = (job.operation, job.value)
                    self.save_timer.start(500)
                elif job.operation in ('apply', 'defaults', 'calibrate'):
                    self.timer.stop()
                    self.save_timer.stop()
                    self.pending = None
                    self.set_actions(False)
                    self.client = None
                    self.set_status(str(job.error) + ' Wait, then refresh the keyboard to read its actual state before editing again.')
                return
            if job.operation == 'connect':
                self.client = job.result
                self.connected()
            elif job.operation == 'snapshot':
                self.show_snapshot(job.value, *job.result)
            elif job.operation == 'frame':
                position, pressed, readings = job.result
                self.choose(position)
                for pos, value in readings.items():
                    if pos != position:
                        self.store_sample(pos, value)
                self.show_snapshot(position, pressed, readings.get(position))
            elif job.operation in ('apply', 'defaults', 'calibrate'):
                if self.pending is None:
                    self.load_settings(self.client.settings)
                self.set_status('Defaults restored; keymaps preserved.' if job.operation == 'defaults' else 'Calibration applied and verified.' if job.operation == 'calibrate' else 'Saved to keyboard and verified by readback.')
                self.show_thresholds()
            elif job.operation == 'boot':
                self.deactivate()
                self.set_status('Bootloader requested. The keyboard will disconnect.')
            elif job.operation == 'erase':
                self.deactivate()
                self.set_status('EEPROM cleared. Reconnect the keyboard to initialize defaults.')
                self.set_actions(False)
        finally:
            job.deleteLater()
            self.busy_changed.emit(False)
            if self.pending is not None and not self.closing and not self.save_timer.isActive():
                self.save_timer.start()
            # A one-shot timer may fire while connect/save still owns HID.
            # Every completion rearms it, not just completed sensor frames.
            if self.section in ('calibration', 'sensors') and not self.closing and self.client and self.pending is None:
                filling = any(pos not in self.last_samples for pos in self.client.thresholds)
                delay = 500 if job.error else 0 if filling and self.client.background_allowed else 100
                self.timer.start(delay)

    def connected(self):
        client = self.client
        self.info.setText('Automatic calibration: %s at startup · Calibration diagnostics built: %s\nFirmware utility protocol %s · %s sensor rows · DAC range 0–%s' %
                          ('enabled' if client.auto else 'disabled', 'not reported' if client.debug is None else 'yes' if client.debug else 'no', '.'.join(map(str, client.version)), client.sense_rows, client.dac_max))
        self.general_info.setText(self.info.text())
        self.sensor_info.setText(self.info.text())
        self.set_actions(True)
        if client.extension:
            self.sliders['groups'].setMaximum(client.max_groups)
            self.sliders['margin'].setMaximum(client.dac_max)
            self.load_settings(client.settings)
            self.set_status('Settings loaded from the keyboard. Changes save automatically after a short pause.')
        else:
            self.set_status('Legacy firmware: live signals and thresholds work without flashing. Adjustable settings require the optional XCAL firmware; no unsupported writes will be sent.')
            self.readouts['settle'].setText(str(client.settle)+' µs')
            self.readouts['sample'].setText(str(client.sample)+' steps')
        self.show_thresholds()

    def load_settings(self, settings):
        if settings is None:
            return
        self.loading = True
        try:
            for name, _, unit, *_ in FIELDS:
                value = getattr(settings, name)
                raw = value.bit_length()-1 if name in ('initial', 'per_key') else value
                with QSignalBlocker(self.sliders[name]):
                    self.sliders[name].setValue(raw)
                self.readouts[name].setText('%s %s' % (value, unit))
        finally:
            self.loading = False

    def edited(self):
        if self.loading or not self.client or not self.client.extension:
            return
        values = {name: (1 << slider.value() if name in ('initial', 'per_key') else slider.value()) for name, slider in self.sliders.items()}
        settings = Settings(**values)
        for name, _, unit, *_ in FIELDS:
            self.readouts[name].setText('%s %s' % (getattr(settings, name), unit))
        if self.worker is None and settings == self.client.settings:
            self.pending = None
            self.save_timer.stop()
            self.set_status('Settings match the keyboard; no save needed.')
            return
        self.pending = ('apply', settings)
        self.set_status('Change pending. Release all keys while it saves and recalibrates.')
        self.save_timer.start()

    def save_pending(self):
        if self.pending is None or self.closing:
            return
        if self.worker is not None:
            self.save_timer.start(100)
            return
        operation, value = self.pending
        self.pending = None
        self.submit(operation, value)

    def poll(self):
        if self.worker is None and self.client and self.pending is None:
            positions = sorted(self.client.thresholds)
            missing = [pos for pos in positions if pos not in self.last_samples]
            if missing:
                background = missing[:3]
            elif positions:
                background = [positions[self.scan_index % len(positions)]]
                self.scan_index += 1
            else:
                background = []
            self.submit('frame', (self.position, background))

    def choose(self, position):
        if position != self.position:
            self.position = position
            self.released.clear()
            self.last_held = None
            self.graph.clear()
        self.selection_label.setText('Following row %s, column %s.' % position)
        self.preview.active_key = next((key for key in self.preview.widgets
                                       if (key.desc.row, key.desc.col) == position), None)
        self.preview.update()

    def select_table(self, row, column):
        if 0 <= row < len(self.threshold_positions):
            self.choose(self.threshold_positions[row])

    def select_key(self):
        if self.preview.active_key is not None:
            desc = self.preview.active_key.desc
            self.choose((desc.row, desc.col))

    def select_matrix(self, row, col):
        self.choose((row, col))

    def show_snapshot(self, position, pressed, sample):
        added = pressed - self.pressed
        self.pressed = pressed
        if added:
            visible = {(key.desc.row, key.desc.col) for key in self.preview.widgets}
            eligible = sorted(pos for pos in added if pos[0] < self.client.sense_rows and pos in visible)
            if eligible:
                self.choose(eligible[0])
        self.preview.pressed_positions = pressed
        self.preview.update()
        if sample is None and position == self.position:
            self.sensor_summary.setText('Matrix %s,%s · Digital input; no capacitive signal measurement is available.' % position)
        if sample is not None:
            self.store_sample(position, sample)
            if position == self.position:
                threshold = self.client.thresholds.get(position, (None, None))[1]
                self.graph.feed(sample, threshold)
                if position in pressed:
                    self.last_held = sample
                else:
                    self.released.append(sample)
                noise = max(self.released)-min(self.released) if self.released else None
                self.sensor_summary.setText('Matrix %s,%s · Signal %s · Released %s · Held %s · Released noise %s DAC counts' %
                                            (*position, sample, self.released[-1] if self.released else '—', self.last_held if self.last_held is not None else '—', noise if noise is not None else '—'))
        for row in range(self.matrix.rowCount()):
            for col in range(self.matrix.columnCount()):
                item = self.matrix.item(row, col)
                pos = (row, col)
                item.setBackground(QColor('#45ae70' if pos in pressed else '#666b73' if pos in self.last_samples else '#343b43'))
                item.setForeground(QColor('#ffffff'))

    def store_sample(self, position, value):
        self.last_samples[position] = value
        self.sampled_at[position] = time.monotonic()
        self.matrix.item(*position).setText(str(value))
        if position in getattr(self, 'threshold_rows', {}):
            self.values.item(self.threshold_rows[position], 1).setText(str(value))
        for key in self.preview.widgets:
            if (key.desc.row, key.desc.col) == position:
                key.setText(str(value))
                key.tooltip = 'Matrix %s,%s · Signal %s DAC counts · Updated on this sampling pass.' % (*position, value)
        self.preview.update()
        self.summary.setText('%s / %s calibration positions sampled • Values refresh in rotation.' %
                             (sum(pos in self.last_samples for pos in self.client.thresholds), len(self.client.thresholds)))

    def show_thresholds(self):
        rows = self.threshold_positions = sorted(self.client.thresholds)
        self.threshold_rows = {position: index for index, position in enumerate(rows)}
        self.values.setRowCount(len(rows))
        for index, position in enumerate(rows):
            group, threshold = self.client.thresholds[position]
            for column, value in enumerate(('%s,%s' % position, self.last_samples.get(position, '—'), threshold, group+1)):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.values.setItem(index, column, item)
        self.table_source.setText('Thresholds read from keyboard; live signal values refresh in rotation.')

    def confirm_erase(self):
        answer = QMessageBox.question(self.window, 'Erase all EEPROM', 'Erase keymaps, macros and calibration settings on this keyboard? Reconnect afterward to initialize defaults.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.submit('erase')
