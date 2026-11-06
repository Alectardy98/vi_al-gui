# SPDX-License-Identifier: GPL-2.0-or-later
"""Scrollable combo popups, including font lists, bounded to the current screen.

Qt menu-style combos ignore maxVisibleItems. Use its list-popup style instead,
so Qt positions the popup above/below the control within the available screen.
No models, selection signals, focus handling or device settings are changed.
"""
from PyQt5.QtCore import QObject, QEvent, Qt
from PyQt5.QtWidgets import QApplication, QComboBox


class ComboPopupLimits(QObject):
    def eventFilter(self, obj, event):
        if isinstance(obj, QComboBox) and event.type() in (QEvent.Polish, QEvent.Show):
            if not obj.property('astroBoundedPopup'):
                obj.setProperty('astroBoundedPopup', True)
                obj.setStyleSheet(obj.styleSheet() + '\nQComboBox { combobox-popup: 0; }')
                obj.setMaxVisibleItems(int(obj.property('astroPopupRows') or 10))
                view = obj.view()
                view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                view.window().installEventFilter(self)
                view.window().setProperty('astroComboPopup', True)
        elif event.type() == QEvent.Show and obj.property('astroComboPopup'):
            # Qt's own popup placement handles screen edges. The explicit size
            # cap also covers unusual fonts/high-DPI themes with very tall rows.
            screen = obj.screen() or QApplication.primaryScreen()
            if screen:
                available = screen.availableGeometry()
                obj.setMaximumSize(max(1, available.width()-16), max(1, available.height()-16))
        return super().eventFilter(obj, event)


def install_combo_popup_limits(app):
    if not hasattr(app, '_astro_combo_popup_limits'):
        app._astro_combo_popup_limits = ComboPopupLimits(app)
        app.installEventFilter(app._astro_combo_popup_limits)
    return app._astro_combo_popup_limits


class ClickComboBox(QComboBox):
    """Open after the opening click is released; select with a second click.

    Opening on press can deliver that same release to an item on some desktop
    popup placements, producing the old press/hold/release menu interaction.
    Keyboard navigation remains QComboBox's normal implementation.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._open_on_release = False
        self.setProperty('astroPopupRows', 6)
        self.setMaxVisibleItems(6)
        self.setStyleSheet('QComboBox { combobox-popup: 0; }')
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.isEditable() and not self.view().window().isVisible():
            self._open_on_release = True
            self.setFocus(Qt.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._open_on_release and event.button() == Qt.LeftButton:
            self._open_on_release = False
            if self.rect().contains(event.pos()):
                self.showPopup()
            event.accept()
            return
        super().mouseReleaseEvent(event)
