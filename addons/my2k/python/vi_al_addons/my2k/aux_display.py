# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtWidgets import QSpinBox, QPushButton, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QComboBox, QMessageBox, QCheckBox, QLineEdit, QGroupBox, QSizePolicy
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPainter, QBrush, QPixmap, QFont, QFontDatabase, QFontInfo, QFontMetrics
from PyQt5.QtCore import Qt, QSize, QPoint, QDateTime, QTimer, QSettings, QSignalBlocker

import math

from editor.basic_editor import BasicEditor
from util import tr
from vial_device import VialKeyboard
from vi_al_addons.my2k.oled_typing_preview import typing_bitmap

class AuxWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.text = "Hello\nMatrix"
        self.font_size = 12
        self.font = QFont()
        self.font.setStyleStrategy(QFont.NoAntialias)
        self.font.setPixelSize(self.font_size)
        self.pixmap_width = 70
        self.pixmap_height = 40
        self.update_pixmap()

    def sizeHint(self):
        return QSize(216, 120)

    def minimumSizeHint(self):
        return QSize(144, 80)

    def paintEvent(self, event):
        # Scale the actual device bitmap by whole pixels; never smooth glyphs.
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        scale = max(1, min(self.width() // self.pix.width(),
                           self.height() // self.pix.height()))
        width, height = self.pix.width() * scale, self.pix.height() * scale
        painter.drawPixmap((self.width()-width)//2, (self.height()-height)//2,
                           self.pix.scaled(width, height, Qt.KeepAspectRatio,
                                           Qt.FastTransformation))
        painter.end()

    def set_text(self, text):
        self.text = text
        self.update_pixmap()
        self.repaint()
    
    def set_mode(self, mode):
        self.mode = mode
        self.set_text(self.text)

    def get_mode(self):
        return self.mode

    def set_font(self, family):
        self.font.setFamily(family)
        self.font.setStyleStrategy(QFont.NoAntialias)
        self.font.setPixelSize(self.font_size)
        #print("set font", family)
        self.update_pixmap()
        self.repaint()
    
    def get_font(self):
        return self.font.family()

    def set_font_size(self, size):
        self.font_size = size 
        self.font.setPixelSize(self.font_size)
        self.update_pixmap()
        self.repaint()
    
    def get_font_size(self):
        return self.font_size

    def get_pixmap_width(self):
        return self.pixmap_width

    def get_pixmap_height(self):
        return self.pixmap_height

    def set_pixmap_size(self, width, height):
        self.pixmap_width = width
        self.pixmap_height = height

    def update_pixmap(self):
        self.pix = QPixmap(self.pixmap_width, self.pixmap_height)
        qp = QPainter()
        qp.begin(self.pix)
        brush = QBrush()
        brush.setColor(Qt.black)
        brush.setStyle(Qt.SolidPattern)
        qp.setBrush(brush)
        pen = qp.pen()
        
        qp.setFont(self.font)
        pen.setColor(Qt.white)
        qp.setPen(pen)
        qp.fillRect(0,0,self.pixmap_width,self.pixmap_height,Qt.black)

        lines = self.text.splitlines()
        x = 0
        y_step = self.font_size+1
        y = y_step
        for l in lines:
            qp.drawText(QPoint(x,y), l)
            y = y + y_step
        qp.end()

        self.pix_scaled = self.pix.scaled(self.get_pixmap_width()*2,self.get_pixmap_height()*2,Qt.KeepAspectRatio)
    
    def set_bitmap(self, bitmap):
        if bitmap is None:
            return
        self.pix = QPixmap(72, 40)
        self.pix.fill(Qt.black)
        painter = QPainter(self.pix)
        painter.setPen(Qt.white)
        for y in range(40):
            for x in range(72):
                if bitmap[y // 8 * 72 + x] & (1 << (y % 8)):
                    painter.drawPoint(x, y)
        painter.end()
        self.pix_scaled = self.pix.scaled(144, 80, Qt.KeepAspectRatio)
        self.repaint()

    def get_pixmap_data(self):
        img = self.pix.toImage()
        data = []
        #print(img.height(), img.width())
        for y in range(img.height()):
            for x in range(img.width()):
                data.append(img.pixelColor(x,y))
        return data

import sys
class AuxDsiplay(BasicEditor):
    def __init__(self, layout_editor, appctx):
        super().__init__()
        self.keyboard = None
        self.device = None
        
        self.oled_client = None
        self.clock_settings = QSettings("Vial", "Vial")
        self._clock_keyboard = None
        self._auto_clock_attempted = False
        self.auto_clock_timer = QTimer()
        self.auto_clock_timer.setSingleShot(True)
        self.auto_clock_timer.timeout.connect(self.run_auto_clock_sync)
        self.ready_attempts = 0
        self.ready_timer = QTimer()
        self.ready_timer.timeout.connect(self.reload_oled)
        self.save_timer = QTimer()
        self.save_timer.timeout.connect(self.check_oled_save)
        self.setSpacing(8)
        self.apply_banner = QLabel("Changes on this page are not applied until you click Apply changes.")
        self.apply_banner.setWordWrap(True)
        self.apply_banner.setStyleSheet('QLabel { background: palette(alternate-base); border: 1px solid palette(mid); border-radius: 5px; padding: 8px; }')
        self.addWidget(self.apply_banner)

        self.screen_section = QGroupBox(tr("AuxDisplay", "Screen Saver"))
        self.typing_section = QGroupBox(tr("AuxDisplay", "Typing Mode"))
        left, right = QVBoxLayout(self.screen_section), QVBoxLayout(self.typing_section)
        for layout in (left, right):
            layout.setSpacing(8)
            layout.setContentsMargins(12, 16, 12, 12)
        sections = QHBoxLayout()
        sections.setSpacing(12)
        sections.addWidget(self.screen_section, 1)
        sections.addWidget(self.typing_section, 1)
        self.addLayout(sections)

        self.ad_text = QPlainTextEdit()
        self.typing_label = QPlainTextEdit()
        self.typing_label.setPlaceholderText("Optional corner label")
        for layout, title, field in ((left, "Idle message", self.ad_text),
                                      (right, "Typing corner label", self.typing_label)):
            label = QLabel(tr("AuxDisplay", title))
            label.setBuddy(field)
            layout.addWidget(label)
            field.setFixedHeight(52)
            field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            layout.addWidget(field)
        self.ad_text.setToolTip("Up to 59 ASCII characters, including line breaks; must fit 72 × 40 pixels.")
        self.typing_label.setToolTip("Up to 10 printable ASCII characters on one line. Leave empty for no label.")

        self.ad_preview = AuxWidget()
        self.typing_preview = AuxWidget()
        self.ad_preview.set_pixmap_size(72, 40)
        self.ad_preview.update_pixmap()
        self.ad_fonts = QComboBox()
        self.ad_fonts.addItems(QFontDatabase().families())
        family = QFontInfo(self.ad_preview.font).family()
        self.ad_fonts.setCurrentText(family)
        self.ad_font_size = QSpinBox()
        self.ad_font_size.setRange(8, 38)
        self.ad_font_size.setSuffix(" px")
        self.ad_font_size.setValue(self.ad_preview.font_size)
        self.typing_fonts = QComboBox()
        self.typing_fonts.addItem("Firmware bitmap (6 × 8)")
        self.typing_font_size = QSpinBox()
        self.typing_font_size.setRange(8, 8)
        self.typing_font_size.setValue(8)
        self.typing_font_size.setSuffix(" px")
        for widget in (self.typing_fonts, self.typing_font_size):
            widget.setEnabled(False)
            widget.setToolTip("Release 1 uses a fixed 6 × 8 bitmap font for the corner label. Its font and size cannot be configured.")
        for layout, fonts, size in ((left, self.ad_fonts, self.ad_font_size),
                                    (right, self.typing_fonts, self.typing_font_size)):
            row = QHBoxLayout()
            row.addWidget(QLabel(tr("AuxDisplay", "Font")))
            fonts.setMinimumWidth(110)
            fonts.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            fonts.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            fonts.setMinimumContentsLength(10)
            row.addWidget(fonts, 1)
            row.addWidget(QLabel(tr("AuxDisplay", "Size")))
            size.setFixedWidth(74)
            row.addWidget(size)
            layout.addLayout(row)
        for layout, preview in ((left, self.ad_preview), (right, self.typing_preview)):
            layout.addWidget(QLabel(tr("AuxDisplay", "Display preview · 72 × 40")))
            preview.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            preview.setFixedSize(216, 120)
            layout.addWidget(preview, 0, Qt.AlignHCenter)
        self.screen_note = QLabel("ASCII · up to 59 characters")
        self.typing_note = QLabel("Fixed 6 × 8 · sample ABC → D")
        for layout, note in ((left, self.screen_note), (right, self.typing_note)):
            note.setWordWrap(True)
            note.setFixedHeight(26)
            layout.addWidget(note)
        self.priority_note = QLabel("Typing takes priority.")
        self.priority_note.setWordWrap(False)
        left.addWidget(self.priority_note)
        self.typing_toggle = QCheckBox("Enable typing display")
        right.addWidget(self.typing_toggle)
        footer_height = max(self.priority_note.sizeHint().height(), self.typing_toggle.sizeHint().height())
        self.priority_note.setFixedHeight(footer_height)
        self.typing_toggle.setFixedHeight(footer_height)

        self.ad_btn = QPushButton(tr("AuxDisplay", "Apply changes"))
        self.ad_btn.setToolTip("Save the entire page, then verify acknowledgement and configuration readback.")
        self.ad_btn.clicked.connect(self.on_sync_clicked)
        self.reload_btn = QPushButton("Reload from keyboard")
        self.reload_btn.clicked.connect(self.reload_oled)
        self.insertWidget(1, self.ad_btn)
        self.addWidget(self.reload_btn)
        self.happy_toggle = QPushButton("Happy Mode Override")
        self.clock_toggle = QPushButton("Clock Mode Override")
        for button in (self.happy_toggle, self.clock_toggle):
            button.setCheckable(True)
            button.setMinimumHeight(44)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.setStyleSheet("""
                QPushButton {
                    padding: 10px 16px;
                    border: 1px solid palette(mid);
                    border-radius: 6px;
                    background-color: palette(button);
                    color: palette(button-text);
                    font-weight: bold;
                }
                QPushButton:hover { border-color: palette(highlight); }
                QPushButton:checked {
                    background-color: palette(highlight);
                    color: palette(highlighted-text);
                    border: 2px inset palette(dark);
                    padding: 11px 15px 9px 17px;
                }
                QPushButton:disabled { color: palette(mid); }
            """)
            button.setToolTip("Click to select; click again to return to the idle message. Saved by Apply changes.")
        self.override_section = QGroupBox("Idle display override")
        self.override_section.setStyleSheet('QGroupBox { background: palette(alternate-base); border: 1px solid palette(mid); border-radius: 5px; margin-top: 10px; padding: 12px 8px 8px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; font-weight: bold; }')
        override_layout = QVBoxLayout(self.override_section)
        override_layout.setSpacing(10)
        overrides = QHBoxLayout()
        overrides.addWidget(self.happy_toggle, 1)
        overrides.addWidget(self.clock_toggle, 1)
        override_layout.addLayout(overrides)
        self.override_note = QLabel("Enabling an override replaces the message when you are not typing. Typing takes priority.")
        self.override_note.setWordWrap(True)
        override_layout.addWidget(self.override_note)
        self.addSpacing(12)
        self.addWidget(self.override_section)
        self.dt_btn = QPushButton("Sync Date && Time")
        self.dt_btn.setToolTip("Synchronize now without changing the saved message or typing label.")
        self.dt_btn.clicked.connect(self.on_dt_btn)
        self.auto_clock = QCheckBox("Sync date and time on connect")
        self.auto_clock.setToolTip("Sync the PC's current time once when this keyboard connects while VialAstro is running. Enabling also syncs now. Saved on this computer for this keyboard.")
        self.auto_clock.setEnabled(False)
        self.auto_clock.toggled.connect(self.on_auto_clock_toggled)
        self.insertWidget(2, self.dt_btn)
        self.insertWidget(3, self.auto_clock, 0, Qt.AlignHCenter)
        self.oled_status = QLabel("Reading keyboard configuration…")
        self.oled_status.setWordWrap(True)
        self.addWidget(self.oled_status)
        self.addStretch(1)

        self.ad_text.setPlainText(self.ad_preview.text)
        self.ad_text.textChanged.connect(self.on_text)
        self.typing_label.textChanged.connect(self.on_typing_label_changed)
        self.ad_fonts.currentIndexChanged.connect(self.on_font_change)
        self.ad_fonts.activated.connect(self.on_font_selected)
        self.ad_font_size.valueChanged.connect(self.on_font_size_change)
        self.typing_toggle.clicked.connect(self.on_typing_update)
        self.happy_toggle.clicked.connect(self.on_happy_update)
        self.clock_toggle.clicked.connect(self.on_clock_update)
        self.refresh_typing_preview()

    def refresh_typing_preview(self):
        label = self.typing_label.toPlainText()
        self.typing_preview.set_bitmap(typing_bitmap(label))
        self.typing_preview.setEnabled(self.typing_toggle.isChecked())
        self.typing_note.setText("Fixed 6 × 8 · sample ABC → D" if self.typing_toggle.isChecked()
                                 else "Fixed 6 × 8 · typing disabled")

    def on_typing_label_changed(self):
        self.refresh_typing_preview()
        self.mark_oled_dirty()

    def rebuild(self, device):
        super().rebuild(device)
        if self.valid():
            if self._clock_keyboard is not device.keyboard:
                self.auto_clock_timer.stop()
                self._auto_clock_attempted = False
                self._clock_keyboard = device.keyboard
            self.keyboard = device.keyboard
            with QSignalBlocker(self.auto_clock):
                self.auto_clock.setChecked(self.clock_settings.value(self.clock_preference_key(), False, type=bool))
            self.auto_clock.setEnabled(True)
            self.reset_ui()
        else:
            self.ready_timer.stop()
            self.save_timer.stop()
            self.auto_clock_timer.stop()
            self.keyboard = self.oled_client = self._clock_keyboard = None
            self._auto_clock_attempted = False
            self.auto_clock.setEnabled(False)

    def clock_preference_key(self):
        uid = getattr(self.keyboard, "keyboard_id", "unknown")
        if isinstance(uid, bytes):
            uid = uid.hex()
        return "my2k/clock-sync-on-connect/" + str(uid)

    def on_auto_clock_toggled(self, checked):
        if not self.keyboard:
            return
        self.clock_settings.setValue(self.clock_preference_key(), bool(checked))
        self.auto_clock_timer.stop()
        if checked:
            self._auto_clock_attempted = False
            self.schedule_auto_clock_sync()
            if self.oled_client is None:
                self.ready_attempts = 0
                self.ready_timer.start(500)

    def schedule_auto_clock_sync(self):
        if self.auto_clock.isChecked() and not self._auto_clock_attempted and self.oled_client is not None:
            # Existing storage-export connection is not a clock-sync target.
            desc = getattr(self.device, "desc", {})
            if desc.get("product_id") != 0xf1fc:
                self.auto_clock_timer.start(0)

    def run_auto_clock_sync(self):
        if not self.auto_clock.isChecked() or self._auto_clock_attempted or self.oled_client is None or self.keyboard is None:
            return
        self._auto_clock_attempted = True  # Never retry an uncertain time command.
        try:
            self.sync_current_clock()
            self.oled_status.setText("Clock synchronized automatically. " + ("Other changes remain unsaved until Apply changes." if getattr(self, "_oled_dirty", False) else ""))
        except (OSError, RuntimeError, ValueError) as error:
            self.oled_status.setText("Automatic clock sync failed: " + str(error) + " Use Sync Date & Time to try manually.")

    def valid(self):
        return isinstance(self.device, VialKeyboard) and (self.device.keyboard and self.device.keyboard.amk_feature["aux_display"])

    def reset_ui(self):
        self.ready_attempts = 0
        self.ad_font_size.setValue(self.ad_preview.get_font_size())
        self.ad_preview.set_pixmap_size(self.keyboard.amk_aux_display["width"], self.keyboard.amk_aux_display["height"])
        self.ad_preview.update_pixmap()
        self.reload_oled()

    def reload_oled(self):
        from vi_al_addons.my2k.oled_config import OledClient
        self.ready_timer.stop()
        self.oled_client = None
        try:
            client = OledClient(self.keyboard)
            caps = client.capabilities()
            if not caps['peer_ready']:
                self.ready_attempts += 1
                if self.ready_attempts < 8:
                    self.ready_timer.start(500)
                raise RuntimeError("Waiting for Release 1 AUX configuration. Both new firmware images are required; no settings have been read yet.")
            self.ad_preview.set_pixmap_size(72, 40)
            values = client.read(refresh=True)
            self.oled_client = client
            self._load_oled_values(values)
            self.oled_status.setText("Configuration read from keyboard. " +
                ("Persistent settings." if caps['persistent'] else "Session-only settings.") +
                ("" if caps['peer_ready'] else " AUX is not ready; wait and reopen this tab."))
            self.schedule_auto_clock_sync()
            enabled = caps['peer_ready']
        except (OSError, RuntimeError, ValueError) as error:
            self.oled_status.setText(str(error))
            self.ad_text.setPlainText("")
            enabled = False
        for widget in (self.typing_toggle, self.happy_toggle, self.clock_toggle, self.typing_label, self.ad_btn):
            widget.setEnabled(enabled)
        self.ad_fonts.setEnabled(enabled)
        self.ad_font_size.setEnabled(enabled)

    def _load_oled_values(self, values):
        self._oled_loading = True
        self.ad_text.setPlainText(values['message'])
        self.typing_label.setPlainText(values['label'])
        self.typing_toggle.setChecked(values['typing'])
        self.refresh_typing_preview()
        self.happy_toggle.setChecked(values['happy'])
        self.clock_toggle.setChecked(values['clock'])
        if self.ad_fonts.findText(values['font_family']) < 0:
            self.ad_fonts.addItem(values['font_family'])
        self.ad_fonts.setCurrentText(values['font_family'])
        self.ad_font_size.setValue(values['font_size'])
        self.ad_preview.set_font(values['font_family'])
        self.ad_preview.set_font_size(values['font_size'])
        self.ad_preview.set_bitmap(values["bitmap"])
        self._oled_loading = False
        self._oled_dirty = False

    def _apply_oled(self, **changes):
        if not self.oled_client:
            return False
        try:
            values = self.oled_client.read()
            values.update(changes)
            status = self.oled_client.apply(**values)
            if values['clock']:
                try:
                    self.sync_current_clock()
                except (OSError, RuntimeError, ValueError) as error:
                    raise RuntimeError("Display settings were saved, but clock sync failed: " + str(error)) from error
            self._load_oled_values(values)
            self.oled_status.setText("OLED transfer completed; configuration readback matches. " +
                ("Save pending — wait for confirmation." if status['pending_save'] else "Settings saved." if status['durable'] else "Persistence unavailable."))
            if status['pending_save']:
                self.save_timer.start(500)
            return True
        except (OSError, RuntimeError, ValueError) as error:
            self.oled_status.setText(str(error))
            QMessageBox.warning(None, "OLED update failed", str(error))
            return False

    def check_oled_save(self):
        if not self.oled_client:
            self.save_timer.stop()
            return
        try:
            status = self.oled_client.status()
            if not status['durable']:
                self.save_timer.stop()
                self.oled_status.setText("OLED updated, but persistent storage reports an error.")
            elif not status['pending_save']:
                self.save_timer.stop()
                self.oled_status.setText("OLED updated; settings saved on keyboard storage.")
        except (OSError, RuntimeError, ValueError) as error:
            self.save_timer.stop()
            self.oled_status.setText("Save verification failed: " + str(error))

    def mark_oled_dirty(self):
        if getattr(self, "oled_client", None) and not getattr(self, "_oled_loading", False):
            self._oled_dirty = True
            self.oled_status.setText("Unsaved changes — click Apply changes to save the entire page.")

    def on_typing_update(self):
        self.refresh_typing_preview()
        self.mark_oled_dirty()
        return True

    def on_happy_update(self):
        if self.happy_toggle.isChecked():
            self.clock_toggle.setChecked(False)
        self.mark_oled_dirty()
        return True

    def on_clock_update(self):
        if self.clock_toggle.isChecked():
            self.happy_toggle.setChecked(False)
        self.mark_oled_dirty()
        return True

    def activate(self):
        if self.keyboard and hasattr(self, "oled_status"):
            self.reload_oled()

    def deactivate(self):
        self.save_timer.stop()
        if not self.auto_clock.isChecked() or self._auto_clock_attempted:
            self.ready_timer.stop()

    def on_text(self):
        text = self.ad_text.toPlainText()
        self.ad_preview.set_text(text)
        self.mark_oled_dirty()

    def on_mode_check(self):
        pass
        #if self.ad_mode.isChecked():
        #    self.ad_preview.set_mode(1)
        #else:
        #    self.ad_preview.set_mode(0)
    
    def on_sync_clicked(self):
        if self.oled_client:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                text=self.ad_text.toPlainText()
                metrics=QFontMetrics(self.ad_preview.font)
                for i,line in enumerate(text.split('\n')):
                    if not line:
                        continue
                    rect=metrics.boundingRect(line).translated(0,(self.ad_preview.font_size+1)*(i+1))
                    if rect.left()<0 or rect.top()<0 or rect.right()>=72 or rect.bottom()>=40:
                        raise ValueError("Text does not fit 72 × 40 pixels with this font. Reduce the font size or shorten the lines.")
                image=self.ad_preview.pix.toImage()
                bitmap=bytearray(360)
                for y in range(40):
                    for x in range(72):
                        if image.pixelColor(x,y).red():
                            bitmap[y//8*72+x]|=1<<(y%8)
                return self._apply_oled(message=text,label=self.typing_label.toPlainText(),typing=self.typing_toggle.isChecked(),happy=self.happy_toggle.isChecked(),clock=self.clock_toggle.isChecked(),font_family=self.ad_preview.get_font(),font_size=self.ad_preview.font_size,bitmap=bytes(bitmap))
            except (ValueError,RuntimeError) as error:
                QMessageBox.warning(None,"OLED update failed",str(error))
                return False
            finally:
                QApplication.restoreOverrideCursor()
        QMessageBox.warning(None, "Unsupported firmware", "Release 1 Main and AUX are required. No asset file was written.")
        return False

    def legacy_asset_upload(self):
        from vi_al_addons.my2k.animation import pack_anim_header
        import struct
        packed = pack_anim_header(self.ad_preview.get_pixmap_width(),
                                  self.ad_preview.get_pixmap_height(), "ABIT", 1)
        packed += struct.pack("<H", 0)
        data = self.ad_preview.get_pixmap_data()
        frames = bytearray((len(data) + 7) // 8)
        for i, color in enumerate(data):
            if color.red() > 0:
                frames[i // 8] |= 1 << (i % 8)
        packed += frames

        index = 0xFF
        closed = False
        error = None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            index = self.keyboard.open_anim_file("BW_TEXT.ABW", False)
            if index == 0xFF:
                raise RuntimeError("Could not open BW_TEXT.ABW for writing.")
            for offset in range(0, len(packed), 24):
                if not self.keyboard.write_anim_file(index, packed[offset:offset+24], offset):
                    raise RuntimeError("Text upload failed at byte {}. The display was not switched.".format(offset))
            closed = True  # Do not repeat a failed/uncertain close.
            if not self.keyboard.close_anim_file(index):
                raise RuntimeError("The text file could not be committed. The display was not switched.")
            index = self.keyboard.open_anim_file("BW_TEXT.ABW", True)
            if index == 0xFF:
                raise RuntimeError("Text uploaded, but it could not be reopened for verification.")
            closed = False
            for offset in range(0, len(packed), 24):
                expected = packed[offset:offset+24]
                actual = self.keyboard.read_anim_file(index, offset, len(expected))
                if actual is None or bytes(actual) != expected:
                    raise RuntimeError("Text readback did not match at byte {}. The display was not switched.".format(offset))
            # Original stock firmware echoes the requested read count even at
            # EOF; requiring a zero-length EOF response would break its ABI.
            # Verify every intended byte, without claiming total file length.
            closed = True
            if not self.keyboard.close_anim_file(index):
                raise RuntimeError("Text readback completed, but its file handle could not be closed.")
            if not self.keyboard.apply_aux_mode(0):
                raise RuntimeError("Text uploaded, but the keyboard rejected display mode selection.")
        except (OSError, RuntimeError, ValueError) as failure:
            error = str(failure)
        finally:
            if index != 0xFF and not closed:
                try:
                    self.keyboard.close_anim_file(index)
                except (OSError, RuntimeError, ValueError):
                    pass
            QApplication.restoreOverrideCursor()
        if error:
            QMessageBox.warning(None, tr("AuxDisplay", "Display update failed"), error)
            return False
        return True


    def on_font_selected(self):
        # Wait until Qt has completed the combo activation/popup teardown before
        # accepting text input again. Readback/programmatic changes do not take
        # focus, and keyboard navigation in an open popup remains available.
        self.ad_fonts.hidePopup()
        QTimer.singleShot(0, self.focus_message_editor)

    def focus_message_editor(self):
        if self.ad_text.isVisible() and self.ad_text.isEnabled():
            self.ad_text.setFocus(Qt.OtherFocusReason)

    def on_font_change(self):
        family = self.ad_fonts.currentText()
        if hasattr(self,"ad_preview"):
            self.ad_preview.set_font(family)
            self.mark_oled_dirty()
    
    def on_font_size_change(self):
        size = self.ad_font_size.value()
        if hasattr(self,"ad_preview"):
            self.ad_preview.set_font_size(size)
            self.mark_oled_dirty()

    def sync_current_clock(self):
        current = QDateTime.currentDateTime()
        return self.oled_client.sync_datetime(current.date().year(), current.date().month(),
            current.date().day(), current.date().dayOfWeek(), current.time().hour(),
            current.time().minute(), current.time().second())

    def on_dt_btn(self):
        datetime = QDateTime.currentDateTime()
        if getattr(self,"oled_client",None):
            try:
                self.oled_client.sync_datetime(datetime.date().year(), datetime.date().month(),
                    datetime.date().day(), datetime.date().dayOfWeek(), datetime.time().hour(),
                    datetime.time().minute(), datetime.time().second())
                self.oled_status.setText("Time synchronized and OLED transfer completed; typing has priority. " + ("Other changes remain unsaved until Apply changes." if getattr(self,"_oled_dirty",False) else ""))
                return True
            except (OSError, RuntimeError, ValueError) as error:
                QMessageBox.warning(None, "Clock sync failed", str(error))
                return False
        try:
            if not self.keyboard.apply_datetime(datetime.date().year(), datetime.date().month(),
                    datetime.date().day(), datetime.date().dayOfWeek(), datetime.time().hour(),
                    datetime.time().minute(), datetime.time().second()):
                raise RuntimeError("The keyboard rejected the date and time.")
            if not self.keyboard.apply_aux_mode(1):
                raise RuntimeError("Time synchronized, but the keyboard rejected clock mode selection.")
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.warning(None, tr("AuxDisplay", "Clock sync failed"), str(error))
            return False
        return True
