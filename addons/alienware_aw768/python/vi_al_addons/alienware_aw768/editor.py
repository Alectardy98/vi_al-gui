# SPDX-License-Identifier: GPL-2.0-or-later
"""AW768 lighting editor with staged edits and native keyboard readback.

The RP2040 remains responsible for Vial and input. Native lighting operations
own a separate, verified companion interface and run in a bounded worker.
"""
import logging
import re
from dataclasses import replace
from PyQt5 import sip

from PyQt5.QtCore import Qt, QThread, QTimer, QSignalBlocker, QEvent, QObject
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                            QPushButton, QGroupBox, QSlider, QColorDialog, QSpinBox,
                            QLineEdit, QButtonGroup,
                            QSplitter, QScrollArea, QSizePolicy)
from editor.basic_editor import BasicEditor
from vial_device import VialKeyboard
from .identity import is_supported_keyboard
from .protocol import GROUPS, ZONE_GROUPS, EFFECTS, GLOBAL_EFFECTS, MACRO_ZONE, Lighting
from .preview import AW768Preview, HueWheel
from .themes import SCHEMES, encode_theme

PRESET_COLORS = ('#131185','#263a9a','#237ca5','#179431','#227b12','#839b16',
                 '#a58220','#9e5a16','#ad151b','#862459','#762289','#491ab0')
STYLE = """
QWidget#aw768Page { background: #353535; color: #e2e2e4; }
QWidget#aw768Page QLabel, QWidget#aw768Page QCheckBox, QWidget#aw768Page QRadioButton { color: #d9d9dd; }
QWidget#aw768Page QGroupBox { color: #999ba3; border: 1px solid #414247; border-radius: 4px; margin-top: 9px; padding: 10px 7px 6px; }
QWidget#aw768Page QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0 5px; }
QWidget#aw768Page QPushButton, QWidget#aw768Page QComboBox, QWidget#aw768Page QSpinBox, QWidget#aw768Page QLineEdit { background: #2c2d32; color: #dedee3; border: 1px solid #45474f; border-radius: 3px; padding: 5px; }
QWidget#aw768Page QPushButton:hover { border-color: #61b7df; }
QWidget#aw768Page QPushButton:checked { background: #467e9d; border-color: #65c7f5; color: white; }
QWidget#aw768Page QPushButton:disabled { color: #73757e; }
QWidget#aw768Page QRadioButton:disabled, QWidget#aw768Page QCheckBox:disabled { color: #71747c; }
QWidget#aw768Page QPushButton#saveTheme { background: #56aada; border: 0; color: #10191f; font-weight: bold; padding: 10px; }
QWidget#aw768Page QPushButton#saveTheme:disabled { background: #37434e; color: #8c95a0; }
QWidget#aw768Page QSlider::groove:horizontal { height: 6px; background: #41464d; border-radius: 3px; }
QWidget#aw768Page QSlider::sub-page:horizontal { background: #50aacb; border-radius: 3px; }
QWidget#aw768Page QSlider::handle:horizontal { width: 15px; margin: -5px 0; border-radius: 7px; background: #cbd5db; }
"""

def _client_factory(descriptor, uid):
    from .client import Client
    return Client(descriptor, uid)

class LightingJob(QThread):
    """One client operation, with no retries and no GUI work off the Qt thread."""
    def __init__(self, client, factory, descriptor, uid, operation, settings, scheme, parent):
        super().__init__(parent)
        self.client = client
        self.factory = factory
        self.descriptor = descriptor
        self.uid = uid
        self.operation = operation
        self.settings = settings
        self.scheme = scheme
        self.result = None
        self.error = None

    def run(self):
        try:
            if self.client is None:
                self.client = self.factory(self.descriptor, self.uid)
            self.result = (self.client.load() if self.operation == 'load'
                           else self.client.apply(self.settings, self.scheme))
        except Exception as error:
            self.error = str(error)


class AW768Lighting(BasicEditor):
    def __init__(self, client_factory=None, settings_store=None):
        super().__init__()
        self.client_factory = client_factory or _client_factory
        # No PC-side lighting profiles. Keep palette and write-only Macro intent
        # in RAM only; read ordinary settings from the native PCB on connection.
        self.custom_colors = [None] * 6
        self.client = self.worker = self.snapshot = None
        self.active = self.online = self.loading = self._closing = False
        self._generation = self._revision = 0
        self._attempted = False
        self.scheme = 'groups'
        self.schemes = {scheme:{} for scheme in SCHEMES}
        self.selected = {GROUPS[0][0]}
        self.colors = [(255,255,255),(0,0,0)]
        self.active_color = 0
        self.profile_brightness = 10
        self._macro_touched = False
        self._macro_readback = None
        self.root = QWidget(); self._ui_scale=self.root.logicalDpiX()/96.; self.root.installEventFilter(self); self.root.setObjectName('aw768Page'); self.ui_style(self.root,STYLE)
        body = QVBoxLayout(self.root); self.ui_metric(body,'setContentsMargins',12,10,12,10); self.ui_metric(body,'setSpacing',8)
        save_row = QHBoxLayout()
        self.apply_button = QPushButton('Save changes to keyboard')
        self.apply_button.setObjectName('saveTheme')
        self.ui_metric(self.apply_button,'setMinimumSize',300,44)
        save_row.addStretch()
        save_row.addWidget(self.apply_button)
        save_row.addStretch()
        body.addLayout(save_row)

        # The diagram fills the upper area; only the lower third is a dark
        # lighting-control card. Dimensions are Qt display-independent pixels.
        self.content_splitter = QSplitter(Qt.Vertical)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.addWidget(self.build_diagram())
        self.controls_scroll = QScrollArea()
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setFrameShape(QScrollArea.NoFrame)
        self.controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ui_style(self.controls_scroll,'QScrollArea, QScrollArea > QWidget > QWidget {background:#353535;}')
        self.form_group = self.build_lighting_controls()
        self.form_group.setObjectName('aw768Controls')
        self.ui_style(self.form_group,'QWidget#aw768Controls {background:#202022;border:1px solid #45474f;border-radius:6px;} QWidget#aw768Controls QWidget {font-size:11pt;}')
        self.controls_scroll.setWidget(self.form_group)
        self.ui_metric(self.controls_scroll,'setMinimumHeight',210)
        self.content_splitter.addWidget(self.controls_scroll)
        self.content_splitter.setStretchFactor(0, 2)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setSizes([round(600*self._ui_scale), round(300*self._ui_scale)])
        body.addWidget(self.content_splitter, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel('Open this page to load native lighting.')
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.PlainText)
        footer.addWidget(self.status_label, 1)
        self.reload_button = QPushButton('Reload from keyboard')
        self.ui_metric(self.reload_button,'setMinimumHeight',38)
        footer.addWidget(self.reload_button)
        body.addLayout(footer)
        self.identity_label = QLabel('Lighting PCB not loaded')
        self.ui_style(self.identity_label,'font-size:10px;color:#a2a4ae;')
        self.identity_label.setToolTip('Saves target the native lighting profile. No lighting themes are stored on this PC. Native key-reactive effects cannot see RP2040 key activity.')
        body.addWidget(self.identity_label, 0, Qt.AlignRight)
        self.addWidget(self.root, 1)
        self.preview.selectionChanged.connect(self.selection_changed)
        self.speed.valueChanged.connect(self.form_changed);self.brightness.valueChanged.connect(self.brightness_changed)
        self.wheel.colorChanged.connect(self.set_chosen_color)
        for spin in self.rgb:spin.valueChanged.connect(self.rgb_changed)
        self.hex_input.editingFinished.connect(self.hex_changed)
        self.apply_button.clicked.connect(self.apply_selected);self.reload_button.clicked.connect(self.reload)
        self.rebuild_selection();self.set_controls()
    def ui_metric(self,target,method,*values):
        """Scale only this lighting page when the application's DPI is unscaled.

        Qt already handles DPI on some platforms/launch configurations. Its
        widget logical DPI is then 96, so no second scaling is applied here.
        Store base values on each owned object for later monitor/font changes.
        """
        templates=getattr(target,'_aw_metrics',{})
        templates[method]=values
        target._aw_metrics=templates
        getattr(target,method)(*(round(value*self._ui_scale) for value in values))

    def ui_style(self,target,style):
        target._aw_style=style
        target.setStyleSheet(re.sub(r'(\d+(?:\.\d+)?)px',
            lambda match:'{}px'.format(round(float(match.group(1))*self._ui_scale)),style))

    def eventFilter(self,target,event):
        if target is self.root and event.type() in (
                QEvent.Show,QEvent.FontChange,QEvent.ApplicationFontChange,
                getattr(QEvent,'ScreenChangeInternal',216)):
            QTimer.singleShot(0,self.refresh_display_scale)
        return super().eventFilter(target,event)

    def refresh_display_scale(self):
        if sip.isdeleted(self.root):return
        scale=self.root.logicalDpiX()/96.
        if abs(scale-self._ui_scale)<.001:return
        self._ui_scale=scale
        for target in [self.root,*self.root.findChildren(QObject)]:
            for method,values in getattr(target,'_aw_metrics',{}).items():
                getattr(target,method)(*(round(value*scale) for value in values))
            style=getattr(target,'_aw_style',None)
            if style is not None:self.ui_style(target,style)
        self.preview.set_ui_scale(scale)
        self.wheel.set_ui_scale(scale)
        self.root.updateGeometry()

    def build_diagram(self):
        diagram = QWidget()
        visual = QVBoxLayout(diagram)
        self.ui_metric(visual,'setContentsMargins',0,0,0,0)
        self.ui_metric(visual,'setSpacing',6)
        self.check_container = QWidget()
        self.check_layout = QGridLayout(self.check_container)
        self.ui_metric(self.check_layout,'setContentsMargins',0,0,0,0)
        self.ui_metric(self.check_layout,'setSpacing',6)
        self.checks = {}
        self.selection_scroll = QScrollArea()
        self.selection_scroll.setWidgetResizable(True)
        self.selection_scroll.setFrameShape(QScrollArea.NoFrame)
        self.selection_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ui_style(self.selection_scroll,'QScrollArea, QScrollArea > QWidget > QWidget {background:#353535;}')
        self.ui_metric(self.selection_scroll,'setMinimumWidth',250)
        self.ui_metric(self.selection_scroll,'setMaximumWidth',280)
        self.selection_scroll.setWidget(self.check_container)
        self.ui_style(self.check_container,'QPushButton {font-size:11pt;}')
        self.check_layout.setAlignment(Qt.AlignTop)
        keyboard_row = QHBoxLayout()
        self.ui_metric(keyboard_row,'setSpacing',10)
        group_column = QVBoxLayout()
        self.ui_metric(group_column,'setSpacing',6)
        group_column.addWidget(QLabel('KEY GROUPS'))
        group_column.addWidget(self.selection_scroll,1)
        keyboard_row.addLayout(group_column)
        self.preview = AW768Preview()
        self.preview.set_ui_scale(self._ui_scale)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        keyboard_row.addWidget(self.preview, 1)
        visual.addLayout(keyboard_row, 1)
        return diagram

    def build_lighting_controls(self):
        panel = QWidget()
        row = QHBoxLayout(panel)
        self.ui_metric(row,'setContentsMargins',8,10,8,10)
        self.ui_metric(row,'setSpacing',5)

        # Effect and color selection.
        effect_column = QVBoxLayout()
        self.selection_label = QLabel('Select a lighting group')
        self.selection_label.setWordWrap(True)
        self.ui_metric(self.selection_label,'setMaximumHeight',34)
        effect_column.addWidget(self.selection_label)
        self.effect_mode = None
        self.effect_buttons = {}
        self.effect_group = QButtonGroup(self.root)
        self.effect_grid = QGridLayout()
        self.ui_metric(self.effect_grid,'setSpacing',4)
        effect_column.addLayout(self.effect_grid)
        self.effect_note = QLabel()
        self.effect_note.setWordWrap(True)
        effect_column.addWidget(self.effect_note)
        self.morph_end_button = QPushButton('End color…')
        self.morph_end_button.setToolTip('Choose the second color used by Morph.')
        self.morph_end_button.clicked.connect(self.choose_morph_end_color)
        effect_column.addWidget(self.morph_end_button)
        effect_column.addStretch()
        row.addLayout(effect_column, 2)

        self.wheel = HueWheel()
        self.wheel.set_ui_scale(self._ui_scale)
        self.ui_metric(self.wheel,'setMinimumSize',110,110)
        self.ui_metric(self.wheel,'setMaximumSize',150,150)
        row.addWidget(self.wheel, 1, Qt.AlignCenter)

        # Precise RGB/hex editing stays adjacent to the wheel.
        color_column = QVBoxLayout()
        color_column.addWidget(QLabel('COLOR VALUE'))
        rgb_row = QHBoxLayout()
        self.ui_metric(rgb_row,'setSpacing',3)
        self.rgb = []
        for name in ('R', 'G', 'B'):
            rgb_row.addWidget(QLabel(name))
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.setButtonSymbols(QSpinBox.NoButtons)
            self.ui_metric(spin,'setMinimumWidth',32)
            self.ui_metric(spin,'setMaximumWidth',54)
            rgb_row.addWidget(spin)
            self.rgb.append(spin)
        color_column.addLayout(rgb_row)
        self.hex_input = QLineEdit()
        self.hex_input.setMaxLength(7)
        self.hex_input.setPlaceholderText('#RRGGBB')
        color_column.addWidget(self.hex_input)
        more = QPushButton('More colors…')
        more.clicked.connect(lambda: self.choose_color(self.active_color))
        color_column.addWidget(more)
        color_column.addStretch()
        row.addLayout(color_column, 2)

        # Presets and session-only palette share one compact column.
        palettes = QVBoxLayout()
        self.ui_metric(palettes,'setSpacing',4)
        presets = QGroupBox('PRESET COLORS')
        palette = QGridLayout(presets)
        self.ui_metric(palette,'setContentsMargins',5,8,5,5)
        self.ui_metric(palette,'setSpacing',3)
        for i, value in enumerate(PRESET_COLORS):
            button = QPushButton()
            self.ui_metric(button,'setFixedHeight',20)
            self.ui_metric(button,'setMinimumWidth',16)
            button.setToolTip(value)
            self.ui_style(button,'background:'+value+';border:1px solid #666;')
            button.clicked.connect(lambda checked=False, v=value: self.set_chosen_color(QColor(v)))
            palette.addWidget(button, i//6, i%6)
        palettes.addWidget(presets)
        custom = QGroupBox('SESSION COLORS')
        custom_row = QHBoxLayout(custom)
        self.ui_metric(custom_row,'setContentsMargins',5,8,5,5)
        self.ui_metric(custom_row,'setSpacing',3)
        self.custom_buttons = []
        for i in range(6):
            button = QPushButton('+')
            self.ui_metric(button,'setMinimumWidth',16)
            button.setToolTip('Remember a color for this session; right-click to replace it. Nothing is saved on this PC.')
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.clicked.connect(lambda checked=False, index=i: self.custom_color(index))
            button.customContextMenuRequested.connect(lambda point, index=i: self.custom_color(index, True))
            custom_row.addWidget(button)
            self.custom_buttons.append(button)
        palettes.addWidget(custom)
        palettes.addStretch()
        row.addLayout(palettes, 2)

        sliders = QVBoxLayout()
        self.speed_label = QLabel()
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(1, 3)
        self.speed.setValue(2)
        self.ui_metric(self.speed,'setMinimumHeight',25)
        self.speed.setToolTip('Slow → Medium → Fast. Existing device default is retained until changed.')
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel('TEMPO'))
        label_row.addStretch()
        label_row.addWidget(self.speed_label)
        sliders.addLayout(label_row)
        sliders.addWidget(self.speed)
        self.brightness_label = QLabel()
        self.brightness = QSlider(Qt.Horizontal)
        self.brightness.setRange(1, 10)
        self.brightness.setValue(10)
        self.ui_metric(self.brightness,'setMinimumHeight',25)
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel('BRIGHTNESS'))
        label_row.addStretch()
        label_row.addWidget(self.brightness_label)
        sliders.addLayout(label_row)
        sliders.addWidget(self.brightness)
        hint = QLabel('Brightness affects the whole native profile.')
        hint.setWordWrap(True)
        self.ui_style(hint,'font-size:10px;color:#a2a4ae;')
        sliders.addWidget(hint)
        sliders.addStretch()
        row.addLayout(sliders, 2)
        return panel

    @property
    def drafts(self):
        return self.schemes[self.scheme]

    def valid(self):
        return (isinstance(self.device,VialKeyboard) and self.device.keyboard is not None and
                is_supported_keyboard(self.device.desc,self.device.keyboard.keyboard_id))

    def rebuild(self,device):
        self.active=False;self._generation+=1;super().rebuild(device)
        self.online=self._attempted=False;self.snapshot=None
        self._macro_touched=False;self._macro_readback=None
        self.schemes={scheme:{} for scheme in SCHEMES}
        if self.worker is None:self.close_client()
        self.identity_label.setText('Lighting PCB not loaded')
        self.set_status('Open this page to read native lighting.')
        self.refresh_custom_colors();self.set_controls()

    def activate(self):
        self.active=True
        if self.valid() and not self._attempted and self.worker is None:self.reload()

    def deactivate(self):
        self.active=False

    def shutdown(self):
        self.active=False;self._closing=True
        if self.worker is not None:return False
        self.close_client();return True

    def close_client(self,client=None):
        client=self.client if client is None else client
        if client is None:return
        if client is self.client:self.client=None
        try:client.close()
        except Exception:logging.exception('AW768 lighting handle close failed')

    def set_status(self,text,error=False):
        self.status_label.setText(text)
        self.ui_style(self.status_label,'color:#ff9999;' if error else 'color:#bdc4d0;')

    def rebuild_selection(self):
        while self.check_layout.count():
            item=self.check_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.checks={}
        for i,(mask,label) in enumerate(SCHEMES[self.scheme]):
            box=QPushButton(('{}  '.format(i+1) if self.scheme!='all' else '')+label);box.setCheckable(True);self.ui_metric(box,'setMinimumHeight',38)
            box.setProperty('awMask',mask);box.toggled.connect(lambda checked,m=mask:self.toggle_mask(m,checked))
            self.check_layout.addWidget(box,i//2,i%2);self.checks[mask]=box
        modes = GLOBAL_EFFECTS if self.scheme=='all' else ((0,'Color'),) if self.scheme=='fine' else EFFECTS
        self.rebuild_effect_buttons(((-1,'Off'),) + tuple(modes) + ((-2,'Default blue'),))
        self.preview.set_groups(SCHEMES[self.scheme],self.scheme)
        self.selection_changed(self.selected)

    def toggle_mask(self,mask,checked):
        if self.loading:return
        selected=set(self.selected)
        if checked:selected.add(mask)
        else:selected.discard(mask)
        self.selection_changed(selected)

    def selection_changed(self,selection):
        allowed={mask for mask,_ in SCHEMES[self.scheme]};self.selected=set(selection)&allowed
        self.loading=True
        try:
            for mask,box in self.checks.items():box.setChecked(mask in self.selected)
        finally:self.loading=False
        self.preview.set_selected(self.selected)
        self.show_selection();self.set_controls()

    def selected_mask(self):
        if self.scheme=='groups' and MACRO_ZONE in self.selected:return MACRO_ZONE
        return next((mask for mask,_ in SCHEMES[self.scheme] if mask in self.selected),None)

    def show_selection(self):
        names=[label for mask,label in SCHEMES[self.scheme] if mask in self.selected]
        self.selection_label.setText(', '.join(names) if names else 'Select a group on the keyboard')
        self.selection_label.setToolTip('')
        if MACRO_ZONE in self.selected and self.scheme=='groups' and (self._macro_readback is None or len(set(self._macro_readback))!=1):
            self.selection_label.setText(self.selection_label.text()+' • readback is unavailable')
        if MACRO_ZONE in self.selected and self.scheme=='groups':
            self.selection_label.setToolTip('Macro covers X and M1–M5. When device readback is unavailable, the preview shows the chosen or last-sent session color. Save sets all three native modes together.')
        setting=self.drafts.get(self.selected_mask())
        if setting is None:return
        self.loading=True
        try:
            mode=-1 if setting.mode==0 and setting.color0==(0,0,0) else setting.mode
            self.show_effect(mode);self.colors=[setting.color0,setting.color1]
            self.speed.setRange(0 if setting.tempo==0 else 1,3)
            self.speed.setValue(0 if setting.tempo==0 else 4-setting.tempo)
            self.brightness.setValue(self.profile_brightness)
            self.sync_color_controls()
        finally:self.loading=False
        self.set_controls()

    def form_settings(self):
        mode=self.effect_mode;c0,c1=map(tuple,self.colors)
        if mode==-1:mode=0;c0=c1=(0,0,0)
        elif mode==-2:mode=0;c0=(0,240,240);c1=(0,0,0)
        if self.scheme=='groups' and MACRO_ZONE in self.selected and mode!=0:
            raise ValueError('Macro supports Color or Off only; deselect it to edit animated effects.')
        tempo=0 if self.speed.value()==0 else 4-self.speed.value()
        return Lighting(mode,c0,c1,tempo,self.profile_brightness).validate()

    def set_controls(self):
        supported=self.valid() and not self._closing;busy=self.worker is not None
        editable=supported and self.online and (not busy or self.worker.operation=='apply') and bool(self.selected)
        self.form_group.setEnabled(editable)
        self.check_container.setEnabled(supported and self.online and not busy)
        self.preview.setEnabled(supported and self.online and not busy)
        valid=False
        try:
            valid=bool(self.drafts) and all(setting.validate() for setting in self.drafts.values())
        except ValueError:pass
        self.apply_button.setEnabled(editable and not busy and valid)
        self.reload_button.setEnabled(supported and not busy)
        self.update_effect_controls()

    def update_effect_controls(self):
        mode=self.effect_mode;colorful=mode not in (-1,-2,4,10,None)
        macro_selected=self.scheme=='groups' and MACRO_ZONE in self.selected
        for value,button in self.effect_buttons.items():
            button.setEnabled(not macro_selected or value in (-2,-1,0))
        self.morph_end_button.setVisible(mode==3)
        self.active_color=0
        for control in [self.wheel,self.hex_input,*self.rgb]:control.setEnabled(colorful)
        self.speed.setEnabled(mode not in (-1,-2,0,None))
        self.speed_label.setText({0:'Device default',1:'Slow',2:'Medium',3:'Fast'}.get(self.speed.value(),''))
        self.brightness_label.setText('{}%'.format(self.profile_brightness*10))
        color=QColor(*self.colors[1])
        contrast='#101014' if color.lightness()>140 else '#ffffff'
        self.ui_style(self.morph_end_button,'background:{};color:{};'.format(color.name(),contrast))

    def refresh_preview(self):
        self.preview.set_settings(self.drafts);self.preview.set_selected(self.selected)
        for mask,box in self.checks.items():
            setting=self.drafts.get(mask)
            if setting:box.setToolTip('{} • {} • {}'.format(QColor(*setting.color0).name(),dict(GLOBAL_EFFECTS).get(setting.mode,'unknown'),QColor(*setting.color1).name()))

    def form_changed(self,*_):
        if self.loading or not self.online:return
        try:
            setting=self.form_settings()
            for mask in self.selected:self.drafts[mask]=setting
            if self.scheme=='groups' and MACRO_ZONE in self.selected:self._macro_touched=True
            self._revision+=1;self.refresh_preview();self.set_status('Unapplied changes. Save changes to keyboard sends them to the lighting PCB.')
        except ValueError as error:self.set_status(str(error),True)
        self.set_controls()

    def brightness_changed(self,value):
        if not self.loading:
            self.profile_brightness=value
            for scope in self.schemes:
                self.schemes[scope]={mask:replace(setting,brightness=value) for mask,setting in self.schemes[scope].items()}
        self.form_changed()

    def rebuild_effect_buttons(self,options):
        for button in self.effect_buttons.values():
            self.effect_group.removeButton(button)
        while self.effect_grid.count():
            item=self.effect_grid.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        self.effect_buttons={}
        for index,(mode,label) in enumerate(options):
            button=QPushButton('Rainbow' if mode==10 else label)
            button.setToolTip(label)
            button.setCheckable(True)
            self.ui_metric(button,'setMinimumHeight',30)
            button.clicked.connect(lambda checked=False,value=mode:self.choose_effect(value))
            self.effect_group.addButton(button)
            self.effect_buttons[mode]=button
            self.effect_grid.addWidget(button,index//2,index%2)

    def show_effect(self,mode):
        self.effect_mode=mode
        self.effect_group.setExclusive(False)
        for value,button in self.effect_buttons.items():button.setChecked(value==mode)
        self.effect_group.setExclusive(True)
        self.effect_note.setText('Stored mode {} (unsupported)'.format(mode) if mode not in self.effect_buttons else '')
        self.effect_note.setVisible(mode not in self.effect_buttons)

    def choose_effect(self,mode):
        button=self.effect_buttons.get(mode)
        if button is None or not button.isEnabled():return
        self.show_effect(mode)
        self.form_changed()

    def choose_morph_end_color(self):
        if self.effect_mode!=3:return
        color=QColorDialog.getColor(QColor(*self.colors[1]),self.root,'Choose Morph end color')
        if color.isValid():
            self.colors[1]=(color.red(),color.green(),color.blue())
            self.form_changed()

    def sync_color_controls(self):
        color=QColor(*self.colors[self.active_color]);self.wheel.setColor(color)
        for spin,value in zip(self.rgb,self.colors[self.active_color]):
            with QSignalBlocker(spin):spin.setValue(value)
        self.hex_input.setText(color.name().upper())

    def set_chosen_color(self,color):
        if not color.isValid():return
        self.colors[self.active_color]=(color.red(),color.green(),color.blue())
        self.sync_color_controls();self.form_changed()

    def rgb_changed(self,*_):
        if not self.loading:self.set_chosen_color(QColor(*(spin.value() for spin in self.rgb)))

    def hex_changed(self):
        value=self.hex_input.text().strip()
        import re
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',value):
            self.set_status('Enter a six-digit color, for example #00F0F0. No settings were sent.',True);return
        self.set_chosen_color(QColor(value))

    def choose_color(self,index):
        color=QColorDialog.getColor(QColor(*self.colors[index]),self.root,'Choose lighting color')
        if color.isValid():self.active_color=index;self.set_chosen_color(color)

    def macro_intent(self,snapshot,brightness,previous=None,sent=None):
        colors=getattr(snapshot,'macro_colors',None)
        if colors is not None and len(set(colors))==1:
            return Lighting(0,colors[0],(0,0,0),2,brightness)
        if sent is not None:return replace(sent,brightness=brightness)
        if previous is not None:return replace(previous,brightness=brightness)
        # An explicit draft, not a fabricated device measurement. Legacy native
        # firmware cannot read Macro colors, so never restore a PC default.
        return Lighting(0,(0,128,255),(0,0,0),2,brightness)

    def custom_color(self,index,replace_existing=False):
        color=self.custom_colors[index]
        if replace_existing or color is None:
            self.custom_colors[index]=QColor(*self.colors[self.active_color])
            self.refresh_custom_colors()
        else:self.set_chosen_color(color)

    def refresh_custom_colors(self):
        for i,button in enumerate(self.custom_buttons):
            color=self.custom_colors[i]
            button.setText('' if color is not None else '+')
            self.ui_style(button,'background:{};border:1px solid #666;'.format(color.name()) if color is not None else '')

    def reload(self):
        if self.valid() and not self._closing and self.worker is None:self._attempted=True;self.start_job('load')

    def apply_selected(self):
        if not self.valid() or not self.online or self.worker is not None or self._closing:return
        try:
            # Every draft in this layout is saved, so individually edited groups
            # retain their own effect/colors instead of only saving the last click.
            encode_theme(self.scheme,self.drafts)
            settings=dict(self.drafts)
            if self.scheme=='groups' and not self._macro_touched:settings.pop(MACRO_ZONE,None)
            if self.scheme=='groups' and MACRO_ZONE in settings and self.snapshot is not None:
                native=self.snapshot.settings_for('groups')
                if all(value==native.get(mask) for mask,value in settings.items() if mask!=MACRO_ZONE):
                    settings={MACRO_ZONE:settings[MACRO_ZONE]}
            self.start_job('apply',settings)
        except ValueError as error:self.set_status(str(error),True)

    def start_job(self,operation,settings=None):
        job=LightingJob(self.client,self.client_factory,dict(self.device.desc),self.device.keyboard.keyboard_id,
                        operation,dict(settings or {}),self.scheme,self.root)
        job.generation=self._generation;job.revision=self._revision
        self.worker=job;job.finished.connect(lambda:self.completed(job))
        self.set_status('Reading keyboard lighting…' if operation=='load' else 'Saving keyboard lighting and checking readback…')
        self.set_controls();job.start()

    def completed(self,job):
        self.worker=None
        try:
            if self._closing or job.generation!=self._generation:self.close_client(job.client);return
            self.client=job.client
            if job.error:raise ValueError(job.error)
            previous=self.schemes;actual={scope:job.result.settings_for(scope) for scope in SCHEMES}
            brightness=next(iter(actual[job.scheme].values())).brightness
            self._macro_readback=getattr(job.result,'macro_colors',None)
            actual['groups'][MACRO_ZONE]=self.macro_intent(job.result,brightness,previous['groups'].get(MACRO_ZONE),job.settings.get(MACRO_ZONE) if job.operation=='apply' else None)
            brightness=next(iter(actual[job.scheme].values())).brightness
            if not 1<=brightness<=10:raise ValueError('Unsupported native brightness.')
            if job.operation=='load':self.schemes=actual;self.profile_brightness=brightness;self._macro_touched=False
            else:
                current=dict(previous[job.scheme])
                self.schemes={scope:dict(values) for scope,values in actual.items()}
                if job.revision!=self._revision:
                    self.schemes[job.scheme]={mask:(current[mask] if current.get(mask)!=job.settings.get(mask) else setting)
                                               for mask,setting in actual[job.scheme].items()}
                    self.schemes={scope:{mask:replace(v,brightness=self.profile_brightness) for mask,v in values.items()} for scope,values in self.schemes.items()}
                else:self.profile_brightness=brightness;self._macro_touched=False
            if job.operation=='apply' and MACRO_ZONE in job.settings:
                self._macro_touched=self.schemes['groups'][MACRO_ZONE].color0!=job.settings[MACRO_ZONE].color0
            self.snapshot=job.result;self.online=True
            self.identity_label.setText('Native profile {} • {}'.format(job.result.profile,job.result.variant))
            self.show_selection();self.refresh_preview()
            self.set_status('Lighting loaded. Changes wait for Save changes to keyboard.' if job.operation=='load' else
                            'Keyboard updated and read back. Newer edits remain unapplied.' if job.revision!=self._revision else
                            'Keyboard lighting saved; settings readback verified. No PC theme was saved.')
            if job.operation=='apply' and getattr(job.result,'macro_sent',None) is not None and self._macro_readback is None:
                self.set_status('Macro color sent to all three native modes; this firmware has no Macro color readback. Other zones were verified.'+(' Newer edits remain unapplied.' if job.revision!=self._revision else ''))
        except Exception as error:
            self.online=False;self.close_client(job.client)
            self.set_status('{} — Reload before retrying; no automatic write retry.'.format(error),True)
        finally:
            job.deleteLater();self.set_controls()
            if not self._closing and job.generation!=self._generation and self.active and self.valid() and not self._attempted:QTimer.singleShot(0,self.reload)
