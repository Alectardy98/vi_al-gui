# SPDX-License-Identifier: GPL-2.0-or-later
"""Version 1 of Vi_al's add-on interface. Hooks never perform discovery implicitly."""
from dataclasses import dataclass
from typing import Callable, Optional

API_VERSION = 1


@dataclass(frozen=True)
class Page:
    editor: object
    title: str
    order: int


@dataclass(frozen=True)
class Addon:
    id: str
    create_session: Optional[Callable] = None
    keyboard_mixin: Optional[type] = None
    initialize_keyboard: Optional[Callable] = None
    definition_loaded: Optional[Callable] = None
    keyboard_loaded: Optional[Callable] = None


class Session:
    """Per-window extension. Pages retain normal BasicEditor.valid() gates."""
    pages = ()

    def filter_event(self, watched, event):
        return False

    def before_close(self):
        return True
