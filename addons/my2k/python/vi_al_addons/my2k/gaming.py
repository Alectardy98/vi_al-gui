# SPDX-License-Identifier: GPL-2.0-or-later
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QLabel, QPushButton, QScrollArea, QComboBox, QSizePolicy
from editor.basic_editor import BasicEditor
from vial_device import VialKeyboard
from keycodes.keycodes import Keycode
from widgets.key_widget import KeyWidget
from widgets.keyboard_widget import KeyboardWidget
from tabbed_keycodes import FilteredTabbedKeycodes
from vi_al_addons.my2k.gaming_protocol import GamingClient, valid_key


def key_filter(key):
    try:
        return valid_key(Keycode.deserialize(key.replace('(kc)', '(KC_A)'), reraise=True))
    except Exception:
        return False


class GameControlKey(KeyWidget):
    selected = pyqtSignal(object)

    def mousePressEvent(self, event):
        # Use the normal key hit testing, but target this page's local picker.
        # Other tabs retain their existing global bottom tray.
        KeyboardWidget.mousePressEvent(self, event)
        self.selected.emit(self if self.active_key is not None else None)


class Gaming(BasicEditor):
    def __init__(self, layout_editor):
        super().__init__()
        self.keyboard = self.client = None
        self.loading = True
        self.revision = 0
        self.keys = {}
        self.pickers = {}
        self.targets = {}
        self.default_buttons = {}
        self.rom_client = None
        self.rom_clients = {}
        self.rom_widgets = {}
        self.active = False
        self.rom_load_timer = QTimer(self)
        self.rom_load_timer.setSingleShot(True)
        self.rom_load_timer.timeout.connect(self.load_current_rom_page)
        self.dirty = set()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.apply_live)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(500)
        self.poll_timer.timeout.connect(self.poll)
        self.pages = QTabWidget()
        self.note = QLabel('Assign the User mode keycodes: OLED Default, NES, GBC, Doom, GIF Next and OLED Mode toggle. Games require Standard USB mode. While a game runs, keyboard input goes only to that game. Press its mode key again, or OLED Default, to return to typing. Controls save automatically.')
        self.note.setWordWrap(True)
        self.addWidget(self.note)
        for game, title, actions in ((1, 'NES', ('A', 'B', 'Select', 'Start', 'Up', 'Down', 'Left', 'Right')), (3, 'Game Boy Color', ('A', 'B', 'Select', 'Start', 'Up', 'Down', 'Left', 'Right')), (2, 'Doom', ('Fire', 'Use / open door', 'Run', 'Detail (hold Run + Detail)', 'Forward', 'Backward', 'Turn left', 'Turn right'))):
            page = QWidget()
            layout = QVBoxLayout(page)
            if game in (1, 3):
                roms = QComboBox()
                roms.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                roms.setMinimumContentsLength(16)
                roms.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                roms.setMinimumWidth(0)
                use = QPushButton('Use selected ROM')
                use.setEnabled(False)
                status = QLabel('ROMs live in the %s folder on keyboard storage.' % ('gbc' if game == 3 else 'nes'))
                status.setWordWrap(True)
                self.rom_widgets[game] = (roms, use, status)
                if game == 1:
                    self.roms, self.rom_use, self.rom_status = self.rom_widgets[game]
                row = QHBoxLayout()
                row.addWidget(use)
                row.addWidget(roms, 1)
                layout.addLayout(row)
                layout.addWidget(status)
                use.clicked.connect(lambda checked=False, g=game: self.select_rom(g))
                roms.currentIndexChanged.connect(lambda *args, g=game: self.rom_changed(game=g))
            grid = QGridLayout()
            self.keys[game] = []
            for i, name in enumerate(actions):
                row, col = divmod(i, 4)
                label = QLabel(name)
                label.setAlignment(Qt.AlignCenter)
                grid.addWidget(label, row * 2, col)
                key = GameControlKey(key_filter)
                key.setMinimumSize(100, 80)
                key.changed.connect(lambda *args, g=game: self.changed(g))
                key.selected.connect(lambda target, g=game: self.select_control(g, target))
                grid.addWidget(key, row * 2 + 1, col, Qt.AlignCenter)
                grid.setColumnStretch(col, 1)
                self.keys[game].append(key)
            layout.addLayout(grid)
            hint = QLabel('Click a control to choose the ordinary keyboard key that will activate it. Bindings use the resolved keycode on your active QMK layer. None disables a control. Firmware mode keys remain available on your normal Vial keymap.')
            hint.setWordWrap(True)
            layout.addWidget(hint)
            defaults = QPushButton('Restore default controls')
            defaults.clicked.connect(lambda checked=False, g=game: self.defaults(g))
            layout.addWidget(defaults)
            self.default_buttons[game] = defaults
            picker = FilteredTabbedKeycodes(keycode_filter=key_filter)
            picker.keycode_changed.connect(lambda code, g=game: self.pick_key(g, code))
            picker.anykey.connect(lambda g=game: self.pick_any(g))
            picker.setEnabled(False)
            layout.addWidget(picker)
            self.pickers[game] = picker
            self.targets[game] = None
            layout.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setWidget(page)
            self.pages.addTab(scroll, title)
        self.addWidget(self.pages)
        self.pages.currentChanged.connect(self.game_page_changed)
        self.status = QLabel('Connect a supported MY-2K Gaming keyboard.')
        self.status.setWordWrap(True)
        self.addWidget(self.status)
        self.pages.setEnabled(False)

    def valid(self):
        return bool(isinstance(self.device, VialKeyboard) and self.device.keyboard and
                    getattr(self.device.keyboard, 'amk_rgb_indicator', None) and
                    tuple(i.get('index') for i in self.device.keyboard.amk_rgb_indicator.get('indicators', [])) == (125, 126, 112, 64, 65, 127))

    def rebuild(self, device):
        self.active = False
        self.rom_load_timer.stop()
        self.close_roms()
        self.clear_selection()
        self.timer.stop()
        self.poll_timer.stop()
        self.client = self.keyboard = None
        self.dirty.clear()
        self.pages.setEnabled(False)
        super().rebuild(device)
        if self.valid():
            self.keyboard = device.keyboard

    def set_keys(self, game, values):
        before = self.loading
        self.loading = True
        for key, value in zip(self.keys[game], values):
            key.set_keycode(Keycode.serialize(value))
        self.loading = before

    def activate(self):
        self.active = True
        if not self.keyboard:
            return
        self.loading = True
        self.client = None
        self.pages.setEnabled(False)
        try:
            client = GamingClient(self.keyboard)
            caps = client.capabilities()
            for game in ((1,3,2) if caps.get('gbc') else (1,2)):
                values, self.revision, status = client.read(game)
                self.set_keys(game, values)
            if status['error']:
                raise RuntimeError('Main persistence error; controls preserved.')
            self.dirty.clear()
            self.pages.setTabEnabled(1, bool(caps.get('gbc')))
            if not caps.get('gbc'):self.rom_widgets[3][2].setText('Game Boy Color requires matching Main and AUX firmware.')
            self.client = client
            self.pages.setEnabled(not caps['active'])
            self.status.setText('Exit the game using OLED Default or its mode key before editing controls.' if caps['active'] else 'Controls loaded from keyboard. Games require Standard USB (1,000 Hz).')
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(str(error))
        finally:
            self.loading = False
        self.schedule_rom_load()

    def game_page_changed(self, *args):
        self.clear_selection()
        self.schedule_rom_load()

    def schedule_rom_load(self):
        self.rom_load_timer.stop()
        if self.active and not self.loading and self.client and self.pages.isEnabled():
            if self.pages.currentIndex() in (0, 1):
                self.rom_load_timer.start(0)
            else:
                self.close_roms()

    def load_current_rom_page(self):
        if self.active and self.client and self.pages.isEnabled():
            game = {0: 1, 1: 3}.get(self.pages.currentIndex())
            if game is not None and self.pages.isTabEnabled(self.pages.currentIndex()):
                self.rom_widgets[game][2].setText('Loading ROM list from keyboard…')
                self.reload_roms(game)

    def deactivate(self):
        self.active = False
        self.rom_load_timer.stop()
        self.close_roms()
        self.clear_selection()
        self.timer.stop()
        if self.dirty:
            self.apply_live()
        self.poll_timer.stop()

    def close_roms(self, game=None):
        for g in ((game,) if game is not None else (1,3)):
            self.rom_widgets[g][1].setEnabled(False)
            client = self.rom_clients.pop(g, None)
            if client is not None:client.close()
        self.rom_client = self.rom_clients.get(1)

    def show_roms(self, rows, truncated, game=1):
        roms, use, status = self.rom_widgets[game]
        roms.blockSignals(True)
        roms.clear()
        selected = -1
        for row in rows:
            controller = ('type 0x%02X' % row['mapper'] if row['error'] else 'MBC %d' % row['mapper']) if game==3 else 'mapper %d' % row['mapper']
            roms.addItem('%s — %s, %.0f KiB%s' % (row['name'], controller, row['size']/1024, '' if not row['error'] else ' — unsupported'), row)
            roms.setItemData(roms.count()-1, row['name'], Qt.ToolTipRole)
            if row['selected']:selected = roms.count()-1
        if selected >= 0:roms.setCurrentIndex(selected)
        roms.blockSignals(False)
        self.rom_changed(game=game)
        if truncated:status.setText('The ROM folder exceeds the 512-entry scan limit; only the bounded catalogue is shown.')

    def rom_changed(self, *args, game=1):
        roms, use, status = self.rom_widgets[game]
        row = roms.currentData()
        use.setEnabled(bool(row and not row['error'] and not row['selected']))
        if row:status.setText(('Saved selection. ' if row['selected'] else '') + row['status'] + '. Games require Standard (1K) mode.')

    def reload_roms(self, game=1):
        # There is one physical bulk transport; retire the other page first.
        self.close_roms()
        if not self.keyboard:return
        try:
            from vi_al_addons.my2k.nes_library_protocol import NesLibraryClient, GbcLibraryClient
            client = (GbcLibraryClient if game==3 else NesLibraryClient)(self.keyboard)
            self.rom_clients[game] = client
            self.rom_client = self.rom_clients.get(1)
            self.show_roms(*client.catalogue(), game=game)
        except (OSError, RuntimeError, ValueError) as error:
            self.rom_widgets[game][2].setText(str(error) + ' Switch away and back to reload this ROM page.')
            self.close_roms(game)

    def select_rom(self, game=1):
        roms, use, status = self.rom_widgets[game]
        row = roms.currentData()
        client = self.rom_clients.get(game)
        if not client or not row or row['error']:return
        use.setEnabled(False)
        try:
            self.show_roms(*client.select(row['name']), game=game)
            status.setText('ROM selection saved — acknowledgement and keyboard readback verified. Press your physical %s mode key to play.' % ('Game Boy Color' if game==3 else 'NES'))
        except (OSError, RuntimeError, ValueError) as error:
            status.setText(str(error) + ' Switch away and back to this ROM page before trying another change.')
            self.close_roms(game)

    def clear_selection(self, *args):
        for game, target in self.targets.items():
            if target is not None:
                target.deselect()
            self.targets[game] = None
            self.pickers[game].setEnabled(False)

    def select_control(self, game, target):
        self.clear_selection()
        if target is not None and self.client and self.pages.isEnabled():
            # clear_selection may have deselected the same target.
            target.active_key = target.widgets[0]
            target.update()
            self.targets[game] = target
            self.pickers[game].setEnabled(True)

    def pick_key(self, game, code):
        target = self.targets[game]
        if target is not None and self.client and self.pages.isEnabled():
            target.on_keycode_changed(code)

    def pick_any(self, game):
        target = self.targets[game]
        if target is not None and self.client and self.pages.isEnabled():
            target.on_anykey()

    def changed(self, game):
        if self.loading or not self.client:
            return
        self.dirty.add(game)
        self.status.setText('Applying controls…')
        self.timer.start(200)

    def defaults(self, game):
        values = (0x1d, 0x1b, 0xe5, 0x28, 0x52, 0x51, 0x50, 0x4f) if game in (1,3) else (0x1d, 0x1b, 0xe5, 0x28, 0x1a, 0x16, 0x04, 0x07)
        self.set_keys(game, values)
        self.changed(game)

    def report(self, status):
        if status['error']:
            self.status.setText('Controls applied, but saving failed. Reconnect before further changes.')
        elif status['pending']:
            self.status.setText('Applied and readback verified; saving. Pause typing briefly until Saved appears.')
            self.poll_timer.start()
        else:
            self.status.setText('Saved — keyboard acknowledgement and readback verified.')
            self.poll_timer.stop()

    def apply_live(self):
        if not self.client or not self.dirty:
            return
        try:
            for game in sorted(self.dirty):
                values = [Keycode.deserialize(k.keycode, reraise=True) for k in self.keys[game]]
                self.revision, status = self.client.apply(game, values, self.revision)
            self.dirty.clear()
            self.report(status)
        except (OSError, RuntimeError, ValueError) as error:
            self.timer.stop()
            self.poll_timer.stop()
            self.client = None
            self.pages.setEnabled(False)
            self.status.setText(str(error) + ' Reopen Gaming before editing; no save was retried.')

    def poll(self):
        if not self.client or self.dirty:
            return
        try:
            _, self.revision, status = self.client.read(1)
            self.report(status)
        except (OSError, RuntimeError, ValueError) as error:
            self.poll_timer.stop()
            self.status.setText(str(error))
