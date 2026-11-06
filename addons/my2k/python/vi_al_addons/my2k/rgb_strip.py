import time

from ui_text import device_text
# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QCheckBox, QColorDialog, QListWidget, QSizePolicy, QGroupBox, QWidget
from PyQt5.QtCore import Qt, QTimer, QSignalBlocker, QSize, QRectF

from PyQt5.QtGui import QPainter, QColor, QPainterPath, QTransform, QBrush, QPolygonF, QPalette, QFont
from PyQt5.QtWidgets import QApplication

from themes import Theme
from vi_al_addons.my2k.rgb_strip_preview import compact_strip_layout
from vi_al_addons.my2k.rgb_controls import enlarge_rgb_control

from editor.basic_editor import BasicEditor
from vi_al_addons.my2k.widget import ClickableWidget, AmkWidget
from util import tr
from vial_device import VialKeyboard
from vi_al_addons.my2k.protocol import RGB_PARAM_COLOR, RGB_PARAM_SPEED, RGB_PARAM_SYNC, RGB_PARAM_BRIGHT, RGB_PARAM_USE_CUSTOM_COLOR, RGB_TYPE_STRIP, RgbColor

def rgb_display(widget, is_custom, color, led = None, strip=-1, index=-1):
    mask_text =""
    widget.setMaskColor(None)

    if is_custom:
        if led is not None and led.get_on():
            dynamic = "\u2b12" if led.get_dynamic() else " "
            blink = "\u2b16" if led.get_blink() else " "
            breath = "\u2b14" if led.get_breath() else " "
            speed = "\u2942{}".format(led.get_speed())
            mask_text = "{}{}{}{}".format(dynamic, blink, breath, speed)

    if False and strip != -1 and index != -1:
        mask_text = "{}:{}".format(strip, index)

    led_color = QColor.fromRgbF(color.get_red()/255.0, color.get_green()/255.0, color.get_blue()/255.0)
    widget.setMaskColor(led_color)
    widget.setText(mask_text)

class RgbStripWidget(AmkWidget):
    def __init__(self, layout_editor, editor):
        super().__init__(layout_editor)
        self.editor = editor 
        self._my2k_layout = False
        self._natural_size = (900, 340)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def set_strip_layout(self, layout, strips):
        self._my2k_layout = [s.get('count') for s in strips] == [19,19,8,1,8,4,2]
        self.set_scale(1)
        self.set_keys(compact_strip_layout(layout, strips), [])
        if self._my2k_layout:
            font = QFont(self.font())
            font.setPointSize(9)
            self.setFont(font)
        else:
            self.setFont(QApplication.font())
        self.update_layout()
        self._natural_size = (self.width, self.height)
        self.fit_preview(QWidget.width(self))
        for key in self.widgets:
            strip = strips[key.desc.row]
            key.setToolTip('{} · LED {}/{}'.format(device_text(strip['name']), key.desc.col+1, strip['count']))

    def fit_preview(self, available_width):
        if not self.widgets:
            return
        pad = 2*self.padding
        self.set_scale(max(.05, (available_width-pad)/max(1, self._natural_size[0]-pad)))
        self.update_layout()

    def heightForWidth(self, width):
        pad = 2*self.padding
        return round((self._natural_size[1]-pad)*max(.05, (width-pad)/max(1, self._natural_size[0]-pad))+pad)

    def minimumSizeHint(self):
        return QSize(360, self.heightForWidth(360))

    def sizeHint(self):
        return QSize(920, self.heightForWidth(920))

    def resizeEvent(self, event):
        self.fit_preview(event.size().width())

    def paintEvent(self, event):
        super().paintEvent(event)
        qp = QPainter()
        qp.begin(self)
        qp.setRenderHint(QPainter.Antialiasing)

        for idx, key in enumerate(self.widgets):
            #led = self.editor.keyboard.get_rgb_matrix_led_by_index(key.desc.col)
            #index = self.editor.get_led_index(key.desc.row, key.desc.col)
            #led = self.editor.keyboard.amk_rgb_strip["leds"][index]

            qp.save()

            qp.scale(self.scale, self.scale)
            qp.translate(key.shift_x, key.shift_y)
            qp.translate(key.rotation_x, key.rotation_y)
            qp.rotate(key.rotation_angle)
            qp.translate(-key.rotation_x, -key.rotation_y)

            qp.setPen(Qt.NoPen)
            color_brush = QBrush()
            color_brush.setColor(key.mask_color if key.mask_color else QApplication.palette().color(QPalette.Button).lighter(120))
            color_brush.setStyle(Qt.SolidPattern)
            qp.setBrush(color_brush)
            # Same colored square for every region. Selection is an outline,
            # not a different filled shape for the Top Left group.
            qp.drawRoundedRect(key.rect, key.corner, key.corner)

            if self.editor.strip == key.desc.row:
                qp.setBrush(Qt.NoBrush)
                pen = qp.pen()
                pen.setColor(QApplication.palette().color(QPalette.Highlight))
                pen.setWidthF(2)
                pen.setStyle(Qt.SolidLine)
                qp.setPen(pen)
                qp.drawPath(key.background_draw_path)

            qp.restore()

        qp.end()

class RgbStrip(BasicEditor):
    def __init__(self, layout_editor):
        super().__init__()

        self.layout_editor = layout_editor
        self.keyboard = None
        self.device = None
        self.strip = -1
        self.mode = -1
        self._preview_offset = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.on_rgb_strip_poller)

        self.keyboardWidget = RgbStripWidget(layout_editor, self)
        self.keyboardWidget.set_enabled(True)
        self.keyboardWidget.clicked.connect(self.on_key_clicked)

        self.setSpacing(12)
        self.preview_group = QGroupBox(tr('RGB Strip', 'Lighting preview'))
        preview_layout = QVBoxLayout(self.preview_group)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.addWidget(self.keyboardWidget)
        self.addWidget(self.preview_group)

        self.configuration_group = QGroupBox(tr('RGB Strip', 'Configuration'))
        config_layout = QHBoxLayout(self.configuration_group)
        config_layout.setSpacing(20)
        vv = QVBoxLayout()
        vv.addWidget(QLabel(tr("RGB Strip", "Strips")))
        self.strip_lst = QListWidget()
        self.strip_lst.setMinimumHeight(165)
        self.strip_lst.setMaximumHeight(210)
        self.strip_lst.itemSelectionChanged.connect(self.on_strip_changed)
        vv.addWidget(self.strip_lst)
        config_layout.addLayout(vv, 1)
        vv = QVBoxLayout()
        vv.addWidget(QLabel(tr("RGB Strip", "Effects")))
        self.mode_lst = QListWidget()
        self.mode_lst.setMinimumHeight(165)
        self.mode_lst.setMaximumHeight(210)
        self.mode_lst.itemSelectionChanged.connect(self.on_mode_changed)
        vv.addWidget(self.mode_lst)
        config_layout.addLayout(vv, 1)
        layout = QVBoxLayout()
        layout.setSpacing(12)
        self.color_btn = QPushButton(tr("RGB Strip", "Color…"))
        self.color_btn.clicked.connect(self.on_color_btn_clicked)
        layout.addWidget(self.color_btn)
        self.on_cbx = QCheckBox(tr("RGB Strip", "Enabled"))
        self.on_cbx.stateChanged.connect(self.on_state_check)
        self.on_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        self.dynamic_cbx = QCheckBox(tr("RGB Strip", "Dynamic"))
        self.dynamic_cbx.stateChanged.connect(self.on_dynamic_check)
        self.dynamic_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        self.blink_cbx = QCheckBox(tr("RGB Strip", "Blink"))
        self.blink_cbx.stateChanged.connect(self.on_blink_check)
        self.blink_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        self.breath_cbx = QCheckBox(tr("RGB Strip", "Breathing"))
        self.breath_cbx.stateChanged.connect(self.on_breath_check)
        self.breath_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        lyt = QHBoxLayout()
        self.speed_lbl = QLabel(tr("RGB Strip", "Speed"))
        lyt.addWidget(self.speed_lbl)
        self.speed_sld = QSlider(Qt.Horizontal)
        self.speed_sld.setMaximumWidth(300)
        self.speed_sld.setMinimumWidth(200)
        self.speed_sld.setRange(0, 15)
        self.speed_sld.setSingleStep(1)
        self.speed_sld.setValue(8)
        self.speed_sld.setTickPosition(QSlider.TicksAbove)
        self.speed_sld.setTracking(False)
        self.speed_sld.valueChanged.connect(self.on_speed_sld) 
        enlarge_rgb_control(self.speed_lbl, self.speed_sld)
        lyt.addWidget(self.speed_sld)
        layout.addLayout(lyt)
        lyt = QHBoxLayout()
        self.bright_lbl = QLabel(tr("RGB Strip", "Brightness"))
        lyt.addWidget(self.bright_lbl)
        self.bright_sld = QSlider(Qt.Horizontal)
        self.bright_sld.setMaximumWidth(300)
        self.bright_sld.setMinimumWidth(200)
        self.bright_sld.setRange(0, 255)
        self.bright_sld.setSingleStep(1)
        self.bright_sld.setValue(255)
        self.bright_sld.setTickPosition(QSlider.TicksAbove)
        self.bright_sld.setTracking(False)
        self.bright_sld.valueChanged.connect(self.on_bright_sld) 
        enlarge_rgb_control(self.bright_lbl, self.bright_sld)
        lyt.addWidget(self.bright_sld)
        layout.addLayout(lyt)
        self.sync_cbx = QCheckBox(tr("RGB Strip", "Synchronize"))
        self.sync_cbx.stateChanged.connect(self.on_sync_check)
        self.sync_cbx.hide()  # Preserve cached protocol state, omit unused control.
        self.use_custom_cbx = QCheckBox(tr("RGB Strip", "Custom color"))
        self.use_custom_cbx.stateChanged.connect(self.on_use_custom_check)
        self.use_custom_cbx.hide()
        layout.addStretch(1)
        config_layout.addLayout(layout, 2)
        self.addWidget(self.configuration_group)
        self.addStretch(1)

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            # A newly opened keyboard may have a different strip definition.
            if self.keyboard is not device.keyboard:
                self.strip = -1
                self._preview_offset = 0
            self.keyboard = device.keyboard
            self.keyboardWidget.set_strip_layout(self.keyboard.amk_rgb_strip["layout"], self.keyboard.amk_rgb_strip["strips"])
            self.keyboardWidget.setEnabled(True)
            self.reset_keyboard_widget()
        else:
            self.timer.stop()
            self.keyboard = None
            self.strip = self.mode = -1
            self._preview_offset = 0
            with QSignalBlocker(self.strip_lst), QSignalBlocker(self.mode_lst):
                self.strip_lst.clear()
                self.mode_lst.clear()
            self.keyboardWidget.setEnabled(False)

    def valid(self):
        return isinstance(self.device, VialKeyboard) and bool(
            self.device.keyboard and self.device.keyboard.amk_rgb_strip.get("strips"))

    def reset_mode_widgets(self):
        if self.is_custom_mode(self.strip):
            self.on_cbx.setEnabled(True)
            self.dynamic_cbx.setEnabled(True)
            self.blink_cbx.setEnabled(True)
            self.breath_cbx.setEnabled(True)
        else:
            self.on_cbx.setEnabled(False)
            self.dynamic_cbx.setEnabled(False)
            self.blink_cbx.setEnabled(False)
            self.breath_cbx.setEnabled(False)
        
    def reset_sync_widgets(self):
        self.sync_cbx.setEnabled(False)
        if self.strip != -1:
            strip = self.keyboard.amk_rgb_strip["strips"][self.strip]
            if self.keyboard.rgb_strip_supports_sync(self.strip) and "sync" in strip:
                self.sync_cbx.setEnabled(True)
                with QSignalBlocker(self.sync_cbx):
                    self.sync_cbx.setChecked(True if strip["sync"] < len(self.keyboard.amk_rgb_strip["strips"]) else False)

    def reset_use_custom_widgets(self):
        self.use_custom_cbx.setEnabled(True if self.keyboard.amk_feature["use_custom_color"] else False)
        if self.strip != -1:
            strip = self.keyboard.amk_rgb_strip["strips"][self.strip]
            self.use_custom_cbx.setChecked(True if strip["use_custom_color"] else False)

    def reset_bright_widgets(self):
        if self.keyboard.amk_feature["bright"]:
            self.bright_lbl.show()
            self.bright_sld.show()
            self.bright_sld.setEnabled(True)
            if self.strip != -1:
                strip = self.keyboard.amk_rgb_strip["strips"][self.strip]
                self.bright_sld.setValue(strip["bright"])
        else:
            self.bright_sld.setEnabled(False)
            self.bright_sld.hide()
            self.bright_lbl.hide()

    def reset_keyboard_widget(self):
        if self.valid():
            # Populate both lists before displaying the selected strip. Qt list
            # signals during clear/repopulation must never act as user edits.
            with QSignalBlocker(self.strip_lst), QSignalBlocker(self.mode_lst):
                self.strip_lst.clear()
                for strip in self.keyboard.amk_rgb_strip["strips"]:
                    self.strip_lst.addItem(device_text(strip["name"]))
                self.mode_lst.clear()
                for effect in self.keyboard.amk_rgb_strip["effects"]:
                    self.mode_lst.addItem(device_text(effect))
                if not 0 <= self.strip < self.strip_lst.count():
                    self.strip = 0
                self.strip_lst.setCurrentRow(self.strip)
            self.on_strip_changed()

            self.keyboardWidget.update_layout()
            for widget in self.keyboardWidget.widgets:
                widget.masked = True
                widget.setOn(False)

            self.keyboardWidget.update()
            self.keyboardWidget.updateGeometry()

    def activate(self):
        self._preview_offset = 0
        if self.valid():
            self.reset_keyboard_widget()
            self.on_rgb_strip_poller()
            self.timer.start(50)
        else:
            self.timer.stop()

    def deactivate(self):
        self.timer.stop()
    
    def on_empty_space_clicked(self):
        self.keyboardWidget.clear_active_keys()
        self.keyboardWidget.update()

    def on_key_clicked(self):
        if not self.keyboardWidget.active_keys:
            return

        key = list(self.keyboardWidget.active_keys.values())[0]
        if not self.is_custom_mode(key.desc.row):
            return

        color, led = self.get_led(key.desc.row, key.desc.col)
        if led is None:
            return
        
        self.on_cbx.blockSignals(True)
        self.dynamic_cbx.blockSignals(True)
        self.blink_cbx.blockSignals(True)
        self.breath_cbx.blockSignals(True)
        self.speed_sld.blockSignals(True)

        self.on_cbx.setCheckState(Qt.Checked if led.get_on() else Qt.Unchecked)
        self.dynamic_cbx.setCheckState(Qt.Checked if led.get_dynamic() else Qt.Unchecked)
        self.blink_cbx.setCheckState(Qt.Checked if led.get_blink() else Qt.Unchecked)
        self.breath_cbx.setCheckState(Qt.Checked if led.get_breath() else Qt.Unchecked)
        self.speed_sld.setValue(led.get_speed())
        
        self.speed_sld.blockSignals(False)
        self.breath_cbx.blockSignals(False)
        self.blink_cbx.blockSignals(False)
        self.dynamic_cbx.blockSignals(False)
        self.on_cbx.blockSignals(False)

    def is_custom_mode(self, strip):
        if strip == -1 or strip >= len(self.keyboard.amk_rgb_strip["strips"]):
            return False
        
        #print("strip", strip)
        #print(self.keyboard.amk_rgb_strip["strips"][strip])
        return self.keyboard.amk_rgb_strip["strips"][strip]["mode"] == self.keyboard.amk_rgb_strip["effects"].index("Custom") 

    def on_color_btn_clicked(self):
        self.dlg_color = QColorDialog()
        self.dlg_color.setModal(True)
        self.dlg_color.finished.connect(self.on_color_selected)
        self.dlg_color.show()

    def on_color_selected(self):
        if self.strip == -1 or self.strip >= len(self.keyboard.amk_rgb_strip["strips"]):
            return

        color = self.dlg_color.selectedColor()
        if not color.isValid():
            return

        if self.is_custom_mode(self.strip):
            h, s, v, a = color.getHsvF()
            if h < 0:
                h = 0

            hue = int(255*h)
            sat = int(255*s)
            val = int(255*v)

            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.strip:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_strip["leds"][index]
                    led.set_hue(hue)
                    led.set_sat(sat)
                    led.set_val(val)
                    self.keyboard.apply_rgb_strip_led(index, led)
        else:
            r, g, b, a = color.getRgbF()
            red = int(255*r)
            green = int(255*g)
            blue = int(255*b)
            self.keyboard.apply_rgb_param(RGB_TYPE_STRIP, RGB_PARAM_COLOR, RgbColor(red, green, blue), self.strip)

        self.keyboardWidget.update()

    def on_state_check(self):
        if self.strip == -1:
            return

        if self.is_custom_mode(self.strip):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.strip:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_strip["leds"][index]
                    on = not led.get_on()
                    led.set_on(on)
                    self.keyboard.apply_rgb_strip_led(index, led)

        self.keyboardWidget.update()

    def on_dynamic_check(self):
        if self.strip == -1:
            return

        if self.is_custom_mode(self.strip):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.strip:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_strip["leds"][index]
                    dynamic = not led.get_dynamic()
                    led.set_dynamic(dynamic)
                    self.keyboard.apply_rgb_strip_led(index, led)

        self.keyboardWidget.update()

    def on_blink_check(self):
        if self.strip == -1:
            return

        if self.is_custom_mode(self.strip):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.strip:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_strip["leds"][index]
                    blink = not led.get_blink()
                    led.set_blink(blink)
                    self.keyboard.apply_rgb_strip_led(index, led)

        self.keyboardWidget.update()

    def on_breath_check(self):
        if self.strip == -1:
            return

        if self.is_custom_mode(self.strip):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.strip:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_strip["leds"][index]
                    breath = not led.get_breath()
                    led.set_breath(breath)
                    self.keyboard.apply_rgb_strip_led(index, led)

        self.keyboardWidget.update()

    def on_sync_check(self):
        if self.strip == -1:
            return

        sync = self.keyboard.amk_rgb_strip["strips"][self.strip]["master"] if self.sync_cbx.isChecked() else 0xFF
        self.keyboard.apply_rgb_param(RGB_TYPE_STRIP, RGB_PARAM_SYNC, sync, self.strip)

        self.keyboardWidget.update()

    def on_use_custom_check(self):
        if self.strip == -1:
            return

        use_custom = 1 if self.use_custom_cbx.isChecked() else 0
        self.keyboard.apply_rgb_param(RGB_TYPE_STRIP, RGB_PARAM_USE_CUSTOM_COLOR, use_custom, self.strip)

        self.keyboardWidget.update()

    def on_speed_sld(self):
        if self.strip == -1:
            return

        if self.is_custom_mode(self.strip):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.strip:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_strip["leds"][index]
                    if (led.get_speed() != self.speed_sld.value()):
                        led.set_speed(self.speed_sld.value())
                        self.keyboard.apply_rgb_strip_led(index, led)
        else:
            speed = (self.speed_sld.value() * 255) // self.speed_sld.maximum()
            self.keyboard.apply_rgb_param(RGB_TYPE_STRIP, RGB_PARAM_SPEED, speed, self.strip)

        self.keyboardWidget.update()

    def on_bright_sld(self):
        if self.strip == -1:
            self.strip = 0

        bright = self.bright_sld.value()
        self.keyboard.apply_rgb_param(RGB_TYPE_STRIP, RGB_PARAM_BRIGHT, bright, self.strip)

        self.keyboardWidget.update()

    def get_led_index(self, strip, offset):
        if strip >= len(self.keyboard.amk_rgb_strip["strips"]):
            return None
        
        if offset >= self.keyboard.amk_rgb_strip["strips"][strip]["count"]:
            return None

        index = self.keyboard.amk_rgb_strip["start"] + self.keyboard.amk_rgb_strip["strips"][strip]["start"] + offset
        return index 

    def get_led(self, strip, offset):
        color = RgbColor(0,0,0)
        index = self.get_led_index(strip, offset)
        led = None
        if index is not None:
            sampled = self.keyboard.amk_rgb_data[index]
            # A large sweep may need several ticks after the first connection.
            # Unsampled buffer entries are initialized to integer zero.
            if isinstance(sampled, RgbColor):
                color = sampled
            if self.is_custom_mode(strip):
                led = self.keyboard.amk_rgb_strip["leds"][index]

        return color, led
    
    def on_rgb_strip_poller(self):
        if not self.valid():
            self.timer.stop()
            return
        
        try:
            # All previews share the rendered RGB buffer. Read the declared
            # feature range, independent of the strip selected for editing.
            start = self.keyboard.amk_rgb_strip["start"]
            count = self.keyboard.amk_rgb_strip["count"]
            if not 0 <= self._preview_offset < count:
                self._preview_offset = 0
            packet_size = 8 if self.keyboard.amk_rgb_led["protocol_v2"] else 9
            deadline = time.monotonic() + 0.040
            while self._preview_offset < count:
                size = min(packet_size, count - self._preview_offset)
                self.keyboard.reload_rgb_leds(start + self._preview_offset, size)
                self._preview_offset += size
                if self._preview_offset == count:
                    self._preview_offset = 0
                    break
                # Bound a busy Qt callback to a few reports. Large/slow sweeps
                # resume on the same timer's next tick, without starving later LEDs.
                if time.monotonic() >= deadline:
                    break

        except (RuntimeError, ValueError):
            self.timer.stop()
            return

        for widget in self.keyboardWidget.widgets:
            color, led = self.get_led(widget.desc.row, widget.desc.col)
            rgb_display(widget, self.is_custom_mode(widget.desc.row), color, led, self.strip if self.strip == widget.desc.row else -1, widget.desc.col)

        self.keyboardWidget.update()

    def on_strip_changed(self):
        cur = self.strip_lst.currentRow()
        if not self.valid() or not 0 <= cur < len(self.keyboard.amk_rgb_strip["strips"]):
            return

        self.strip = cur
        self.mode = self.keyboard.amk_rgb_strip["strips"][cur]["mode"]
        # Selecting or refreshing a strip displays cached settings, not edits.
        with QSignalBlocker(self.mode_lst), QSignalBlocker(self.sync_cbx), \
                QSignalBlocker(self.use_custom_cbx), QSignalBlocker(self.bright_sld):
            self.mode_lst.setCurrentRow(self.mode)
            self.reset_mode_widgets()
            self.reset_sync_widgets()
            self.reset_bright_widgets()
            self.reset_use_custom_widgets()

    def on_mode_changed(self):
        cur = self.mode_lst.currentRow()
        if cur == -1:
            return

        if self.strip == -1:
            self.strip = 0

        self.keyboard.apply_rgb_strip_mode(self.strip, cur)
        self.mode = cur
        self.reset_mode_widgets()
