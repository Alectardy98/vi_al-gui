# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared presentation for the RGB pages; no protocol or value changes."""
from PyQt5.QtGui import QFont, QFontInfo


def enlarge_rgb_control(label, slider):
    font = QFont(label.font())
    font.setPointSizeF(QFontInfo(font).pointSizeF()*1.2)
    label.setFont(font)
    slider.setMaximumWidth(400)
    slider.setMinimumHeight(34)
    slider.setStyleSheet('''
        QSlider::groove:horizontal {
            height: 8px;
            border-radius: 4px;
            background: palette(midlight);
        }
        QSlider::handle:horizontal {
            width: 22px;
            margin: -7px 0;
            border: 1px solid palette(mid);
            border-radius: 5px;
            background: palette(button);
        }
        QSlider::handle:horizontal:hover {
            border-color: palette(highlight);
        }
        QSlider::handle:horizontal:disabled {
            background: palette(midlight);
        }
    ''')
