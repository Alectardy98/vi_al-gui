# SPDX-License-Identifier: GPL-2.0-or-later
"""Generic page/lifecycle integration and the Add-ons menu."""
import logging
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import (QAction, QApplication, QFileDialog, QMessageBox,
                            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QListWidget, QListWidgetItem)
from .loader import installed_addons, load_errors
from .packages import inspect_package, install_package, read_index, set_enabled, storage_root


class AddonManager(QObject):
    def __init__(self, window, appctx):
        super().__init__(window)
        self.window = window
        self.sessions = []
        self.errors = []
        for addon in installed_addons():
            if addon.create_session:
                try:
                    self.sessions.append(addon.create_session(window, appctx))
                except Exception as error:
                    self.errors.append(addon.id + ': ' + str(error))
                    logging.exception('Cannot construct add-on %s', addon.id)
        QApplication.instance().installEventFilter(self)

    def pages(self):
        return [page for session in self.sessions for page in session.pages]

    def eventFilter(self, watched, event):
        for session in self.sessions:
            if session.filter_event(watched, event):
                return True
        return False

    def before_close(self):
        # Each worker must finish before the host window or HID handle closes.
        return all(session.before_close() for session in self.sessions)

    @staticmethod
    def same_controller(old, new):
        first = getattr(getattr(old, 'editor', None), 'addon_controller', None)
        return first is not None and first is getattr(getattr(new, 'editor', None), 'addon_controller', None)

    def add_menu(self, bar):
        menu = bar.addMenu('Add-ons')
        action = QAction('Install from ZIP…', self.window)
        action.triggered.connect(self.install_dialog); menu.addAction(action)
        manage = QAction('Manage Add-ons…', self.window)
        manage.triggered.connect(self.manage_dialog); menu.addAction(manage)

    def install_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self.window, 'Install Vi_al add-on', '', 'Vi_al add-on (*.zip)')
        if not path:
            return
        try:
            meta = inspect_package(path)
            text = ('Install {name} {version}?\n\n{description}\n\n'
                    'Add-ons run Python with your permissions. Install only packages you trust.\n'
                    'Restart Vi_al afterwards to load this package.').format(description=meta.get('description',''), **{k:meta[k] for k in ('name','version')})
            if QMessageBox.question(self.window, 'Install Add-on', text, QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes:
                return
            install_package(path)
            QMessageBox.information(self.window, 'Add-on installed', 'Installed successfully. Restart Vi_al when current keyboard operations are complete.')
        except Exception as error:
            QMessageBox.warning(self.window, 'Cannot install add-on', str(error))

    def manage_dialog(self):
        dialog = QDialog(self.window); dialog.setWindowTitle('Vi_al Add-ons'); dialog.resize(600, 360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Installed keyboard extensions — changes take effect after restarting Vi_al.'))
        listing = QListWidget(); layout.addWidget(listing)
        def refresh():
            listing.clear()
            for ident,row in read_index().items():
                item = QListWidgetItem('{}  {}  ({})'.format(ident,row['version'],'enabled' if row['enabled'] else 'disabled'))
                item.setData(256,ident); listing.addItem(item)
        try:
            refresh()
        except Exception as error:
            layout.addWidget(QLabel(str(error)))
        errors = self.errors + list(load_errors())
        if errors:
            message = QLabel('Could not load:\n'+'\n'.join(errors)); message.setWordWrap(True); layout.addWidget(message)
        buttons = QHBoxLayout(); layout.addLayout(buttons)
        for title, enabled in [('Enable', True),('Disable', False)]:
            button = QPushButton(title); buttons.addWidget(button)
            def change(_, state=enabled):
                item=listing.currentItem()
                if item:
                    try:
                        set_enabled(item.data(256),state); refresh()
                    except Exception as error:
                        QMessageBox.warning(dialog,'Cannot change add-on',str(error))
            button.clicked.connect(change)
        close=QPushButton('Close');close.clicked.connect(dialog.accept);buttons.addWidget(close)
        note=QLabel('Disabled package versions are retained for rollback; no keyboard settings are erased.')
        note.setWordWrap(True);layout.addWidget(note)
        dialog.exec_()
