# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtWidgets import QVBoxLayout, QPushButton, QHBoxLayout, QGridLayout, QLabel, QCheckBox, QMessageBox
from PyQt5.QtCore import QSize, Qt, QRect
from PyQt5.QtGui import QPalette, QPainter, QBrush, QPixmap, QImage, QColor
from PyQt5.QtWidgets import QApplication

from themes import Theme

from editor.basic_editor import BasicEditor
from widgets.keyboard_widget import KeyboardWidget
from util import tr
from vial_device import VialKeyboard
from keycodes.keycodes import Keycode
from tabbed_keycodes import TabbedKeycodes, keycode_filter_masked
from vi_al_addons.my2k.protocol import DksKey

def dks_display(widget, dks):
    if dks.is_valid():
        widget.setText("\u21DF\u21DE")
        widget.setToolTip(tr("DKS", "DKS configured"))
        widget.setColor(QApplication.palette().color(QPalette.Link))
    else:
        widget.setText("")
        widget.setToolTip(tr("DKS", "DKS not configured"))
        widget.setColor(None)

class DksButton(QPushButton):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.scale = 3
        self.label = None
        self.word_wrap = False
        self.text = ""
        self.index = 0
        self.masked = False
        self.masked_text = ""
        self.mask_selected = False

    def is_masked(self):
        return self.masked
    
    def set_masked(self, masked):
        self.masked = masked

    def is_mask_selected(self):
        return self.mask_selected
    
    def set_mask_selected(self, selected):
        self.mask_selected = selected

    def set_index(self, index):
        self.index = index
    
    def get_index(self):
        return self.index

    def get_text(self):
        return self.text

    def set_text(self, text):
        self.text = text

    def get_masked_text(self):
        return self.masked_text

    def set_masked_text(self, text):
        self.masked_text = text

    def setRelSize(self, ratio):
        self.scale = ratio
        self.updateGeometry()

    def sizeHint(self):
        size = int(round(self.fontMetrics().height() * self.scale))
        return QSize(size, size)

    def mousePressEvent(self, ev):
        if not self.isEnabled():
            return
        
        if self.is_masked():
            rect = self.rect()
            masked_rect = self.get_split_rect(True)
            if masked_rect.contains(ev.pos()):
                self.mask_selected = True
            else:
                self.mask_selected = False

        self.toggle()
        self.clicked.emit()

    def get_split_rect(self, masked):
        rect = self.rect()
        if masked:
            return QRect(3, int(rect.height()*2/5)+3, rect.width()-6, int(rect.height()*3/5)-6)
        else:
            return QRect(3, 3, rect.width()-6, int(rect.height()*2/5)-6)


    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.setRenderHint(QPainter.Antialiasing)

        background_brush = QBrush()
        background_brush.setColor(QApplication.palette().color(QPalette.Button))
        background_brush.setStyle(Qt.SolidPattern)

        mask_brush = QBrush()
        mask_brush.setColor(QApplication.palette().color(QPalette.Button).lighter(Theme.mask_light_factor()))
        mask_brush.setStyle(Qt.SolidPattern)

        active_pen = qp.pen()
        active_pen.setColor(QApplication.palette().color(QPalette.Highlight))
        active_pen.setWidthF(2)

        masked_pen = qp.pen()
        masked_pen.setColor(QApplication.palette().color(QPalette.Highlight).darker(120))

        regular_pen = qp.pen()
        regular_pen.setColor(QApplication.palette().color(QPalette.Button))

        # for text 
        text_pen = qp.pen()
        text_pen.setColor(QApplication.palette().color(QPalette.ButtonText))

        mask_font = qp.font()
        mask_font.setPointSize(round(mask_font.pointSize() * 0.8))

        rect = self.rect()
        if self.isChecked():
            qp.setPen(active_pen)
            qp.setBrush(background_brush)
            qp.drawRect(rect)
        else:
            qp.setPen(regular_pen)
            qp.setBrush(background_brush)
            qp.drawRect(rect)

        if self.is_masked():
            masked_rect = self.get_split_rect(True)
            if self.mask_selected:
                qp.setPen(masked_pen)
            else:
                qp.setPen(regular_pen)

            qp.setBrush(mask_brush)
            qp.drawRect(masked_rect)
        
        if self.is_masked():
            qp.setPen(text_pen)
            qp.setFont(mask_font)
            outer_rect = self.get_split_rect(False)
            qp.drawText(outer_rect, Qt.AlignCenter, self.text)
            inner_rect = self.get_split_rect(True)
            qp.drawText(inner_rect, Qt.AlignCenter, self.masked_text)
        else:
            qp.setPen(text_pen)
            qp.drawText(rect, Qt.AlignCenter, self.text)

        qp.end()

class DksCheckBox(QCheckBox):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.index = 0

    def set_index(self, index):
        self.index = index
    
    def get_index(self):
        return self.index

DKS_TRIGGER_LABELS = [tr("DKS", "Event point 1:"), tr("DKS", "Event point 2:"),
                tr("DKS", "Event point 3:"), tr("DKS", "Event point 4:")]

DKS_KEY_EVENT_LABELS = [tr("DKS", "\u21A7"), tr("DKS", "\u21A5")]

class Dks(BasicEditor):

    def __init__(self, layout_editor, appctx):
        super().__init__()

        self.layout_editor = layout_editor
        self.active_dks_btn = None
        self.active_dks = None
        self.dks_btns = []
        self.dks_ckbs = []

        self.dks_lbl = QLabel()
        self.dks_img = QImage(appctx.get_resource("dks.png"))
        # The original artwork embeds bilingual captions. Render English at the
        # same positions, preserving transparency, arrows and button alignment.
        painter = QPainter(self.dks_img)
        caption_font = painter.font()
        caption_font.setPixelSize(68)
        caption_font.setBold(True)
        painter.setFont(caption_font)
        for rect, caption, background in [
                (QRect(700, 1015, 540, 155), tr("DKS", "Travel"), Qt.transparent),
                (QRect(700, 1500, 550, 75), tr("DKS", "Bottom out"), Qt.transparent),
                (QRect(50, 860, 510, 210), tr("DKS", "Event point 1"), QColor(255, 255, 255, 51)),
                (QRect(50, 1175, 510, 210), tr("DKS", "Event point 2"), QColor(255, 255, 255, 51)),
                (QRect(1410, 1175, 515, 210), tr("DKS", "Event point 3"), QColor(255, 255, 255, 51)),
                (QRect(1410, 860, 515, 210), tr("DKS", "Event point 4"), QColor(255, 255, 255, 51))]:
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(rect, background)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(Qt.white)
            painter.drawText(rect, Qt.AlignCenter, caption)
        painter.end()
        self.dks_lbl.setAccessibleDescription(tr("DKS", "Switch travel and bottom-out diagram"))
        pixmap = QPixmap.fromImage(self.dks_img)
        pixmap = pixmap.scaled(500, 500, aspectRatioMode=Qt.KeepAspectRatio)
        self.dks_lbl.setPixmap(pixmap)

        g_layout = QGridLayout()
        index = 0
        for x in range(4):
            btn = DksButton()
            btn.set_index(index)
            btn.setCheckable(True)
            btn.clicked.connect(self.on_dks_btn_clicked)
            index = index + 1
            self.dks_btns.append(btn)
            g_layout.addWidget(btn, 0, 2+x)
            g_layout.setAlignment(btn, Qt.AlignCenter)

        index = 0

        for line in range(4):
            lbl = QLabel(DKS_TRIGGER_LABELS[line])
            g_layout.addWidget(lbl, 2*line + 1, 0)

            for sub in range(2):
                lbl = DKS_KEY_EVENT_LABELS[sub]
                for x in range(4):
                    ckb = DksCheckBox(lbl)
                    ckb.set_index(index)
                    ckb.setTristate(False)
                    ckb.stateChanged.connect(self.on_dks_checked)
                    index = index + 1
                    self.dks_ckbs.append(ckb)
                    g_layout.addWidget(ckb, 2*line+sub+1, 2+x)
                    g_layout.setAlignment(ckb, Qt.AlignCenter)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.on_apply_clicked)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.on_reset_clicked)

        h_layout = QHBoxLayout()
        h_layout.addWidget(self.apply_btn)
        h_layout.setAlignment(self.apply_btn, Qt.AlignRight)
        h_layout.addWidget(self.reset_btn)
        h_layout.setAlignment(self.reset_btn, Qt.AlignRight)

        v_layout = QVBoxLayout()
        v_layout.addStretch(1)
        v_layout.addLayout(g_layout)
        v_layout.addLayout(h_layout)
        v_layout.setAlignment(h_layout, Qt.AlignRight)
        v_layout.addStretch(1)

        h_layout = QHBoxLayout()
        h_layout.addWidget(self.dks_lbl)
        h_layout.addLayout(v_layout)

        dks_layout = QHBoxLayout()
        dks_layout.addStretch(1)
        dks_layout.addLayout(h_layout)

        self.keyboardWidget = KeyboardWidget(layout_editor)
        self.keyboardWidget.set_enabled(True)
        self.keyboardWidget.clicked.connect(self.on_key_clicked)
        k_layout = QVBoxLayout()
        k_layout.addStretch(1)
        k_layout.addWidget(self.keyboardWidget)
        k_layout.setAlignment(self.keyboardWidget, Qt.AlignVCenter)
        k_layout.addStretch(1)

        dks_layout.addStretch(1)
        dks_layout.addLayout(k_layout)
        dks_layout.addStretch(1)

        self.tabbed_keycodes = TabbedKeycodes()
        self.tabbed_keycodes.keycode_changed.connect(self.on_keycode_changed)
        #self.tabbed_keycodes.anykey.connect(self.on_any_keycode)

        self.addLayout(dks_layout)
        self.addWidget(self.tabbed_keycodes)

        self.keyboard = None
        self.device = None

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.keyboardWidget.set_keys(self.keyboard.keys, self.keyboard.encoders)
            self.keyboardWidget.setEnabled(self.valid())
            self.reset_keyboard_widget()

    def valid(self):
        # Check if vial protocol is v3 or later
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and (self.device.keyboard.keyboard_type.startswith("ms") or self.device.keyboard.keyboard_type == "ec")) and \
               ((self.device.keyboard.cols // 8 + 1) * self.device.keyboard.rows <= 28)

    def reset_keyboard_widget(self):
        if self.valid():
            self.keyboardWidget.update_layout()

            for widget in self.keyboardWidget.widgets:
                dks_display(widget, self.keyboard.amk_dks[(widget.desc.row,widget.desc.col)])
                widget.setOn(False)

            self.keyboardWidget.update()
            self.keyboardWidget.updateGeometry()

    def activate(self):
        if self.valid():
            self.reset_keyboard_widget()
            self.refresh_dks(self.active_dks)

    def deactivate(self):
        pass

    def block_check_box(self, block):
        for b in self.dks_ckbs:
            b.blockSignals(block)

    def save_dks(self, dks):
        if self.keyboardWidget.active_key is None:
            return

        row = self.keyboardWidget.active_key.desc.row
        col = self.keyboardWidget.active_key.desc.col
        self.keyboard.apply_dks(row, col)

    def refresh_dks(self, dks):
        if dks is None:
            return

        for i in range(4):
            if dks is None:
                self.dks_btns[i].setEnabled(False)
            else:
                self.dks_btns[i].setEnabled(True)

                code = dks.get_key(i)
                if Keycode.is_mask(code):
                    outer = Keycode.find_outer_keycode(code)
                    self.dks_btns[i].set_text(outer.label.replace("(kc)","").strip())
                    inner = Keycode.find_inner_keycode(code)
                    if inner is not None:
                        self.dks_btns[i].set_masked_text(inner.label)
                    self.dks_btns[i].set_masked(True)
                else:
                    kc = Keycode.find_by_qmk_id(dks.get_key(i))
                    self.dks_btns[i].set_text(kc.label)
                    self.dks_btns[i].set_masked(False)
                self.dks_btns[i].repaint()

        self.block_check_box(True)
        for index in range(32):
            if dks is None:
                self.dks_ckbs[index].setEnabled(False)
            else:
                self.dks_ckbs[index].setEnabled(True)

                ckb = self.dks_ckbs[index]
                event = index % 4
                key = index // 8
                down = True if (index % 8) < 4 else False

                if dks.is_event_on(event, key, down):
                    ckb.setChecked(True)
                else:
                    ckb.setChecked(False)
        self.block_check_box(False)

        if dks is not None:
            if dks.is_dirty():
                self.apply_btn.setEnabled(True)
            else:
                self.apply_btn.setEnabled(False)

    def reset_active_dks(self):
        if self.keyboardWidget.active_key is None:
            return
        
        widget = self.keyboardWidget.active_key
        dks_display(widget, self.keyboard.amk_dks[(widget.desc.row,widget.desc.col)])
        self.keyboardWidget.update()

    def save_or_discard(self, dks):
        button = QMessageBox.warning(None, tr("DKS", "DKS button"),
                                    tr("DKS", "Save changes to this DKS key?"),
                                    buttons=QMessageBox.Save | QMessageBox.Discard,
                                    defaultButton=QMessageBox.Save)
        if button == QMessageBox.Save:
            self.save_dks(dks)
            self.active_dks.set_dirty(False)
            self.apply_btn.setEnabled(False)
            self.reset_keyboard_widget()
            

    def on_key_clicked(self):
        """ Called when a key on the keyboard widget is clicked """
        if self.keyboardWidget.active_key is None:
            return

        row = self.keyboardWidget.active_key.desc.row
        col = self.keyboardWidget.active_key.desc.col
        dks = self.active_dks
        if dks is not None and dks.is_dirty():
            self.save_or_discard(dks)

        self.active_dks = self.keyboard.amk_dks[(row, col)]
        self.refresh_dks(self.active_dks)

    def on_dks_btn_clicked(self):
        if self.active_dks_btn is not None:
            if self.active_dks_btn.isChecked():
                self.active_dks_btn.toggle()
                self.active_dks_btn.set_mask_selected(False)

        self.active_dks_btn = self.sender()
        if not self.active_dks_btn.isChecked():
            self.active_dks_btn.toggle()
        if self.active_dks_btn.is_mask_selected():
            self.tabbed_keycodes.set_keycode_filter(keycode_filter_masked)
        else:
            self.tabbed_keycodes.set_keycode_filter(None)
    
    def on_keycode_changed(self, code):
        if self.active_dks_btn is not None:
            if self.active_dks_btn.is_mask_selected():
                if Keycode.is_mask(code):
                    QMessageBox.warning(None, tr("DKS", "Keycode selection"),
                                tr("DKS", "DKS supports only basic keycodes."),
                                buttons=QMessageBox.Ok)
                    return
                index = self.active_dks_btn.get_index()
                if self.active_dks is not None:
                    self.active_dks.update_inner_key(index, code)
                    if self.active_dks.is_dirty():
                        self.apply_btn.setEnabled(True)
                    self.active_dks_btn.set_masked_text(Keycode.label(code))
            else:
                if Keycode.is_mask(code):
                    outer = Keycode.find_outer_keycode(code)
                    self.active_dks_btn.set_text(outer.label.replace("(kc)","").strip())
                    inner = Keycode.find_inner_keycode(code)
                    if inner is not None:
                        self.active_dks_btn.set_masked_text(inner.label)
                    self.active_dks_btn.set_masked(True)
                else:
                    kc = Keycode.find_by_qmk_id(code)
                    self.active_dks_btn.set_text(kc.label)
                    self.active_dks_btn.set_masked(False)

                index = self.active_dks_btn.get_index()
                if self.active_dks is not None:
                    self.active_dks.add_key(index, code)
                    if self.active_dks.is_dirty():
                        self.apply_btn.setEnabled(True)
            self.active_dks_btn.repaint()

    def on_apply_clicked(self):
        if self.active_dks is None:
            return

        self.save_dks(self.active_dks)

        self.active_dks.set_dirty(False)
        self.apply_btn.setEnabled(False)
        self.reset_active_dks()

    def on_reset_clicked(self):
        if self.active_dks is not None:
            self.active_dks.clear()
            self.refresh_dks(DksKey())
            self.apply_btn.setEnabled(True)

    def on_dks_checked(self):
        ckb = self.sender()
        index = ckb.get_index()
        if self.active_dks is None:
            return

        event = index % 4
        key = index // 8

        down = True if (index % 8) < 4 else False
        if ckb.isChecked():
            self.active_dks.add_event(event, key, down)
        else:
            self.active_dks.del_event(event, key, down)
        
        if self.active_dks.is_dirty():
            self.apply_btn.setEnabled(True)
