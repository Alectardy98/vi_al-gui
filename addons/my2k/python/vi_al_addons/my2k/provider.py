# SPDX-License-Identifier: GPL-2.0-or-later
"""Existing MY-2K/AMK controls, exposed through the same optional add-on API."""
from addon_runtime import Addon, Page, Session
from .keyboard import My2KKeyboard


def initialize_keyboard(keyboard):
    keyboard.lighting_amk_rgblight = False
    keyboard.input_performance_version = keyboard.input_performance = None


def definition_loaded(keyboard):
    payload = keyboard.definition
    keyboard.keyboard_type = payload.get('keyboardType', '')
    keyboard.keyboard_speed = payload.get('keyboardSpeed')
    performance = payload.get('inputPerformance')
    keyboard.input_performance_version = 1 if isinstance(performance, dict) and performance.get('version') == 1 else None
    keyboard.input_performance = None


def keyboard_loaded(keyboard):
    keyboard.reload_amk()


class My2KSession(Session):
    def __init__(self, window, appctx):
        from .calibrate import Calibrate
        from .apc_rt import ApcRt
        from .dks import Dks
        from .snaptap import Snaptap
        from .misc import Misc
        from .animation import Animation
        from .rgb_matrix import RgbMatrix
        from .rgb_strip import RgbStrip
        from .rgb_grid import RgbGrid
        from .lock_lights2 import LockLights
        from .touch_bar import TouchBar
        from .gaming import Gaming
        from .rgb_config import RgbConfig
        from .aux_display import AuxDsiplay
        layout = window.layout_editor
        factories = [
            ('rgb_strip', RgbStrip, 'RGB Strips', 40),
            ('rgb_grid', RgbGrid, 'RGB Grids', 50),
            ('rgb_matrix', RgbMatrix, 'RGB Matrix', 60),
            ('rgb_indicator', LockLights, 'Lock Lights', 70),
            ('touch_bar', TouchBar, 'Touch Bar', 80),
            ('gaming', Gaming, 'Gaming', 90),
            ('calibrate', Calibrate, 'Calibration', 100),
            ('apc_rt', ApcRt, 'APC/RT', 110),
            ('dks', lambda l: Dks(l, appctx), 'DKS', 120),
            ('snaptap', Snaptap, 'Snap Tap', 130),
            ('misc', lambda l: Misc(l, appctx), 'General', 140),
            ('aux_display', lambda l: AuxDsiplay(l, appctx), 'Auxiliary Display', 150),
            ('animation', lambda l: Animation(), 'Animations', 160),
            ('rgb_config', RgbConfig, 'RGB Configuration', 170),
        ]
        self.pages = []
        for attribute, factory, title, order in factories:
            editor = factory(layout)
            setattr(self, attribute, editor)
            setattr(window, attribute, editor)
            self.pages.append(Page(editor, title, order))
        self.misc.attach_animation_tools(self.animation.library_page)


ADDON = Addon('my2k', create_session=My2KSession, keyboard_mixin=My2KKeyboard,
              initialize_keyboard=initialize_keyboard, definition_loaded=definition_loaded,
              keyboard_loaded=keyboard_loaded)
