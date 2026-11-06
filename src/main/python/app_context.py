# SPDX-License-Identifier: GPL-2.0-or-later
"""Small source/frozen context; no legacy fbs build system dependency."""
from functools import cached_property
import json
from pathlib import Path
import sys


class ApplicationContext:
    def __init__(self):
        # Match the original context: Qt exists before fonts/resources are used.
        self.app

    @cached_property
    def build_settings(self):
        if getattr(sys, 'frozen', False):
            path = Path(sys._MEIPASS) / 'build-settings.json'
        else:
            path = Path(__file__).resolve().parents[3] / 'src/build/settings/base.json'
        return json.loads(path.read_text())

    def get_resource(self, name):
        if getattr(sys, 'frozen', False):
            candidates = [Path(sys._MEIPASS)/name]
        else:
            root = Path(__file__).resolve().parents[3]
            candidates = [root/'src/main/resources/base'/name, root/'src/main/icons'/name]
        for path in candidates:
            if path.is_file():
                return str(path)
        raise FileNotFoundError('Missing application resource: ' + name)


def is_frozen():
    return bool(getattr(sys, "frozen", False))
