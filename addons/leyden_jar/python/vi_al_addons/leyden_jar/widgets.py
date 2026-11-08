# SPDX-License-Identifier: GPL-3.0-or-later
"""Layout-driven diagnostics; no hard-coded keyboard geometry."""
from collections import deque
from PyQt5.QtCore import Qt, QSize, QPointF, QRectF
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPalette
from PyQt5.QtWidgets import QWidget
from widgets.keyboard_widget import KeyboardWidget


class SensorKeyboard(KeyboardWidget):
    def sizeHint(self):
        return QSize(1050, 280)

    def minimumSizeHint(self):
        return QSize(280, 130)

    def offset(self):
        return max(0., (QWidget.width(self) - self.width * self.scale) / 2)

    def hit_test(self, position):
        return super().hit_test(QPointF(position) - QPointF(self.offset(), 0))

    def update_layout(self):
        self.scale = 1
        super().update_layout()
        self.scale = min(1.1, max(.1, QWidget.width(self) / max(1, self.width)))
        height = round(self.height * self.scale) + 2
        if self.minimumHeight() != height:
            self.setFixedHeight(height)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.offset(), 0)
        for key in self.widgets:
            painter.save()
            painter.scale(self.scale, self.scale)
            painter.translate(key.shift_x, key.shift_y)
            painter.translate(key.rotation_x, key.rotation_y)
            painter.rotate(key.rotation_angle)
            painter.translate(-key.rotation_x, -key.rotation_y)
            color = QColor('#45ae70') if key.pressed else self.palette().color(QPalette.Button)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color.darker(120))
            painter.drawPath(key.background_draw_path)
            painter.setPen(QPen(self.palette().color(QPalette.Highlight), 2)
                           if key is self.active_key else Qt.NoPen)
            painter.setBrush(color if key.pressed else color.lighter(120))
            painter.drawPath(key.foreground_draw_path)
            painter.setPen(self.palette().color(QPalette.ButtonText))
            painter.drawText(key.text_rect, Qt.AlignCenter, key.text)
            painter.restore()


class SignalGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.values = deque(maxlen=160)
        self.threshold = None
        self.setMinimumHeight(210)

    def clear(self):
        self.values.clear()
        self.update()

    def feed(self, value, threshold):
        self.values.append(value)
        self.threshold = threshold
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#181526'))
        rect = QRectF(self.rect()).adjusted(55, 25, -15, -30)
        painter.setPen(QColor('#eee8ff'))
        if not self.values:
            painter.drawText(rect, Qt.AlignCenter, 'Select or press a key to inspect its live signal.')
            return
        values = list(self.values)
        limits = values + ([self.threshold] if self.threshold is not None else [])
        low, high = min(limits) - 5, max(limits) + 5
        def y(value):
            return rect.bottom() - (value - low) / (high - low) * rect.height()
        for n in range(5):
            value = low + (high - low) * n / 4
            painter.setPen(QPen(QColor('#514763'), 1))
            painter.drawLine(round(rect.left()), round(y(value)), round(rect.right()), round(y(value)))
            painter.setPen(QColor('#eee8ff'))
            painter.drawText(3, round(y(value)) + 4, str(round(value)))
        if self.threshold is not None:
            painter.setPen(QPen(QColor('#ffbf47'), 3, Qt.DashLine))
            painter.drawLine(round(rect.left()), round(y(self.threshold)), round(rect.right()), round(y(self.threshold)))
            painter.drawText(round(rect.left()) + 5, round(y(self.threshold)) - 5, 'Activation threshold')
        curve = QPainterPath()
        for n, value in enumerate(values):
            x = rect.left() + n / max(1, len(values) - 1) * rect.width()
            if n:
                curve.lineTo(x, y(value))
            else:
                curve.moveTo(x, y(value))
        painter.setPen(QPen(QColor('#50ddff'), 3))
        painter.drawPath(curve)
        painter.setPen(QColor('#eee8ff'))
        painter.drawText(8, self.height() - 6, 'Recent live signal · DAC counts · RAM only')
