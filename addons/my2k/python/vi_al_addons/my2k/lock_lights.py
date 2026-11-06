# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import Qt,QEvent
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGroupBox,QGridLayout,
    QLabel,QCheckBox,QPushButton,QColorDialog,QTableWidget,QAbstractItemView,
    QHeaderView,QComboBox,QSpinBox,QScrollArea,QMessageBox)
from editor.basic_editor import BasicEditor
from vial_device import VialKeyboard
from vi_al_addons.my2k.protocol import RgbLed
from vi_al_addons.my2k.lock_lights_protocol import LockLightsClient,TRIGGERS,EFFECTS

# Definition-order indices are preserved, not inferred from screen positions.
FIXED = (('Under Cap',((1,'Scroll Lock'),(0,'Caps Lock'),(5,'Num Lock'))),
         ('100NG',((3,'Caps Lock'),(4,'Num Lock'))))


def color_button(button,color):
    q=QColor(*color)
    button.setText(q.name().upper())
    button.setStyleSheet('QPushButton { background-color: %s; color: %s; padding: 5px; }' %
                        (q.name(),'black' if q.lightness()>128 else 'white'))


class RuleTable(QTableWidget):
    def eventFilter(self,widget,event):
        # Cell widgets receive mouse/focus events directly. Keep the selected
        # priority row in sync so Move up/down applies to the rule being edited.
        if event.type() in (QEvent.MouseButtonPress,QEvent.FocusIn):
            row=widget.property('ruleRow')
            if isinstance(row,int) and 0<=row<self.rowCount():self.selectRow(row)
        return super().eventFilter(widget,event)


class LockLights(BasicEditor):
    def __init__(self,layout_editor):
        super().__init__()
        self.keyboard=None
        self.client=None
        self.loading=False
        self.revision=0
        self.fixed={}
        page=QWidget();body=QVBoxLayout(page)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame);scroll.setWidget(page);self.addWidget(scroll)
        groups=QHBoxLayout()
        for title,indicators in FIXED:
            group=QGroupBox(title);grid=QGridLayout(group)
            for row,(index,name) in enumerate(indicators):
                marker=QLabel('●');marker.setFixedSize(24,24);marker.setAlignment(Qt.AlignCenter);marker.setStyleSheet('color: %s; background-color: #333333; border-radius: 9px; padding: 2px; font-size: 22px;'%('white' if title=='Under Cap' else 'red'))
                enabled=QCheckBox(name);button=QPushButton('Color…')
                enabled.clicked.connect(lambda checked,i=index:self.save_fixed(i))
                button.clicked.connect(lambda checked=False,i=index:self.choose_fixed(i))
                grid.addWidget(marker,row,0);grid.addWidget(enabled,row,1);grid.addWidget(button,row,2)
                self.fixed[index]=(enabled,button)
            grid.setColumnStretch(1,1)
            groups.addWidget(group,1)
        body.addLayout(groups)
        self.square=QGroupBox('LED Square');box=QVBoxLayout(self.square)
        hint=QLabel('First matching enabled rule wins (top to bottom). None never matches. Layers use the keyboard’s actual active layer state.')
        hint.setWordWrap(True);box.addWidget(hint)
        self.table=RuleTable(0,7)
        self.table.setHorizontalHeaderLabels(['Enabled','Trigger','Layer','Color','Effect','Speed','Priority'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setMinimumHeight(150);self.table.setMaximumHeight(340)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch)
        box.addWidget(self.table)
        buttons=QHBoxLayout()
        self.add_btn=QPushButton('Add rule');self.remove_btn=QPushButton('Remove');self.up_btn=QPushButton('Move up');self.down_btn=QPushButton('Move down')
        for button,slot in ((self.add_btn,self.add_rule),(self.remove_btn,self.remove_rule),(self.up_btn,lambda:self.move_rule(-1)),(self.down_btn,lambda:self.move_rule(1))):
            button.clicked.connect(slot);buttons.addWidget(button)
        box.addLayout(buttons)
        fallback=QHBoxLayout();self.fallback=QCheckBox('Fallback color when no rule matches');self.fallback_color=(0,0,0);self.fallback_btn=QPushButton();color_button(self.fallback_btn,self.fallback_color)
        self.fallback.clicked.connect(self.mark_dirty);self.fallback_btn.clicked.connect(self.choose_fallback)
        fallback.addWidget(self.fallback,1);fallback.addWidget(self.fallback_btn);box.addLayout(fallback)
        self.save_btn=QPushButton('Update LED Square');self.save_btn.clicked.connect(self.save_rules);box.addWidget(self.save_btn)
        self.reload_btn=QPushButton('Reload from keyboard');self.reload_btn.clicked.connect(self.reload);box.addWidget(self.reload_btn)
        self.status=QLabel('Reading keyboard configuration…');self.status.setWordWrap(True);box.addWidget(self.status)
        body.addWidget(self.square,1)

    def valid(self):
        if not isinstance(self.device,VialKeyboard) or not self.device.keyboard:return False
        data=self.device.keyboard.amk_rgb_indicator
        return bool(data and tuple(entry.get('index') for entry in data.get('indicators',[]))==(125,126,112,64,65,127))

    def rebuild(self,device):
        super().rebuild(device)
        if self.valid():self.keyboard=device.keyboard;self.reload()

    def activate(self):
        if self.keyboard:self.reload()

    def mark_dirty(self,*args):
        if not self.loading:self.status.setText('Unsaved LED Square changes — click Update LED Square. Fixed indicators save separately as before.')

    def reload(self):
        self.client=None;self.loading=True
        try:
            for index,(enabled,button) in self.fixed.items():
                self.keyboard.reload_rgb_indicator(index)
                led=self.keyboard.amk_rgb_indicator['leds'][index]
                enabled.setEnabled(bool(self.keyboard.amk_rgb_indicator.get('on_off')))
                enabled.setChecked(bool(led.get_on()))
                q=QColor.fromHsv(int(led.get_hue()*359/255),led.get_sat(),led.get_val())
                color_button(button,(q.red(),q.green(),q.blue()))
            client=LockLightsClient(self.keyboard);caps=client.capabilities();values=client.read()
            self.client=client;self.revision=caps['revision'];self.set_values(values)
            self.status.setText(('Your previous Caps indicator behavior is preserved until you save these rules. The new default is None/off. ' if caps['legacy'] else 'LED Square settings read from keyboard. ')+str(caps['remaining'])+' journal slots available.'+(' Flash reports an error.' if caps['error'] else ''))
        except (OSError,RuntimeError,ValueError,IndexError) as error:
            self.status.setText(str(error))
        finally:
            self.loading=False
            for widget in (self.table,self.add_btn,self.remove_btn,self.up_btn,self.down_btn,self.fallback,self.fallback_btn,self.save_btn):widget.setEnabled(self.client is not None)
            self.add_btn.setEnabled(self.client is not None and self.table.rowCount()<8)

    def set_values(self,values):
        self.table.setRowCount(0)
        for rule in values['rules']:self.insert_rule(rule)
        self.fallback.setChecked(values['fallback_enabled']);self.fallback_color=tuple(values['fallback']);color_button(self.fallback_btn,self.fallback_color)

    def values(self):
        rules=[]
        for row in range(self.table.rowCount()):
            enabled,trigger,layer,color,effect,speed,_=[self.table.cellWidget(row,col) for col in range(7)]
            rules.append(dict(enabled=enabled.isChecked(),trigger=trigger.currentIndex(),layer=layer.value() if trigger.currentIndex()==4 else 0,color=tuple(color.property('rgb')),effect=effect.currentIndex(),speed=speed.value()))
        return dict(rules=rules,fallback_enabled=self.fallback.isChecked(),fallback=self.fallback_color)

    def insert_rule(self,rule):
        row=self.table.rowCount();self.table.insertRow(row)
        enabled=QCheckBox();enabled.setChecked(rule['enabled']);enabled.clicked.connect(self.mark_dirty)
        trigger=QComboBox();trigger.addItems(TRIGGERS);trigger.setCurrentIndex(rule['trigger'])
        layer=QSpinBox();layer.setRange(0,3);layer.setValue(rule['layer']);layer.setEnabled(rule['trigger']==4)
        trigger.currentIndexChanged.connect(lambda index:(layer.setEnabled(index==4),self.mark_dirty()))
        layer.valueChanged.connect(self.mark_dirty)
        color=QPushButton();color.setProperty('rgb',tuple(rule['color']));color_button(color,rule['color']);color.clicked.connect(lambda checked=False,b=color:self.choose_rule_color(b))
        effect=QComboBox();effect.addItems(EFFECTS);effect.setCurrentIndex(rule['effect']);effect.currentIndexChanged.connect(self.mark_dirty)
        effect.setToolTip('Rainbow cycles hue using the selected color’s maximum channel as brightness.')
        speed=QSpinBox();speed.setRange(0,15);speed.setValue(rule['speed']);speed.valueChanged.connect(self.mark_dirty);speed.setToolTip('0 = 4-second cycle; 15 = 250-ms cycle. Solid ignores speed.');speed.setEnabled(rule['effect']!=0);effect.currentIndexChanged.connect(lambda index:speed.setEnabled(index!=0))
        priority=QLabel(str(row+1))
        for col,widget in enumerate((enabled,trigger,layer,color,effect,speed,priority)):
            widget.setProperty('ruleRow',row);widget.installEventFilter(self.table);self.table.setCellWidget(row,col,widget)
        self.add_btn.setEnabled(self.table.rowCount()<8)

    def add_rule(self):
        if self.table.rowCount()>=8:return
        self.insert_rule(dict(trigger=0,enabled=True,layer=0,color=(0,255,0),effect=0,speed=8));self.table.selectRow(self.table.rowCount()-1);self.mark_dirty()

    def remove_rule(self):
        row=self.table.currentRow()
        if row<0:return
        values=self.values();values['rules'].pop(row);self.set_values(values);self.mark_dirty()

    def move_rule(self,delta):
        row=self.table.currentRow();other=row+delta
        if row<0 or not 0<=other<self.table.rowCount():return
        values=self.values();rules=values['rules'];rules[row],rules[other]=rules[other],rules[row];self.set_values(values);self.table.selectRow(other);self.mark_dirty()

    def choose_rule_color(self,button):
        chosen=QColorDialog.getColor(QColor(*button.property('rgb')),None,'LED Square rule color')
        if chosen.isValid():
            color=(chosen.red(),chosen.green(),chosen.blue());button.setProperty('rgb',color);color_button(button,color);self.mark_dirty()

    def choose_fallback(self):
        chosen=QColorDialog.getColor(QColor(*self.fallback_color),None,'LED Square fallback color')
        if chosen.isValid():self.fallback_color=(chosen.red(),chosen.green(),chosen.blue());color_button(self.fallback_btn,self.fallback_color);self.mark_dirty()

    def save_rules(self):
        if not self.client:return False
        try:
            self.client.apply(self.revision,**self.values())
            self.revision=self.client.capabilities()['revision'];self.loading=True;self.set_values(self.client.read());self.loading=False
            self.status.setText('LED Square saved on Main flash; durable acknowledgement and configuration readback match.')
            return True
        except (OSError,RuntimeError,ValueError) as error:
            self.loading=False
            self.status.setText(str(error));QMessageBox.warning(None,'LED Square update failed',str(error));return False

    def choose_fixed(self,index):
        led=self.keyboard.amk_rgb_indicator['leds'][index]
        chosen=QColorDialog.getColor(QColor.fromHsv(int(led.get_hue()*359/255),led.get_sat(),led.get_val()),None,'Lock indicator color')
        if chosen.isValid():self.save_fixed(index,chosen)

    def save_fixed(self,index,color=None):
        old=self.keyboard.amk_rgb_indicator['leds'][index]
        led=RgbLed(index,*old.pack())
        led.set_on(self.fixed[index][0].isChecked())
        if color is not None:
            h,s,v,_=color.getHsvF();led.set_hue(round(max(0,h)*255));led.set_sat(round(s*255));led.set_val(round(v*255))
        try:
            self.keyboard.apply_rgb_indicator(index,led)
            self.keyboard.reload_rgb_indicator(index)
            actual=self.keyboard.amk_rgb_indicator['leds'][index]
            if actual is led or actual.pack()!=led.pack():raise RuntimeError('Lock indicator readback differs from the requested value.')
            q=QColor.fromHsv(int(actual.get_hue()*359/255),actual.get_sat(),actual.get_val());color_button(self.fixed[index][1],(q.red(),q.green(),q.blue()))
        except (OSError,RuntimeError,ValueError) as error:
            self.status.setText(str(error));QMessageBox.warning(None,'Lock indicator update failed',str(error))
