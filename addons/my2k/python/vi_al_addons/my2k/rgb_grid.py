from ui_text import device_text
# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QCheckBox, QColorDialog, QListWidget, QLineEdit, QComboBox, QGroupBox, QSizePolicy, QWidget
from PyQt5.QtCore import Qt, QTimer, QSize, QSignalBlocker

from PyQt5.QtGui import QPainter, QColor, QBrush, QPalette
from PyQt5.QtWidgets import QApplication

from editor.basic_editor import BasicEditor
from vi_al_addons.my2k.widget import ClickableWidget, AmkWidget
from vi_al_addons.my2k.rgb_controls import enlarge_rgb_control
from util import tr
from vial_device import VialKeyboard
from vi_al_addons.my2k.protocol import RGB_PARAM_COLOR, RGB_PARAM_SPEED, RGB_PARAM_BRIGHT, RGB_TYPE_GRID, GRID_TEXT_MAX, RgbColor

GRID_TEXT_MASK = "x" * GRID_TEXT_MAX

def rgb_display(widget, is_custom, color, led = None, grid=-1, index=-1):
    mask_text =""
    widget.setMaskColor(None)

    if is_custom:
        if led is not None and led.get_on():
            dynamic = "\u2b12" if led.get_dynamic() else " "
            blink = "\u2b16" if led.get_blink() else " "
            breath = "\u2b14" if led.get_breath() else " "
            speed = "\u2942{}".format(led.get_speed())
            mask_text = "{}{}{}{}".format(dynamic, blink, breath, speed)

    if False and grid != -1 and index != -1:
        mask_text = "{}:{}".format(grid, index)

    led_color = QColor.fromRgbF(color.get_red()/255.0, color.get_green()/255.0, color.get_blue()/255.0)
    widget.setMaskColor(led_color)
    widget.setText(mask_text)

class RgbGridWidget(AmkWidget):
    def __init__(self, layout_editor, editor):
        super().__init__(layout_editor)
        self.editor = editor 
        self._natural_size = (900, 230)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def set_grid_layout(self, layout):
        self.set_scale(1)
        self.set_keys(layout, [])
        self._natural_size = (self.width, self.height)
        self.fit_preview(QWidget.width(self))

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
            #led = self.editor.keyboard.amk_rgb_grid["leds"][index]

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
            qp.drawRoundedRect(key.mask_rect, key.corner, key.corner)
            if self.editor.grid == key.desc.row:
                qp.drawPath(key.background_draw_path)

            qp.restore()

        qp.end()

class RgbGrid(BasicEditor):
    def __init__(self, layout_editor):
        super().__init__()

        self.layout_editor = layout_editor
        self.keyboard = None
        self.device = None
        self.grid = -1
        self.mode = -1
        self.timer = QTimer()
        self.timer.timeout.connect(self.on_rgb_grid_poller)

        self.keyboardWidget = RgbGridWidget(layout_editor, self)
        self.keyboardWidget.set_enabled(True)
        self.keyboardWidget.clicked.connect(self.on_key_clicked)

        self.setSpacing(12)
        self.preview_group = QGroupBox(tr('RGB Grid', 'Lighting preview'))
        preview_layout = QVBoxLayout(self.preview_group)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.addWidget(self.keyboardWidget)
        self.addWidget(self.preview_group)

        self.configuration_group = QGroupBox(tr('RGB Grid', 'Configuration'))
        config_layout = QHBoxLayout(self.configuration_group)
        config_layout.setSpacing(20)
        vv = QVBoxLayout()
        vv.addWidget(QLabel(tr("RGB Grid", "Grids")))
        self.grid_lst = QListWidget()
        self.grid_lst.setMinimumHeight(165)
        self.grid_lst.setMaximumHeight(210)
        self.grid_lst.itemSelectionChanged.connect(self.on_grid_changed)
        vv.addWidget(self.grid_lst)
        config_layout.addLayout(vv, 1)
        vv = QVBoxLayout()
        vv.addWidget(QLabel(tr("RGB Grid", "Effects")))
        self.mode_lst = QListWidget()
        self.mode_lst.setMinimumHeight(165)
        self.mode_lst.setMaximumHeight(210)
        self.mode_lst.itemSelectionChanged.connect(self.on_mode_changed)
        vv.addWidget(self.mode_lst)
        config_layout.addLayout(vv, 1)
        layout = QVBoxLayout()
        layout.setSpacing(12)
        self.color_btn = QPushButton(tr("RGB Grid", "Color…"))
        self.color_btn.clicked.connect(self.on_color_btn_clicked)
        layout.addWidget(self.color_btn)
        self.on_cbx = QCheckBox(tr("RGB Grid", "Enabled"))
        self.on_cbx.stateChanged.connect(self.on_state_check)
        self.on_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        self.dynamic_cbx = QCheckBox(tr("RGB Grid", "Dynamic"))
        self.dynamic_cbx.stateChanged.connect(self.on_dynamic_check)
        self.dynamic_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        self.blink_cbx = QCheckBox(tr("RGB Grid", "Blink"))
        self.blink_cbx.stateChanged.connect(self.on_blink_check)
        self.blink_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        self.breath_cbx = QCheckBox(tr("RGB Grid", "Breathing"))
        self.breath_cbx.stateChanged.connect(self.on_breath_check)
        self.breath_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        lyt = QHBoxLayout()
        self.speed_lbl = QLabel(tr("RGB Grid", "Speed"))
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
        lyt.addStretch(1)
        lyt.addWidget(self.speed_sld)
        layout.addLayout(lyt)
        lyt = QHBoxLayout()
        self.bright_lbl = QLabel(tr("RGB Grid", "Brightness"))
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
        lyt = QHBoxLayout()
        self.text_cbx = QCheckBox(tr("RGB Grid", "Text"))
        self.text_cbx.stateChanged.connect(self.on_mask_check)
        lyt.addWidget(self.text_cbx)
        self.text_edt = QLineEdit()
        self.text_edt.setInputMask(GRID_TEXT_MASK)
        self.text_edt.setMaxLength(GRID_TEXT_MAX)
        self.text_edt.editingFinished.connect(self.on_mask_text)
        lyt.addStretch(1)
        lyt.addWidget(self.text_edt)
        self.text_rotation_cbb = QComboBox()
        self.text_rotation_cbb.currentIndexChanged.connect(self.on_mask_rotation)
        lyt.addWidget(self.text_rotation_cbb)
        self.text_mode_cbb = QComboBox()
        self.text_mode_cbb.currentIndexChanged.connect(self.on_mask_mode)
        lyt.addWidget(self.text_mode_cbb)
        # Mask/text widgets remain private for unchanged protocol readback.
        for control in (self.text_cbx,self.text_edt,self.text_rotation_cbb,self.text_mode_cbb):
            control.hide()
        self.typing_cbx = QCheckBox(tr("RGB Grid", "Typing effect"))
        self.typing_cbx.stateChanged.connect(self.on_typing_check)
        self.typing_cbx.hide()  # Retain legacy cached flags; omit unused GUI controls.
        layout.addStretch(1)
        config_layout.addLayout(layout, 2)
        self.addWidget(self.configuration_group)
        self.addStretch(1)

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard
            self.keyboardWidget.set_grid_layout(self.keyboard.amk_rgb_grid["layout"])
            self.keyboardWidget.setEnabled(True)
            self.reset_keyboard_widget()
        else:
            self.timer.stop()
            self.keyboard = None
            self.grid = self.mode = -1
            with QSignalBlocker(self.grid_lst), QSignalBlocker(self.mode_lst):
                self.grid_lst.clear()
                self.mode_lst.clear()
            self.keyboardWidget.setEnabled(False)

    def valid(self):
        return isinstance(self.device, VialKeyboard) and \
               (self.device.keyboard and len(self.device.keyboard.amk_rgb_grid) > 0)

    def reset_mode_widgets(self):
        if self.is_custom_mode(self.grid):
            self.on_cbx.setEnabled(True)
            self.dynamic_cbx.setEnabled(True)
            self.blink_cbx.setEnabled(True)
            self.breath_cbx.setEnabled(True)
        else:
            self.on_cbx.setEnabled(False)
            self.dynamic_cbx.setEnabled(False)
            self.blink_cbx.setEnabled(False)
            self.breath_cbx.setEnabled(False)

    def reset_grid_mask(self):
        cur = self.grid_lst.currentRow()
        if cur == -1:
            cur = 0

        self.text_cbx.blockSignals(True)
        self.text_edt.blockSignals(True)
        self.text_rotation_cbb.blockSignals(True)
        self.text_mode_cbb.blockSignals(True)

        self.text_rotation_cbb.clear()
        self.text_mode_cbb.clear()

        if self.keyboard.amk_rgb_grid["grids"][cur]["mask"] > 0:
            self.text_cbx.setEnabled(True)
            self.text_edt.setEnabled(True)
            grid = self.keyboard.amk_rgb_grid["grids"][cur]
            #print("GRID: ", grid)
            self.text_cbx.setChecked(True if grid["mask_enable"] > 0 else False)
            self.text_edt.setText(grid["mask_text"])
            self.text_rotation_cbb.addItems([device_text(label) for label in grid["rotation_list"]])
            self.text_rotation_cbb.setCurrentIndex(grid["mask_rotation"])
            self.text_mode_cbb.addItems([device_text(label) for label in grid["mode_list"]])
            self.text_mode_cbb.setCurrentIndex(grid["mask_mode"])
        else:
            self.text_cbx.setEnabled(False)
            self.text_edt.setEnabled(False)

        self.text_mode_cbb.blockSignals(False)
        self.text_rotation_cbb.blockSignals(False)
        self.text_edt.blockSignals(False)
        self.text_cbx.blockSignals(False)
    
    def reset_typing_widgets(self):
        self.typing_cbx.setEnabled(False)
        if self.grid != -1:
            grid = self.keyboard.amk_rgb_grid["grids"][self.grid]
            if grid["has_typing"] > 0:
                self.typing_cbx.setEnabled(True)
                with QSignalBlocker(self.typing_cbx):
                    self.typing_cbx.setChecked(True if grid["typing_enable"] > 0 else False)

    def reset_bright_widgets(self):
        if self.keyboard.amk_feature["bright"]:
            self.bright_lbl.show()
            self.bright_sld.show()
            self.bright_sld.setEnabled(True)
            if self.grid != -1:
                grid = self.keyboard.amk_rgb_grid["grids"][self.grid]
                self.bright_sld.setValue(grid["bright"])
        else:
            self.bright_sld.setEnabled(False)
            self.bright_sld.hide()
            self.bright_lbl.hide()

    def reset_keyboard_widget(self):
        if self.valid():
            with QSignalBlocker(self.grid_lst), QSignalBlocker(self.mode_lst):
                self.grid_lst.clear()
                for grid in self.keyboard.amk_rgb_grid["grids"]:
                    self.grid_lst.addItem(device_text(grid["name"]))
                self.mode_lst.clear()
                for effect in self.keyboard.amk_rgb_grid["effects"]:
                    self.mode_lst.addItem(device_text(effect))
                if not 0 <= self.grid < self.grid_lst.count():
                    self.grid = 0
                self.grid_lst.setCurrentRow(self.grid)
            self.on_grid_changed()

            self.keyboardWidget.update_layout()
            for widget in self.keyboardWidget.widgets:
                widget.masked = True
                widget.setOn(False)

            self.reset_mode_widgets()
            with QSignalBlocker(self.bright_sld):
                self.reset_bright_widgets()
            self.reset_typing_widgets()
            self.keyboardWidget.update()
            self.keyboardWidget.updateGeometry()

    def activate(self):
        if self.valid():
            try:
                self.keyboard.reload_rgb_leds(self.keyboard.amk_rgb_grid["start"], self.keyboard.amk_rgb_grid["count"])
            except (RuntimeError, ValueError):
                pass

            self.reset_keyboard_widget()
            self.timer.start(50)

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

    def is_custom_mode(self, grid):
        if grid == -1 or grid >= len(self.keyboard.amk_rgb_grid["grids"]):
            return False
        
        return self.keyboard.amk_rgb_grid["grids"][grid]["mode"] == self.keyboard.amk_rgb_grid["effects"].index("Custom") 

    def on_color_btn_clicked(self):
        self.dlg_color = QColorDialog()
        self.dlg_color.setModal(True)
        self.dlg_color.finished.connect(self.on_color_selected)
        self.dlg_color.show()

    def on_color_selected(self):
        if self.grid == -1 or self.grid >= len(self.keyboard.amk_rgb_grid["grids"]):
            return

        color = self.dlg_color.selectedColor()
        if not color.isValid():
            return

        if self.is_custom_mode(self.grid):
            h, s, v, a = color.getHsvF()
            if h < 0:
                h = 0

            hue = int(255*h)
            sat = int(255*s)
            val = int(255*v)

            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.grid:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_grid["leds"][index]
                    led.set_hue(hue)
                    led.set_sat(sat)
                    led.set_val(val)
                    self.keyboard.apply_rgb_grid_led(index, led)
        else:
            r, g, b, a = color.getRgbF()
            red = int(255*r)
            green = int(255*g)
            blue = int(255*b)
            self.keyboard.apply_rgb_param(RGB_TYPE_GRID, RGB_PARAM_COLOR, RgbColor(red, green, blue), self.grid)

        self.keyboardWidget.update()

    def on_state_check(self):
        if self.grid == -1:
            return

        if self.is_custom_mode(self.grid):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.grid:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_grid["leds"][index]
                    on = not led.get_on()
                    led.set_on(on)
                    self.keyboard.apply_rgb_grid_led(index, led)

        self.keyboardWidget.update()

    def on_dynamic_check(self):
        if self.grid == -1:
            return

        if self.is_custom_mode(self.grid):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.grid:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_grid["leds"][index]
                    dynamic = not led.get_dynamic()
                    led.set_dynamic(dynamic)
                    self.keyboard.apply_rgb_grid_led(index, led)

        self.keyboardWidget.update()

    def on_blink_check(self):
        if self.grid == -1:
            return

        if self.is_custom_mode(self.grid):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.grid:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_grid["leds"][index]
                    blink = not led.get_blink()
                    led.set_blink(blink)
                    self.keyboard.apply_rgb_grid_led(index, led)

        self.keyboardWidget.update()

    def on_breath_check(self):
        if self.grid == -1:
            return

        if self.is_custom_mode(self.grid):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.grid:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_grid["leds"][index]
                    breath = not led.get_breath()
                    led.set_breath(breath)
                    self.keyboard.apply_rgb_grid_led(index, led)

        self.keyboardWidget.update()

    def on_speed_sld(self):
        if self.grid == -1:
            return

        if self.is_custom_mode(self.grid):
            for idx, key in self.keyboardWidget.active_keys.items():
                if key.desc.row == self.grid:
                    index = self.get_led_index(key.desc.row, key.desc.col)
                    led = self.keyboard.amk_rgb_grid["leds"][index]
                    if (led.get_speed() != self.speed_sld.value()):
                        led.set_speed(self.speed_sld.value())
                        self.keyboard.apply_rgb_grid_led(index, led)
        else:
            speed = (self.speed_sld.value() * 255) // self.speed_sld.maximum()
            self.keyboard.apply_rgb_param(RGB_TYPE_GRID, RGB_PARAM_SPEED, speed, self.grid)

        self.keyboardWidget.update()

    def on_bright_sld(self):
        if self.grid == -1:
            self.grid = 0

        bright = self.bright_sld.value()
        self.keyboard.apply_rgb_param(RGB_TYPE_GRID, RGB_PARAM_BRIGHT, bright, self.grid)

        self.keyboardWidget.update()

    def get_led_index(self, grid, offset):
        if grid >= len(self.keyboard.amk_rgb_grid["grids"]):
            return None
        
        if offset >= self.keyboard.amk_rgb_grid["grids"][grid]["count"]:
            return None

        index = self.keyboard.amk_rgb_grid["start"] + self.keyboard.amk_rgb_grid["grids"][grid]["start"] + offset
        return index 

    def get_led(self, grid, offset):
        color = RgbColor(0,0,0)
        index = self.get_led_index(grid, offset)
        led = None
        if index is not None:
            color = self.keyboard.amk_rgb_data[index]
            if self.is_custom_mode(grid):
                led = self.keyboard.amk_rgb_grid["leds"][index]

        return color, led
    
    def on_rgb_grid_poller(self):
        if not self.valid():
            self.timer.stop()
            return
        
        try:
            start = self.keyboard.amk_rgb_grid["start"]
            for i in range(len(self.keyboard.amk_rgb_grid["grids"])):
                if i == self.grid:
                    grid = self.keyboard.amk_rgb_grid["grids"][i]
                    self.keyboard.reload_rgb_leds(start+grid["start"], grid["count"])

        except (RuntimeError, ValueError):
            self.timer.stop()
            return

        #try:
        #    self.keyboard.reload_rgb_leds(self.keyboard.amk_rgb_grid["start"], self.keyboard.amk_rgb_grid["count"])
        #except (RuntimeError, ValueError):
        #    self.timer.stop()
        #    return

        for widget in self.keyboardWidget.widgets:
            color, led = self.get_led(widget.desc.row, widget.desc.col)
            rgb_display(widget, self.is_custom_mode(widget.desc.row), color, led, self.grid if self.grid==widget.desc.row else -1, widget.desc.col)

        self.keyboardWidget.update()

    def on_grid_changed(self):
        cur = self.grid_lst.currentRow()
        if cur == -1:
            return

        self.grid = cur
        self.mode = self.keyboard.amk_rgb_grid["grids"][cur]["mode"]
        with QSignalBlocker(self.mode_lst):
            self.mode_lst.setCurrentRow(self.mode)

        self.reset_typing_widgets()
        self.reset_grid_mask()

    def on_mode_changed(self):
        cur = self.mode_lst.currentRow()
        if cur == -1:
            return

        if self.grid == -1:
            self.grid = 0

        self.keyboard.apply_rgb_grid_mode(self.grid, cur)
        self.mode = cur
        self.reset_mode_widgets()

    def grid_mask_update(self):
        if self.grid == -1:
            return

        enabled = 1 if self.text_cbx.isChecked() else 0
        text = self.text_edt.text().strip()

        rotation = self.text_rotation_cbb.currentIndex()
        mode = self.text_mode_cbb.currentIndex()

        typing = 1 if self.typing_cbx.isChecked() else 0

        self.keyboard.apply_grid_mask(self.grid, enabled, text, rotation, mode, typing)
        #print("enabled: {}, text: {}, rotation: {}, mode: {}".format(enabled, text, rotation, mode))

    def on_mask_check(self):
        self.grid_mask_update()

    def on_mask_text(self):
        self.grid_mask_update()

    def on_mask_rotation(self):
        self.grid_mask_update()

    def on_mask_mode(self):
        self.grid_mask_update()

    def on_typing_check(self):
        self.grid_mask_update()
