# SPDX-License-Identifier: GPL-3.0-or-later
"""EC42 controls for the selected Vial keyboard; ported from EC42 Utility.

Only this editor's worker uses the selected HID handle while a job runs. MainWindow
holds discovery and unrelated HID actions; shared EC pages remain navigable.
No second HID connection, firmware upload, auto-calibration or background saves.
"""
from collections import deque
import datetime
import json
import hashlib
from pathlib import Path
import time
import logging

from PyQt5.QtCore import Qt, QThread, QTimer, QStandardPaths, pyqtSignal, QSignalBlocker, QLockFile, QSize, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF, QPalette
from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                            QPushButton, QCheckBox, QSlider, QSpinBox, QGroupBox,
                            QTabWidget, QScrollArea, QTableWidget, QTableWidgetItem,
                            QHeaderView, QMessageBox, QFileDialog, QPlainTextEdit, QToolButton, QSizePolicy, QFrame, QGridLayout)
from editor.basic_editor import BasicEditor
from vial_device import VialKeyboard
from addon_runtime.widgets import AmkWidget
from keycodes.keycodes import Keycode
from vi_al_addons.ec_42.presentation import GRAY, RED, GREEN, BLUE, ABSENT, held, calibration_color, follow_pressed, actuation_references, LastPressPrediction, follow_updated
from vi_al_addons.ec_42.protocol import (Client, ECError, Op, profile_for_uid, u16, be16,
                         decode_record, load_backup, save_backup, affine)


class Job(QThread):
    """One bounded, serialized operation. Exceptions never retry mutations."""
    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.operation()
        except Exception as e:
            self.error = str(e)


class SensorGraph(QWidget):
    COLORS = {'raw': '#2ee7ff', 'minimum': '#c4d3ed', 'maximum': '#fff09a'}
    BASE_ACTUATION = '#ffbd33'
    BASE_RELEASE = '#c99aff'
    RT_RELEASE = '#ff63c5'
    RT_REACTIVATION = '#58f58b'
    KEY_ACTUATION = '#63ccff'

    def __init__(self):
        super().__init__()
        self.history = deque(maxlen=2000)
        self.lines = {'raw'}
        self.references = {}
        self.predictions = {}
        self.window_seconds = 4.0
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip('Periodic USB snapshots, not every matrix scan. Bright RT bars are estimates from the last observed completed press; they are not live firmware thresholds.')

    def clear(self):
        self.history.clear()
        self.references = {}
        self.predictions = {}
        self.update()

    def append(self, sample, references=None, predictions=None):
        if self.history and sample.get('seconds', 0) < self.history[-1].get('seconds', 0):
            self.clear()
        self.references = dict(references or {})
        self.predictions = dict(predictions or {})
        if self.history and sample.get('seconds', 0) == self.history[-1].get('seconds', 0):
            # Preview and final metadata can describe the same latch. Refresh
            # that point without falsely counting another delivered snapshot.
            self.history[-1] = dict(sample)
        else:
            self.history.append(dict(sample))
        # This is a live view, not a recording. Retain only the displayed window
        # (plus one edge point), with maxlen as an additional absolute bound.
        cutoff = sample.get('seconds', 0)-self.window_seconds
        while len(self.history) > 1 and self.history[1].get('seconds', 0) < cutoff:
            self.history.popleft()
        self.update()

    def cadence(self):
        if len(self.history) < 2:
            return 0., 0.
        end = self.history[-1]['seconds']
        times = [s['seconds'] for s in self.history if s['seconds'] >= end-2]
        gaps = [b-a for a,b in zip(times,times[1:]) if b>a]
        return ((len(times)-1)/(times[-1]-times[0]) if times[-1]>times[0] else 0., max(gaps,default=0.)*1000)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor('#15202d'))
        left, top = 44, 12
        width, height = max(1,self.width()-235), max(1,self.height()-43)
        def y(value):return top+height*(1-min(1023,max(0,value))/1023)
        for value in (0,256,512,768,1023):
            p.setPen(QColor('#b2c2d6'));p.drawText(2,int(y(value))+4,str(value))
            p.setPen(QColor('#35495f'));p.drawLine(left,int(y(value)),left+width,int(y(value)))
        if not self.history:
            p.setPen(QColor('#e1edff'));p.drawText(left+10,top+24,'Press a key to see its live signal.')
            return
        end = self.history[-1]['seconds'];start=end-self.window_seconds
        def x(seconds):return left+width*(seconds-start)/self.window_seconds
        refs = self.references
        if refs:
            p.fillRect(QRectF(left,y(refs['effective_actuation']),width,max(1,y(refs['effective_release'])-y(refs['effective_actuation']))),QColor('#285c83'))
            for name,color in (('base_actuation',self.BASE_ACTUATION),('base_release',self.BASE_RELEASE)):
                p.setPen(QPen(QColor(color),2,Qt.DashLine));p.drawLine(left,int(y(refs[name])),left+width,int(y(refs[name])))
            if refs['effective_actuation'] != refs['base_actuation']:
                p.setPen(QPen(QColor(self.KEY_ACTUATION),3))
                for name in ('effective_actuation','effective_release'):
                    p.drawLine(left,int(y(refs[name])),left+width,int(y(refs[name])))
            p.setPen(QColor('#e1edff'))
            p.drawText(left+8,top+17,'Selected initial actuation {} / release {}'.format(
                refs['effective_actuation'],refs['effective_release']))
        visible=[s for s in self.history if s['seconds']>=start]
        for name in self.lines:
            points=[QPointF(x(s['seconds']),y(s[name]))for s in visible if name in s]
            if len(points)>1:
                p.setPen(QPen(QColor(self.COLORS[name]),2.5 if name=='raw' else 2));p.drawPolyline(QPolygonF(points))
        previous=None
        for sample in visible:
            active=bool(sample.get('active'))
            if previous is not None and active!=previous:
                p.setPen(Qt.NoPen);p.setBrush(QColor(self.RT_REACTIVATION if active else self.RT_RELEASE))
                p.drawEllipse(QPointF(x(sample['seconds']),y(sample['raw'])),4,4)
            previous=active
        gutter=left+width+14
        prediction_labels=[]
        for name,color,label in (('release',self.RT_RELEASE,'RT release ≈'),('reactivation',self.RT_REACTIVATION,'RT press ≈')):
            if name not in self.predictions:continue
            value=self.predictions[name];level=y(value)
            p.setPen(QPen(QColor(color),6));p.drawLine(gutter,int(level),self.width()-12,int(level))
            prediction_labels.append((level,color,label+' '+str(value)))
        # Put one label above the upper bar and the other below the lower bar.
        # Keep the labels separated even at the ADC limits or overlapping bars.
        last_label_y=top-24
        for i,(level,color,label) in enumerate(sorted(prediction_labels)):
            label_y=level-25 if i==0 else level+5
            upper_limit=top+height-22-24*(len(prediction_labels)-i-1)
            label_y=max(top,last_label_y+24,min(upper_limit,label_y))
            last_label_y=label_y
            p.setPen(QColor(color))
            p.drawText(QRectF(gutter,label_y,175,22),Qt.AlignLeft|Qt.AlignVCenter,label)
        if not self.predictions:
            p.setPen(QColor('#d1def2'))
            p.drawText(QRectF(gutter,top+12,172,90),Qt.TextWordWrap,'RT prediction appears after an observed press and release while RT is enabled.')
        rate,gap=self.cadence()
        p.setPen(QColor('#deebff'))
        p.drawText(left,self.height()-7,'Last 4 s • {:.1f} snapshots/s • largest gap {:.0f} ms • USB snapshot rate'.format(rate,gap))


class SensorKeyboard(AmkWidget):
    """Use Vial's geometry/layout selection with EC-specific, per-key fills."""
    def __init__(self, layout_editor):
        super().__init__(layout_editor)
        self.setObjectName('ecSensorKeyboard')
        self.setAutoFillBackground(False)

    def minimumSizeHint(self):
        return QSize(280, 140)

    def content_offset(self):
        # Keep painting and pointer coordinates in the same centered space.
        if not self.widgets:
            return 0.
        left = min(key.polygon.boundingRect().left() for key in self.widgets)
        right = max(key.polygon.boundingRect().right() for key in self.widgets)
        return max(0., (self.size().width()-(left+right)*self.scale)/2)

    def hit_test(self, pos):
        return super().hit_test(QPointF(pos)-QPointF(self.content_offset(), 0))

    def update_select_keys(self):
        offset = QPointF(self.content_offset(), 0)
        rect = QRectF((QPointF(self.start_pos)-offset)/self.scale,
                      (QPointF(self.current_pos)-offset)/self.scale).normalized()
        self.active_keys = {(key.desc.row, key.desc.col): key for key in self.widgets
                            if rect.intersects(key.polygon.boundingRect())}
        return bool(self.active_keys)

    def sizeHint(self):
        return QSize(1100, 300)

    def resizeEvent(self, event):
        if self.widgets:
            width = max(w.polygon.boundingRect().right() for w in self.widgets)+self.padding
            height = max(w.polygon.boundingRect().bottom() for w in self.widgets)+self.padding
            self.scale = min(1.1, max(.2, event.size().width()/max(1, width)))
            wanted = int(height*self.scale)+2
            if self.minimumHeight() != wanted:
                self.setMinimumHeight(wanted)
                self.setMaximumHeight(wanted)
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.content_offset(), 0)
        for key in self.widgets:
            p.save()
            p.scale(self.scale, self.scale)
            p.translate(key.shift_x, key.shift_y)
            p.translate(key.rotation_x, key.rotation_y)
            p.rotate(key.rotation_angle)
            p.translate(-key.rotation_x, -key.rotation_y)
            state = getattr(key, 'ec_color', GRAY)
            neutral = state == GRAY
            # Use precisely the Keymap palette for unselected keys. Status and
            # selection colors remain EC-specific (including selected green).
            color = self.palette().color(QPalette.Button) if neutral else QColor(state)
            p.setPen(Qt.NoPen)
            p.setBrush(color if neutral else color.darker(120))
            p.drawPath(key.background_draw_path)
            p.setPen(QPen(self.palette().color(QPalette.HighlightedText), 2)
                     if getattr(key, 'ec_selected', False) else Qt.NoPen)
            p.setBrush(color.lighter(120) if neutral else color.lighter(130) if key.pressed else color)
            p.drawPath(key.foreground_draw_path)
            p.setPen(self.palette().color(QPalette.ButtonText))
            p.drawText(key.text_rect, Qt.AlignCenter, key.text)
            p.restore()


class ECPage(BasicEditor):
    """One top-level tab, sharing the EC editor's single transport/session."""
    def __init__(self, controller, section):
        super().__init__()
        self.ec_controller = controller
        self.section = section
        self.root = QWidget()
        self.body = QVBoxLayout(self.root)
        self.body.setSpacing(14)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.root)
        # QScrollArea normally fills the whole page with Window rather than the
        # tab pane's gray. Let the normal Keymap-style tab surface show through.
        self.root.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        self.addWidget(scroll)

    def valid(self):
        return self.ec_controller.valid()

    def activate(self):
        self.ec_controller.activate_section(self.section)

    def deactivate(self):
        self.ec_controller.deactivate()


class ECEditor(BasicEditor):
    busy_changed = pyqtSignal(bool)
    state_preview = pyqtSignal(object)

    def __init__(self, layout_editor):
        super().__init__()
        self.profile = self.client = self.keyboard = None
        self.worker = None
        self.running_operation = None
        self.finish_requested = False
        self.queued_action = None
        self.hid_lock = None
        self.online = False
        self.active = False
        self.loading = False
        self.state_preview.connect(self.preview_state)
        self.selected = 0
        self.key_selection = 0
        self.sensor_selection = 0
        self.ec_controller = self
        self.section = 'calibration'
        self.pressed_positions = set()
        self.selection_made = False
        self.selection_revision = 0
        self.selection_refresh_requested = False
        self.last_press_prediction = LastPressPrediction()
        self.sensor_activity_at = 0.
        self.settings_read_at = 0.
        self.samples = []
        self.calibration = None
        self.va = None
        self.review = None
        self.saved_record = None
        self.table_mode = 'stored'
        self.pending = {}
        self.last_error = None
        self.last_poll = 0
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)
        self.apply_timer = QTimer(self)
        self.apply_timer.setSingleShot(True)
        self.apply_timer.setInterval(250)
        self.apply_timer.timeout.connect(self.apply_pending)

        self.identity_labels = []
        self.status_labels = []
        self.actuation_page = ECPage(self, 'actuation')
        self.sensors_page = ECPage(self, 'sensors')
        self.root = QWidget()
        self.body = QVBoxLayout(self.root)
        self.body.setSpacing(14)
        self.identity, self.status_label = self.add_header(self.body)
        self.build_calibration(layout_editor)
        self.build_actuation(layout_editor)
        self.build_sensors()
        self.build_advanced()
        layout_editor.changed.connect(self.on_layout_changed)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.root)
        # QScrollArea normally fills the whole page with Window rather than the
        # tab pane's gray. Let the normal Keymap-style tab surface show through.
        self.root.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        self.addWidget(scroll)
        self.actions_enabled(False)

    def add_header(self, body):
        identity = QLabel('EC42 v2.9 • read-only connection until you change a setting')
        identity.setWordWrap(True)
        status = QLabel()
        status.setWordWrap(True)
        self.identity_labels.append(identity)
        self.status_labels.append(status)
        body.addWidget(identity)
        body.addWidget(status)
        return identity, status

    def set_status(self, text):
        for label in self.status_labels:
            label.setText(text)

    def set_identity(self, text):
        for label in self.identity_labels:
            label.setText(text)

    def button(self, layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def build_calibration(self, layout_editor):
        hint = QLabel('Gray: not captured this session • green: held • blue: captured • red: failed/retry. '
                      'Release every key before Start, then fully press and release the keys you want to calibrate. '
                      'Stored settings are preserved until Save and apply.')
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        columns = QHBoxLayout()
        left = QVBoxLayout()
        self.keyboard_preview = SensorKeyboard(layout_editor)
        self.keyboard_preview.set_scale(1.0)
        self.keyboard_preview.clicked.connect(lambda: self.select_physical(self.keyboard_preview))
        left.addWidget(self.keyboard_preview)
        self.summary = QLabel('Reading stored calibration…')
        self.summary.setWordWrap(True)
        left.addWidget(self.summary)
        self.selection_label = QLabel('Click a key to select it for Retry.')
        self.selection_label.setWordWrap(True)
        left.addWidget(self.selection_label)
        self.row, self.col = QSpinBox(), QSpinBox()
        self.row.valueChanged.connect(self.select_coordinate)
        self.col.valueChanged.connect(self.select_coordinate)
        self.capture_panel = QGroupBox('Manual calibration')
        self.capture_panel.setObjectName('ecCalibrationActions')
        self.capture_panel.setStyleSheet('QGroupBox#ecCalibrationActions { border: 2px solid #000000; border-radius: 5px; margin-top: 10px; padding: 12px; } QGroupBox#ecCalibrationActions::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }')
        buttons = QGridLayout(self.capture_panel)
        def action(text, callback, row, col):
            button = QPushButton(text)
            button.setMinimumHeight(32)
            button.clicked.connect(callback)
            buttons.addWidget(button, row, col)
            return button
        self.start_button = action('Start manual calibration', self.start_capture, 0, 0)
        self.finish_button = action('Finish / review', self.finish_capture, 0, 1)
        self.resume_button = action('Resume capture', lambda: self.launch('resume', lambda: self.client.control(6)), 0, 2)
        self.retry_button = action('Retry selected key', self.retry_capture, 1, 0)
        self.cancel_button = action('Cancel calibration', self.cancel_capture, 1, 1)
        self.save_button = action('Save and apply', self.save_capture, 1, 2)
        left.addWidget(self.capture_panel)
        left.addStretch(1)
        columns.addLayout(left, 13)
        self.position_panel = QWidget(self.root)
        self.position_panel.setMinimumWidth(290)
        position = QVBoxLayout(self.position_panel)
        position.setContentsMargins(0, 0, 0, 0)
        position.addWidget(QLabel('Position / calibration values'))
        self.table_source = QLabel('Reading stored EC values…')
        self.table_source.setWordWrap(True)
        position.addWidget(self.table_source)
        self.review_table = QTableWidget(0, 3)
        self.review_table.setHorizontalHeaderLabels(('Position', 'Result', 'Stored bottom'))
        self.review_table.verticalHeader().setVisible(False)
        self.review_table.horizontalHeader().setStretchLastSection(False)
        self.review_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.review_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.review_table.setMinimumHeight(390)
        position.addWidget(self.review_table, 1)
        columns.addWidget(self.position_panel, 4)
        self.body.addLayout(columns, 1)

    def build_actuation(self, layout_editor):
        body = self.actuation_page.body
        self.add_header(body)
        self.actuation_keyboard = SensorKeyboard(layout_editor)
        self.actuation_keyboard.set_scale(1.0)
        self.actuation_keyboard.clicked.connect(lambda: self.select_physical(self.actuation_keyboard))
        body.addWidget(self.actuation_keyboard)
        self.actuation_group = QGroupBox('Actuation')
        self.actuation_group.setObjectName('ecActuationSettings')
        self.actuation_group.setStyleSheet('QGroupBox#ecActuationSettings { border: 2px solid #000000; border-radius: 6px; margin-top: 12px; padding: 14px; } QGroupBox#ecActuationSettings::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; font-weight: bold; }')
        form = QGridLayout(self.actuation_group)
        form.setHorizontalSpacing(22)
        form.setVerticalSpacing(12)
        form.setColumnStretch(0, 1)
        slider_style = 'QSlider::groove:horizontal { height: 16px; background: #20242b; border-radius: 8px; } QSlider::sub-page:horizontal { background: #4b95db; border-radius: 8px; } QSlider::handle:horizontal { width: 30px; margin: -9px 0; border-radius: 15px; background: #c8d6e8; }'
        self.global_actuation = QSlider(Qt.Horizontal)
        self.key_actuation = QSlider(Qt.Horizontal)
        for slider in (self.global_actuation, self.key_actuation):
            slider.setRange(1, 99)
            slider.setMinimumHeight(56)
            slider.setStyleSheet(slider_style)
            slider.setToolTip('Percentage of calibrated travel. 99 = Deepest (bottom minus one ADC count), not millimeters.')
        self.global_value, self.key_value = QLabel(), QLabel()
        for label in (self.global_value, self.key_value):
            font = label.font()
            font.setPointSize(max(14, font.pointSize()))
            font.setBold(True)
            label.setFont(font)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setMinimumWidth(label.fontMetrics().horizontalAdvance('Override — Deepest')+16)
        self.global_header = QLabel('Global Default Actuation')
        self.per_key_title = QLabel('Per-key Actuation')
        for label in (self.global_header, self.per_key_title):
            font = label.font()
            font.setPointSize(max(12, font.pointSize()))
            font.setBold(True)
            label.setFont(font)
        form.addWidget(self.global_header, 0, 0, 1, 2)
        form.addWidget(self.global_actuation, 1, 0)
        form.addWidget(self.global_value, 1, 1)
        form.addWidget(self.per_key_title, 2, 0, 1, 2)
        self.global_policy = QLabel('Moving Global resets all per-key overrides. Moving Per-key changes only the selected key.')
        self.global_policy.setWordWrap(True)
        form.addWidget(self.global_policy, 3, 0, 1, 2)
        self.per_key_header = QLabel('Click a key above to select its actuation setting.')
        font = self.per_key_header.font()
        font.setPointSize(max(10, font.pointSize()))
        self.per_key_header.setFont(font)
        self.per_key_header.setWordWrap(True)
        form.addWidget(self.per_key_header, 4, 0, 1, 2)
        form.addWidget(self.key_actuation, 5, 0)
        form.addWidget(self.key_value, 5, 1)
        body.addWidget(self.actuation_group)
        self.rt_group = QGroupBox('Dynamic Rapid Trigger')
        self.rt_group.setObjectName('ecRapidTrigger')
        self.rt_group.setStyleSheet('QGroupBox#ecRapidTrigger { border: 2px solid #000000; border-radius: 6px; margin-top: 12px; padding: 14px; } QGroupBox#ecRapidTrigger::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; font-weight: bold; }')
        form = QFormLayout(self.rt_group)
        explanation = QLabel('After a key activates, lift slightly to release it, then press down slightly to activate it again.\n\n'
                             'Higher sensitivity needs less movement. The first press still uses your actuation setting.')
        explanation.setWordWrap(True)
        form.addRow(explanation)
        self.rt_enabled = QCheckBox('Enable Dynamic Rapid Trigger')
        form.addRow(self.rt_enabled)
        self.sensitivity = QSlider(Qt.Horizontal)
        self.sensitivity.setRange(0, 251)
        self.sensitivity.setMinimumHeight(56)
        self.sensitivity.setStyleSheet(slider_style)
        self.sensitivity_value = QLabel()
        font = self.sensitivity_value.font()
        font.setPointSize(max(12, font.pointSize()))
        font.setBold(True)
        self.sensitivity_value.setFont(font)
        row = QHBoxLayout()
        row.addWidget(self.sensitivity, 1)
        row.addWidget(self.sensitivity_value)
        form.addRow('Sensitivity', row)
        self.rt_press, self.rt_release = QSpinBox(), QSpinBox()
        for label, spin in (('Reactivation movement (ADC)', self.rt_press), ('Release movement (ADC)', self.rt_release)):
            spin.setRange(1, 255)
            form.addRow(label, spin)
            spin.valueChanged.connect(self.stage_rt)
        self.rt_range = QLabel()
        self.rt_range.setWordWrap(True)
        form.addRow(self.rt_range)
        body.addWidget(self.rt_group)
        self.global_actuation.valueChanged.connect(lambda v: self.stage('global', v))
        self.key_actuation.valueChanged.connect(lambda v: self.stage('key', (self.key_selection, v)))
        self.rt_enabled.toggled.connect(self.stage_rt)
        self.sensitivity.valueChanged.connect(self.stage_sensitivity)
        body.addStretch()

    def build_sensors(self):
        body = self.sensors_page.body
        body.setSpacing(8)
        self.add_header(body)
        intro = QLabel('Press a key to inspect it. The graph automatically follows the newest detected key activity. '
                       'Green matrix cells show keys that are active or have clear measured movement. '
                       'The graph keeps showing the last key after you release it.')
        intro.setWordWrap(True)
        body.addWidget(intro)
        self.graph = SensorGraph()
        self.details = QLabel('Press a key to begin.')
        self.details.setWordWrap(True)
        body.addWidget(self.details)
        body.addWidget(self.graph, 1)
        legend = QLabel('Live signal: cyan • Global defaults: dashed amber/purple • Selected-key override: bright blue lines and band. '
                        'Bright pink/green bars: RT estimates based on the last observed completed press, held fixed during the next press. '
                        'Dots show sampled firmware press/release transitions; USB snapshots can miss events. A full release resets the next press to the base threshold.')
        legend.setWordWrap(True)
        body.addWidget(legend)
        overlays = QHBoxLayout()
        for key in ('raw', 'minimum', 'maximum'):
            check = QCheckBox(key.capitalize())
            check.setChecked(key in self.graph.lines)
            check.toggled.connect(lambda on, key=key: self.overlay(key, on))
            overlays.addWidget(check)
        overlays.addStretch()
        body.addLayout(overlays)
        self.matrix = QTableWidget()
        self.matrix.setEditTriggers(QTableWidget.NoEditTriggers)
        self.matrix.setSelectionMode(QTableWidget.SingleSelection)
        self.matrix.cellClicked.connect(lambda r, c: self.choose(r*self.profile.cols+c))
        self.matrix.setMinimumHeight(220)
        self.matrix.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.matrix.verticalHeader().setMinimumSectionSize(18)
        body.addWidget(self.matrix, 1)
        note = QLabel('Rows and columns are electrical matrix positions. Gray = released; green = activity; dark = not sampled. '
                      'USB snapshots can miss very short taps and are not a measurement of matrix scan frequency.')
        note.setWordWrap(True)
        body.addWidget(note)

    def build_advanced(self):
        self.tools_toggle = QToolButton()
        self.tools_toggle.setText('Backup and device tools')
        self.tools_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.tools_toggle.setArrowType(Qt.RightArrow)
        self.tools_toggle.setCheckable(True)
        self.body.addWidget(self.tools_toggle)
        self.tools_panel = QWidget(self.root)
        body = QVBoxLayout(self.tools_panel)
        row = QHBoxLayout()
        self.reconnect_button = self.button(row, 'Reconnect / read status', self.connect_client)
        self.export_button = self.button(row, 'Export exact EC backup…', self.export_backup)
        self.restore_button = self.button(row, 'Restore EC backup…', self.restore_backup)
        self.boot_button = self.button(row, 'Enter bootloader…', self.enter_bootloader)
        body.addLayout(row)
        hint = QLabel('Backups contain only the EC record, not Vial keymaps/macros. Restore accepts verified matching EC42 v2.9 packed records. The board UID is not an individual serial number.')
        hint.setWordWrap(True)
        body.addWidget(hint)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        self.log.setMaximumHeight(160)
        body.addWidget(self.log)
        self.tools_panel.hide()
        self.body.addWidget(self.tools_panel)
        self.tools_toggle.toggled.connect(self.tools_panel.setVisible)
        self.tools_toggle.toggled.connect(lambda on: self.tools_toggle.setArrowType(Qt.DownArrow if on else Qt.RightArrow))

    def valid(self):
        if not isinstance(self.device, VialKeyboard):
            return False
        profile = profile_for_uid(self.device.keyboard.keyboard_id)
        return bool(profile and (self.device.keyboard.rows, self.device.keyboard.cols) == (profile.rows, profile.cols))

    def rebuild(self, device):
        self.deactivate()
        super().rebuild(device)
        self.online = False
        self.client = None
        self.profile = profile_for_uid(device.keyboard.keyboard_id) if isinstance(device, VialKeyboard) else None
        self.keyboard = device.keyboard if self.profile else None
        self.samples, self.calibration, self.va, self.review = [], None, None, None
        self.saved_record = None
        self.table_mode = 'stored'
        self.selected = 0
        self.key_selection = 0
        self.sensor_selection = 0
        self.pending = {}
        self.selection_made = False
        self.selection_revision += 1
        self.selection_refresh_requested = False
        self.pressed_positions = set()
        self.last_press_prediction.clear()
        self.sensor_activity_at = 0.
        self.settings_read_at = 0.
        self.graph.clear()
        self.review_table.setRowCount(0)
        if self.profile:
            self.keyboard_preview.set_keys(self.keyboard.keys, self.keyboard.encoders)
            self.actuation_keyboard.set_keys(self.keyboard.keys, self.keyboard.encoders)
            self.refresh_keyboards()
            self.row.setRange(0, self.profile.rows-1)
            self.col.setRange(0, self.profile.cols-1)
            self.matrix.setRowCount(self.profile.rows)
            self.matrix.setColumnCount(self.profile.cols)
            self.matrix.setHorizontalHeaderLabels([str(i) for i in range(self.profile.cols)])
            self.matrix.setVerticalHeaderLabels([str(i) for i in range(self.profile.rows)])
            self.matrix.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.matrix.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.show_stored_rows()
        self.selection_made = False
        self.actions_enabled(False)

    def on_layout_changed(self):
        """Follow Layout's current physical options without any device writes."""
        if not self.profile:
            return
        for preview in (self.keyboard_preview, self.actuation_keyboard):
            preview.clear_active_keys()
            preview.update_layout()
        # Newly visible alternatives need their existing matrix sample/color,
        # not an empty key or a reset of the calibration capture.
        self.refresh_keyboards()

    def activate(self):
        self.activate_section('calibration')

    def activate_section(self, section):
        if section != self.section:
            self.selection_revision += 1
            self.selection_refresh_requested = True
        self.section = section
        self.selected = self.sensor_selection if section == 'sensors' else self.key_selection
        self.key_actuation.setEnabled(False)
        self.on_layout_changed()
        self.timer.setInterval(5 if section == 'sensors' else 150 if section == 'calibration' else 300)
        if not self.valid():
            return
        self.active = True
        if not self.online or not self.hid_lock:
            self.connect_client()
        self.timer.start()

    def deactivate(self):
        self.active = False
        self.finish_requested = False
        self.queued_action = None
        self.timer.stop()
        self.apply_timer.stop()
        # Editing controls never queues a delayed write after leaving the page.
        self.pending = {}
        if self.hid_lock and not self.worker:
            self.hid_lock.unlock()
            self.hid_lock = None

    def exchange(self, packet):
        if self.keyboard.dev.write(b'\0'+packet) != 33:
            raise ECError('HID write failed; no retry')
        response = bytes(self.keyboard.dev.read(32, timeout_ms=500))
        if len(response) != 32:
            raise ECError('HID timeout/disconnect; no retry')
        return response

    def connect_client(self):
        if not self.valid() or self.worker:
            return
        self.online = False
        self.timer.stop()
        self.actions_enabled(False)
        if not self.hid_lock:
            path = self.device.desc['path']
            if isinstance(path, str):
                path = path.encode()
            lock_path = str(Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation)) /
                            ('qmk-ec-util-'+hashlib.sha256(path).hexdigest()+'.lock'))
            lock = QLockFile(lock_path)
            if not lock.tryLock(0):
                self.set_status('EC interface is in use by EC42 Utility. Close it, then reconnect.')
                return
            self.hid_lock = lock
        self.client = Client(self.exchange, self.profile)
        self.set_status('Connecting — reading current EC settings…')
        self.launch('connect', lambda: self.read_state(preview=self.state_preview.emit))

    def read_state(self, preview=None):
        info = self.client.identify()
        status = self.client.status()
        if preview is not None:
            # Publish useful values before the 96 CELL reads and saved records.
            # Detached dictionaries prevent background hydration changing the
            # samples currently being rendered by the GUI thread.
            selected = self.selected
            samples = self.client.poll(selected, full=True, metadata='selected')
            index = selected if samples[selected]['sampled'] else 0xffff
            preview(dict(info=info, status=status, va=self.client.actuation(index),
                         samples=[dict(sample) for sample in samples], full_matrix=False))
        active = None
        record_error = ''
        try:
            active = self.client.active_record()
        except ECError as e:
            if not self.client.healthy:
                raise
            record_error = str(e)
        stored = None
        stored_error = ''
        try:
            stored = decode_record(self.client.read_record(), self.profile)
        except ECError as e:
            if not self.client.healthy:
                raise
            stored_error = str(e)
        samples = (self.client.finish_snapshot_metadata() if preview is not None
                   else self.client.poll(self.selected, full=True))
        index = self.selected if samples[self.selected]['sampled'] else 0xffff
        return dict(info=info, status=status, record=active, record_error=record_error, stored=stored, stored_error=stored_error,
                    va=self.client.actuation(index), samples=samples)

    def preview_state(self, result):
        """Show first readings while retaining the loader's transport/write guard."""
        if not self.active or self.running_operation != 'connect' or not self.worker:
            return
        try:
            self.show_identity(result['info'])
            self.receive(result)
            self.refresh_keyboards()
            self.set_status('Current readings loaded — validating saved calibration and key ranges…')
            self.table_source.setText('Reading stored EC record; controls unlock after validation.')
        except Exception:
            # A preview is optional. Preserve the worker/guard and let final
            # completion perform the normal validation and error cleanup.
            logging.exception('EC initial preview failed')

    def show_identity(self, info):
        self.set_identity('{} • {} • EC42 v2.9 • {}×{} • storage {}'.format(
            info['name'], info['firmware'], self.profile.rows, self.profile.cols,
            'ready' if info['storage'] else 'unavailable (writes disabled)'))

    def launch(self, name, operation):
        if self.worker and self.running_operation == 'poll' and name != 'poll':
            # A user click must not disappear merely because a sensor GET is
            # in flight. One bounded slot; later intent replaces earlier intent.
            self.queued_action = (name, operation)
            return True
        if self.worker or (name != 'connect' and not self.online):
            return False
        self.apply_timer.stop()
        self.running_operation = name
        self.busy_changed.emit(True)
        if name in ('actuation', 'rapid-trigger'):
            # Keep live sliders interactive and coalesce newer intent while this
            # write completes. Disabling their parent on every update caused
            # flicker, broken drags and misleading readback jumps.
            for control in (self.start_button, self.finish_button, self.resume_button,
                            self.retry_button, self.cancel_button, self.save_button,
                            self.export_button, self.restore_button, self.boot_button,
                            self.reconnect_button):
                control.setEnabled(False)
        elif name != 'poll':
            self.actions_enabled(False)
        job = Job(operation, self.parentWidget())
        self.worker = job
        job.finished.connect(lambda: self.completed(name, job))
        job.start()
        return True

    def completed(self, name, job):
        self.worker = None
        try:
            self.consume_result(name, job)
        except Exception as error:
            job.error = 'GUI update failed: '+str(error)
            self.last_error = job.error
            self.online = False
            self.timer.stop()
            self.pending = {}
            self.set_status(job.error+' — reconnect to continue.')
            self.log.appendPlainText(job.error)
            logging.exception('EC GUI completion failed')
        finally:
            self.finish_job(name, job)

    def consume_result(self, name, job):
        if job.error:
            self.last_error = job.error
            self.log.appendPlainText(name+': '+job.error)
            self.set_status('Error: '+job.error)
            self.pending = {}
            self.online = bool(self.client and self.client.healthy and self.client.ready and name != 'connect')
            if not self.online:
                self.timer.stop()
        else:
            if name != 'poll':
                self.last_error = None
            result = job.result
            if name == 'connect':
                self.online = True
                info = result['info']
                self.show_identity(info)
                self.log.appendPlainText('Read-only handshake: '+json.dumps(info))
                if result['record_error']:
                    self.log.appendPlainText('Active record unavailable: '+result['record_error'])
                self.saved_record = result.get('stored')
                self.table_mode = 'stored'
                if result.get('stored_error'):
                    self.log.appendPlainText('Stored record unavailable: '+result['stored_error'])
                self.receive(result)
                self.show_stored_rows()
                if self.active:
                    self.timer.start()
            elif name == 'poll':
                self.receive(result)
            elif name == 'review':
                self.review = result
                self.table_mode = 'proposal'
                self.show_review_rows(result['rows'])
                self.log.appendPlainText('Review ready. '+result['error'])
                self.calibration = self.client.cal_status
            elif name == 'export':
                self.log.appendPlainText('Exact raw EC backup exported: '+str(result))
            elif name == 'bootloader':
                self.online = False
                self.timer.stop()
                self.log.appendPlainText('Bootloader entry acknowledged; no firmware flashed.')
            else:
                self.log.appendPlainText(name+': acknowledged and verified' if name in ('actuation', 'rapid-trigger', 'save', 'restore') else name+': acknowledged')
                if name in ('actuation', 'rapid-trigger'):
                    self.va = result
                    self.update_actuation()
                if name in ('save', 'restore'):
                    self.saved_record = decode_record(result, self.profile)
                    self.client.record = self.saved_record
                if name in ('start', 'resume', 'retry', 'cancel', 'save', 'restore'):
                    self.table_mode = 'capturing' if name in ('start', 'resume', 'retry') else 'stored'
                    self.show_stored_rows()
                    self.review = None
                    self.calibration = None
                    if name in ('save', 'restore', 'cancel'):
                        self.client.samples = []
                self.last_poll = 0
            self.update_status()
        self.actions_enabled(self.online)
    def finish_job(self, name, job):
        self.busy_changed.emit(False)
        if not self.active and self.hid_lock:
            self.hid_lock.unlock()
            self.hid_lock = None
        job.deleteLater()
        self.running_operation = None
        action, self.queued_action = self.queued_action, None
        if action and not job.error and self.active:
            self.finish_requested = False
            QTimer.singleShot(0, lambda: self.active and self.launch(*action))
        if self.finish_requested:
            self.finish_requested = False
            if not job.error and self.active:
                QTimer.singleShot(0, self.finish_capture)
        if self.pending and not job.error:
            self.apply_timer.start()
        if name != 'poll':self.settings_read_at = 0.
        if self.active and self.online:
            if self.selection_refresh_requested:
                QTimer.singleShot(0, self.poll)
            else:
                self.timer.start()

    def poll(self):
        if not self.active or not self.online or self.worker:
            return
        if self.pending:
            self.apply_pending()
            return
        selected = self.selected
        selection_revision = self.selection_revision
        self.selection_refresh_requested = False
        section = self.section
        sensor = self.section == 'sensors'
        now = time.monotonic()
        focused = now-self.sensor_activity_at < 1.
        refresh_settings = not self.va or now-self.settings_read_at >= .25
        previous = set(self.pressed_positions)
        cached_va, cached_cal = self.va, self.calibration
        def read():
            # Interleave a small part of matrix discovery with the followed key;
            # a monolithic 21-report matrix read would stall the trace ~83 ms.
            samples = self.client.poll(selected,selected_only=sensor,metadata=False,
                                       background_pages=(2 if focused else 4) if sensor else 0)
            updated=set(self.client.updated_indices)
            following,down=follow_updated(samples,previous,selected,updated) if sensor else (selected,previous)
            if samples[following]['sampled']:self.client.selected_details(following)
            index = following if samples[following]['sampled'] else 0xffff
            need_settings = refresh_settings or cached_va is None or cached_cal is None or u16(cached_va,18)!=index
            return dict(status=self.client.status() if need_settings else cached_cal,
                        va=self.client.actuation(index) if need_settings else cached_va,
                        samples=samples,following=following,pressed=down,updated=updated,
                        section=section, selection_revision=selection_revision,
                        full_matrix=len(updated)==self.profile.cells,settings_refreshed=need_settings)
        self.last_poll = now
        self.launch('poll', read)

    def receive(self, result):
        self.calibration, self.va = result['status'], result['va']
        if (result.get('section', self.section) != self.section or
                result.get('selection_revision', self.selection_revision) != self.selection_revision):
            # Navigation between shared EC pages can occur during a read. Keep
            # valid cached data, but never apply the old page's following/graph
            # intent to the newly selected page. Its next poll starts on finish.
            if result.get('samples'):
                self.samples = result['samples']
            self.update_status()
            return
        if 'following' in result and self.section == 'sensors':
            if self.selected != result['following']:
                self.graph.clear()
                self.selected = result['following']
            self.sensor_selection = self.selected
            self.pressed_positions = result['pressed']
        if result.get('samples'):
            self.samples = result['samples']
            if result.get('settings_refreshed',True):self.settings_read_at=time.monotonic()
            if held(self.samples[self.selected]):self.sensor_activity_at=time.monotonic()
            self.update_sensors(full=result.get('full_matrix',True),updated=result.get('updated'))
        self.update_actuation()
        self.update_status()

    def update_status(self):
        if not self.va or not self.calibration:
            return
        states = ('Saved', 'Applied in RAM; pending save', 'Saving', 'Save error', 'Calibration required')
        state = states[self.va[4]]
        if self.va[4] == 0 and u16(self.va) != u16(self.va, 2):
            state = 'Unverified revision mismatch'
        self.set_status(('Error: '+self.last_error+' • ' if self.last_error else '') + '{} • revision {} / saved {} • Calibration {}'.format(
            state, u16(self.va), u16(self.va, 2),
            {0:'idle',1:'capturing',3:'review',4:'validated / ready',5:'activated / unsaved'}.get(self.calibration[0], '?')))

    def actions_enabled(self, enabled):
        ready = enabled and bool(self.client and self.client.storage)
        state = self.calibration[0] if self.calibration else None
        idle = ready and state == 0
        for control in (self.actuation_group, self.rt_group):
            control.setEnabled(idle and bool(self.va and self.va[5] and self.va[4] != 3))
        global_supported = bool(self.client and self.client.capabilities & 0x0080)
        self.global_actuation.setEnabled(global_supported)
        self.global_policy.setText('Moving Global resets all per-key overrides. Moving Per-key changes only the selected key.' if global_supported else
                                   'Updating Global requires EC firmware with atomic global-reset support. Per-key controls remain available.')
        sampled = bool(self.samples and self.samples[self.selected]['sampled'])
        calibrated = sampled and self.selection_made and self.samples[self.selected]['enabled'] and bool(self.va and u16(self.va, 18) == self.selected)
        self.key_actuation.setEnabled(idle and calibrated)
        self.start_button.setEnabled(idle and bool(self.va and self.va[4] in (0, 4)))
        self.finish_button.setEnabled(ready and state == 1)
        self.resume_button.setEnabled(ready and state in (3, 4))
        self.retry_button.setEnabled(ready and state == 1 and sampled)
        self.cancel_button.setEnabled(ready and state in (1, 3, 4, 5))
        self.save_button.setEnabled(ready and state in (3, 4) and bool(self.review and self.review['can_apply']))
        self.export_button.setEnabled(enabled)
        self.restore_button.setEnabled(idle)
        self.boot_button.setEnabled(ready)
        self.reconnect_button.setEnabled(not bool(self.worker))

    def choose(self, index):
        if not self.profile or not 0 <= index < self.profile.cells:
            return
        self.selected = index
        self.selection_revision += 1
        self.selection_refresh_requested = True
        if self.section == 'sensors':
            self.sensor_selection = index
        else:
            self.key_selection = index
            self.selection_made = True
        with QSignalBlocker(self.row), QSignalBlocker(self.col):
            self.row.setValue(index//self.profile.cols)
            self.col.setValue(index%self.profile.cols)
        self.graph.clear()
        # Selecting another key must not discard edits to the preceding key.
        # Pending per-key changes are independently keyed by matrix position.
        self.update_sensors()
        # Override status belongs to the previous selection until next readback.
        self.key_actuation.setEnabled(False)
        self.key_value.setText('Reading key…')
        self.last_poll = 0
        if self.active and self.online and not self.worker:
            self.timer.stop()
            QTimer.singleShot(0, self.poll)

    def select_coordinate(self):
        if self.profile:
            self.choose(self.row.value()*self.profile.cols+self.col.value())

    def select_physical(self, preview=None):
        preview = preview or self.keyboard_preview
        if preview.active_keys and self.profile:
            row, col = next(iter(preview.active_keys))
            self.choose(row*self.profile.cols+col)

    def overlay(self, key, on):
        (self.graph.lines.add if on else self.graph.lines.discard)(key)
        self.graph.update()

    def key_label(self, row, col):
        code = getattr(self.keyboard, 'layout', {}).get((0, row, col))
        if code:
            try:
                label = Keycode.label(code).replace('\n', ' ')
                return {'Print Screen':'PrtSc', 'Scroll Lock':'ScrLk', 'Page Up':'PgUp', 'Page Down':'PgDn'}.get(label, label)
            except (KeyError, AttributeError, TypeError):
                pass
        return '{}/{}'.format(row, col)

    def refresh_keyboards(self):
        if not self.profile:
            return
        for preview, actuation in ((self.keyboard_preview, False), (self.actuation_keyboard, True)):
            for key in preview.widgets:
                i = key.desc.row*self.profile.cols+key.desc.col
                sample = self.samples[i] if 0 <= i < len(self.samples) else dict(sampled=True)
                selected = self.selection_made and i == self.key_selection
                key.ec_color = (GREEN if selected else GRAY) if actuation else calibration_color(sample, capturing=bool(self.calibration and self.calibration[0] == 1))
                key.ec_selected = selected
                key.setPressed(False)
                key.setText(self.key_label(key.desc.row, key.desc.col) if actuation else
                            str(sample['raw']) if sample.get('sampled') and 'raw' in sample else '—')
            preview.update()
        if self.selection_made:
            self.per_key_header.setText('Selected key: {} (row {}, column {})'.format(
                self.key_label(self.key_selection//self.profile.cols, self.key_selection%self.profile.cols),
                self.key_selection//self.profile.cols, self.key_selection%self.profile.cols))
        else:
            self.per_key_header.setText('Click a key above to select its actuation setting.')

    def update_sensors(self, full=True, updated=None):
        if not self.samples or not self.profile:
            return
        counts = dict(saved=0, new=0, retry=0, inactive=0, absent=0)
        self.matrix.setUpdatesEnabled(False)
        try:
            for i, sample in enumerate(self.samples):
                if not full and i not in (updated if updated is not None else {self.selected}):continue
                bucket = ('absent' if not sample['sampled'] else 'new' if sample['capture'] == 1 else
                          'retry' if sample['capture'] in (2, 3) else 'saved' if sample['enabled'] else 'inactive')
                counts[bucket] += 1
                item = self.matrix.item(i//self.profile.cols, i%self.profile.cols)
                if item is None:
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignCenter)
                    self.matrix.setItem(i//self.profile.cols, i%self.profile.cols, item)
                item.setText(str(sample['raw']) if sample['sampled'] else '—')
                item.setBackground(QColor(ABSENT if not sample['sampled'] else GREEN if held(sample) else GRAY))
                item.setForeground(QColor('#ffffff'))
                item.setToolTip('Row {} column {} • {}'.format(i//self.profile.cols, i%self.profile.cols, self.capture_text(sample)))
        finally:
            self.matrix.setUpdatesEnabled(True)
        if full:self.refresh_keyboards()
        if full and self.table_mode in ('stored', 'capturing'):
            self.show_stored_rows()
        sample = self.samples[self.selected]
        self.selection_label.setText(self.capture_text(sample))
        if full:self.summary.setText('{saved} saved/enabled • {new} captured this session • {retry} retry • {inactive} inactive • {absent} nonexistent'.format(**counts))
        if sample['sampled']:
            refs = actuation_references(sample, self.va) if self.va and u16(self.va, 18) == self.selected else {}
            text = 'Following row {}, column {} • Raw ADC {}'.format(
                self.selected//self.profile.cols, self.selected%self.profile.cols, sample['raw'])
            if refs:
                text += ' • Base actuation {} / release {} • Selected-key range {}–{}'.format(
                    refs['base_actuation'], refs['base_release'], refs['effective_release'], refs['effective_actuation'])
            else:
                text += ' • No calibrated actuation range available'
            self.details.setText(text)
            if self.section == 'sensors':
                prediction=self.last_press_prediction.observe(self.selected,sample,refs,self.va)
                self.graph.append(sample,refs,prediction)
        else:
            self.details.setText('Firmware does not sample this electrical position.')

    @staticmethod
    def capture_text(s):
        if not s['sampled']:
            return 'Firmware nonexistent'
        if s['capture'] == 1:
            return 'NEW qualified capture — unsaved'
        if s['capture'] in (2, 3):
            return 'Needs retry — disabled after Save'
        if s['enabled']:
            return 'Saved calibration enabled; retained if untouched'
        return 'Uncalibrated or disabled'

    def update_actuation(self):
        if not self.va:
            return
        p = self.va
        if u16(p, 18) not in (0xffff, self.selected):
            return
        self.loading = True
        try:
            self.global_actuation.setValue(self.pending.get('global', round(u16(p, 6)*100/1023)))
            override = self.displayed_override()
            if override is not None:
                self.key_actuation.setValue(override or self.global_actuation.value())
            rt = self.pending.get('rt', p[10:13])
            self.rt_enabled.setChecked(bool(rt[0]))
            self.rt_press.setValue(rt[1])
            self.rt_release.setValue(rt[2])
            lo, hi = self.rt_limits(p)
            self.sensitivity.setValue(255-max(rt[1], rt[2]))
            self.sensitivity.setEnabled(hi >= lo)
            self.rt_range.setText('Available movement: {}–{} ADC. Settings adjust if needed to fit the key travel.'.format(lo, hi) if hi >= lo else 'Recalibrate the keyboard before enabling Rapid Trigger.')
            self.update_values()
        finally:
            self.loading = False

    def minimum_actuation(self, p, selected=None):
        gap = u16(p, 6)-u16(p, 8)
        minimum = 1
        while minimum < 99 and (minimum*1023+50)//100 <= gap:
            minimum += 1
        for i, s in enumerate(self.samples):
            if selected is not None and selected != i:
                continue
            if not s.get('sampled') or not s.get('enabled') or 'baseline' not in s:
                continue
            span = s['bottom']-s['baseline']
            candidate = minimum
            while candidate < 99:
                q = (candidate*1023+50)//100
                if (q-gap)*span//1023 > 0 and q*span//1023 > (q-gap)*span//1023:
                    break
                candidate += 1
            minimum = max(minimum, candidate)
        return minimum

    def rt_limits(self, p):
        hi = 255
        seen = False
        for i, s in enumerate(self.samples):
            if not s.get('sampled') or not s.get('enabled') or 'baseline' not in s:
                continue
            seen = True
            override = self.client.record.overrides[i] if self.client and self.client.record else 0
            q = 1022 if override == 99 else (override*1023+50)//100 if override else u16(p, 6)
            release_q = q-(u16(p, 6)-u16(p, 8))
            fixed_release = min(affine(max(0, release_q), s['baseline'], max(s['baseline'], s['bottom'])), s['bottom']-6)
            hi = min(hi, s['bottom']-fixed_release-2)
        return 4, hi if seen else 0

    def update_values(self):
        self.global_value.setText('Deepest' if self.global_actuation.value() == 99 else str(self.global_actuation.value())+'%')
        v = self.key_actuation.value()
        override = self.displayed_override()
        value = 'Deepest' if v == 99 else str(v)+'%'
        self.key_value.setText('Select a key' if not self.selection_made else 'Reading key…' if override is None else
                               ('Global — ' if override == 0 else 'Override — ')+value)
        self.sensitivity_value.setText('{} ADC movement'.format(255-self.sensitivity.value()))

    def displayed_override(self):
        pending_key = ('key', self.key_selection)
        if pending_key in self.pending:
            return self.pending[pending_key][1]
        if 'global' in self.pending:
            return 0
        if self.va and u16(self.va, 18) == self.key_selection:
            return self.va[13]
        return None

    def stage(self, name, value):
        self.update_values()
        if self.loading or not self.online:
            return
        # Both sliders retain the same 1–99 scale. Validate gestures without
        # rescaling either track (which placed equal percentages at unequal x).
        requested = value[1] if name == 'key' else value if name == 'global' else 0
        if requested and self.va:
            minimum = self.minimum_actuation(self.va, value[0] if name == 'key' else None)
            if requested < minimum:
                slider = self.key_actuation if name == 'key' else self.global_actuation
                with QSignalBlocker(slider):
                    slider.setValue(minimum)
                value = (value[0], minimum) if name == 'key' else minimum
        pending_key = ('key', value[0]) if name == 'key' else name
        if name == 'global':
            # A later Global gesture supersedes older unsent individual edits.
            self.pending = {key: val for key, val in self.pending.items() if not isinstance(key, tuple)}
        self.pending[pending_key] = value
        if name == 'global':
            with QSignalBlocker(self.key_actuation):
                self.key_actuation.setValue(value)
        self.update_values()
        self.apply_timer.start()

    def stage_rt(self):
        self.stage('rt', (int(self.rt_enabled.isChecked()), self.rt_press.value(), self.rt_release.value()))

    def stage_sensitivity(self, value):
        if self.loading:
            return
        if not self.va:
            return
        lo, hi = self.rt_limits(self.va)
        if hi < lo:
            return
        movement = max(lo, min(hi, 255-value))
        with QSignalBlocker(self.rt_press), QSignalBlocker(self.rt_release), QSignalBlocker(self.sensitivity):
            self.rt_press.setValue(movement)
            self.rt_release.setValue(movement)
            self.sensitivity.setValue(255-movement)
        self.update_values()
        self.stage_rt()

    def apply_pending(self):
        if not self.pending or self.worker:
            return
        pending_key = next(iter(self.pending))
        value = self.pending.pop(pending_key)
        name = pending_key[0] if isinstance(pending_key, tuple) else pending_key
        def apply():
            if name == 'global':
                self.client.set_global_actuation(value)
            elif name == 'key':
                self.client.set_actuation(*value)
            else:
                self.client.set_rt(*value)
            self.client.active_record()
            return self.client.actuation(self.selected if self.samples and self.samples[self.selected]['sampled'] else 0xffff)
        self.launch('rapid-trigger' if name == 'rt' else 'actuation', apply)

    def dialog_parent(self):
        page = self.actuation_page if self.section == 'actuation' else self.sensors_page if self.section == 'sensors' else self
        return page.parentWidget()

    def confirm(self, title, text):
        was_active = self.timer.isActive()
        self.timer.stop()
        try:
            return QMessageBox.question(self.dialog_parent(), title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
        finally:
            if was_active and self.active:
                self.timer.start()

    def file_dialog(self, save, title, default):
        was_active = self.timer.isActive()
        self.timer.stop()
        try:
            dialog = QFileDialog.getSaveFileName if save else QFileDialog.getOpenFileName
            return dialog(self.dialog_parent(), title, default, 'JSON (*.json)')[0]
        finally:
            if was_active and self.active:
                self.timer.start()


    def show_stored_rows(self):
        if not self.profile:
            return
        rows = []
        for index in range(self.profile.cells):
            v = u16(self.saved_record.canonical, 9+2*index) if self.saved_record else 0
            sample = self.samples[index] if index < len(self.samples) else None
            if self.saved_record is None:
                reason = 'Stored value unavailable' if self.online else 'Reading stored values…'
            elif sample is not None and not sample['sampled']:
                reason = 'Not sampled'
            elif v & 0x8000:
                reason = 'Saved enabled'
            elif v & 0x2000:
                reason = 'Saved retry / disabled'
            elif v & 0x4000:
                reason = 'Saved disabled'
            else:
                reason = 'No stored capture'
            if self.table_mode == 'capturing' and sample is not None:
                reason = 'Held' if held(sample, capturing=True) else 'Captured this session' if sample['capture'] == 1 else 'Retry required' if sample['capture'] in (2, 3) else reason
            rows.append(dict(index=index, reason=reason, high=v & 1023 if v & 0x4000 else None))
        self.show_review_rows(rows, stored=True)

    def show_review_rows(self, rows, pending=False, stored=False):
        self.review_table.setUpdatesEnabled(False)
        try:
            self.review_table.setRowCount(len(rows))
            for row, data in enumerate(rows):
                i = data['index']
                bottom = data.get('high')
                values = ('{}/{}'.format(i//self.profile.cols, i%self.profile.cols),
                          data['reason'], '—' if bottom is None else str(bottom))
                for col, value in enumerate(values):
                    item = self.review_table.item(row, col)
                    if item is None:
                        item = QTableWidgetItem()
                        self.review_table.setItem(row, col, item)
                    item.setText(value)
                    item.setToolTip(data['reason'])
        finally:
            self.review_table.setUpdatesEnabled(True)
        self.review_table.setHorizontalHeaderLabels(('Position', 'Result', 'Stored bottom' if stored else 'Proposed bottom'))
        if stored:
            text = 'Capture in progress — stored bottom values shown until Finish.' if self.table_mode == 'capturing' else 'Stored EC record readback.' if self.saved_record else 'Stored record unavailable; no values are fabricated.'
        else:
            text = 'Reading and validating proposed values…' if pending else 'Proposed values — not saved yet.'
        self.table_source.setText(text)
        self.review_table.setToolTip(text)

    def finish_capture(self):
        if not self.online:
            return
        if self.worker and self.running_operation != 'poll':
            return
        self.review = None
        self.table_mode = 'proposal_pending'
        self.show_review_rows([dict(index=i, reason='Reading proposal…' if sample['sampled'] else 'Not sampled')
                               for i, sample in enumerate(self.samples)], pending=True)
        self.save_button.setEnabled(False)
        if self.worker:
            self.finish_requested = True
            self.finish_button.setEnabled(False)
            return
        self.launch('review', lambda: self.client.review(fast=True))

    def start_capture(self):
        if not self.confirm('Start manual calibration', 'Release every physical key. Start saves a local recovery backup, then begins an unlimited manual capture. Fully press and release each desired key. Existing saved calibration is unchanged until Save and apply. Continue?'):
            return
        folder = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))/'ec42-backups'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/(self.profile.uid.hex()+'-'+datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')+'.json')
        self.log.appendPlainText('Recovery backup destination: '+str(path))
        self.launch('start', lambda: self.client.start(path))

    def retry_capture(self):
        index = self.selected
        self.launch('retry', lambda: self.client.control(5, be16(index)))

    def cancel_capture(self):
        self.pending = {}
        self.apply_timer.stop()
        self.launch('cancel', lambda: self.client.control(4))

    def save_capture(self):
        if self.review and self.confirm('Save and apply EC calibration', 'Apply this reviewed partial calibration and save only the EC record? Untouched saved keys stay enabled; unmeasured new keys and invalid attempts are disabled. All keys must be released.'):
            review = self.review
            self.launch('save', lambda: self.client.apply_review(review))

    def export_backup(self):
        path = self.file_dialog(True, 'Export exact EC backup', 'ec42-backup.json')
        if path:
            def export():
                save_backup(path, self.client.read_record(), self.profile)
                return path
            self.launch('export', export)

    def restore_backup(self):
        path = self.file_dialog(False, 'Restore EC backup', '')
        if not path:
            return
        try:
            if Path(path).stat().st_size > 65536:
                raise ECError('Backup file exceeds size limit')
            raw = load_backup(json.loads(Path(path).read_text()), self.profile)
        except Exception as e:
            QMessageBox.warning(self.parentWidget(), 'Backup rejected', str(e))
            return
        if self.confirm('Restore EC calibration', 'Replace only this keyboard’s EC record with the validated backup? UID identifies a board definition, not a unique unit. Confirm that this is the correct keyboard and release all keys. Vial keymaps are preserved.'):
            self.launch('restore', lambda: self.client.restore(raw))

    def enter_bootloader(self):
        if self.confirm('Enter bootloader', 'Discard any unsaved calibration and enter this keyboard’s bootloader? No firmware will be flashed.'):
            self.launch('bootloader', self.client.bootloader)
