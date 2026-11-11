# SPDX-License-Identifier: GPL-2.0-or-later
"""Vi_al's web-inspired purple palette and native Qt control styling.

No font, window, keyboard or slider dimensions are forced here. Device status
colors and add-on color previews keep their own palettes/styles.
"""
from PyQt5.QtGui import QPalette

NAME = "Vi_al Purple"
# Match the web keyboard's keycap gradient, independently of selection colors.
KEYCAP_TOP = "#4a4352"
KEYCAP_BOTTOM = "#342e3d"
COLORS = {
    QPalette.Window: "#17151b",
    QPalette.WindowText: "#e9e5ef",
    QPalette.Base: "#18151d",
    QPalette.AlternateBase: "#211e27",
    QPalette.ToolTipBase: "#211e27",
    QPalette.ToolTipText: "#ede7f6",
    QPalette.Text: "#e9e5ef",
    QPalette.Button: KEYCAP_BOTTOM,
    QPalette.ButtonText: "#ede7f6",
    QPalette.BrightText: "#ffb3b0",
    QPalette.Link: "#c9a7ff",
    QPalette.LinkVisited: "#b392f4",
    QPalette.Highlight: "#b392f4",
    QPalette.HighlightedText: "#160f23",
    QPalette.Light: "#5c5365",
    QPalette.Midlight: "#494050",
    QPalette.Mid: "#37323f",
    QPalette.Dark: "#151219",
    QPalette.Shadow: "#0f0c14",
    (QPalette.Disabled, QPalette.ButtonText): "#81758e",
    (QPalette.Disabled, QPalette.WindowText): "#81758e",
    (QPalette.Disabled, QPalette.Text): "#81758e",
    (QPalette.Disabled, QPalette.Highlight): "#4b365f",
    (QPalette.Disabled, QPalette.HighlightedText): "#c4b4d4",
}

STYLESHEET = """
QMenuBar, QMenu {
    background: #1c1922;
    color: #e9e5ef;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #4b365f;
    color: #f0e1ff;
}
QMenu { border: 1px solid #484050; }
QMenu::separator { background: #37323f; height: 1px; }
QToolTip {
    color: #ede7f6;
    background: #211e27;
    border: 1px solid #614879;
    padding: 4px;
}
QPushButton, QToolButton {
    background: #342e3d;
    color: #ede7f6;
    border: 1px solid #484050;
    border-radius: 5px;
    padding: 5px 9px;
}
SquareButton { padding: 0px; border-radius: 4px; }
QPushButton:hover, QToolButton:hover {
    background: #40364c;
    border-color: #a38bba;
}
QPushButton:pressed, QToolButton:pressed,
QPushButton:checked, QToolButton:checked {
    background: #4b365f;
    color: #f0e1ff;
    border-color: #b392f4;
}
QPushButton:default { border-color: #b392f4; }
QPushButton:disabled, QToolButton:disabled {
    color: #81758e;
    background: #26212e;
    border-color: #37323f;
}
QPushButton:focus, QToolButton:focus { border-color: #c8a6ff; }
QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox {
    background: #18151d;
    color: #e9e5ef;
    border: 1px solid #494050;
    border-radius: 4px;
    selection-background-color: #b392f4;
    selection-color: #160f23;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QAbstractSpinBox:focus, QComboBox:focus { border-color: #b392f4; }
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {
    color: #81758e;
    border-color: #37323f;
}
QComboBox QAbstractItemView {
    background: #211e27;
    color: #e9e5ef;
    selection-background-color: #4b365f;
    selection-color: #f0e1ff;
    border: 1px solid #614879;
}
QTabWidget::pane {
    border: 1px solid #37323f;
    background: #211e27;
}
QTabBar::tab {
    background: #211e27;
    color: #afa5ba;
    border: 1px solid #37323f;
    padding: 6px 10px;
}
QTabBar::tab:hover { background: #342e3d; color: #e9e5ef; }
QTabBar::tab:selected {
    background: #35283f;
    color: #ddc5fa;
    border-color: #614879;
}
QTabBar::tab:disabled { color: #81758e; }
QHeaderView::section {
    background: #342e3d;
    color: #e9e5ef;
    border: 1px solid #37323f;
    padding: 4px;
}
QAbstractItemView { alternate-background-color: #211e27; }
QProgressBar {
    border: 1px solid #494050;
    background: #18151d;
    color: #ede7f6;
    text-align: center;
}
QProgressBar::chunk { background: #9a73d7; }
"""
