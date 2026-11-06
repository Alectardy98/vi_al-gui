# SPDX-License-Identifier: GPL-2.0-or-later
"""Load explicitly installed packages. Repository add-ons are never auto-imported."""
import importlib
import logging
from pathlib import Path
import sys
import types
from .api import Addon
from .packages import storage_root, read_index, manifest, PackageError

_loaded, _errors = None, []
_classes = {}


def installed_addons():
    global _loaded
    if _loaded is not None:
        return _loaded
    _loaded = []
    try:
        # The bundled edition ships these same ZIPs; it installs only absent IDs
        # and never replaces an installed version or re-enables a disabled one.
        if getattr(sys, 'frozen', False):
            from .packages import inspect_package, install_package
            bundled = Path(sys._MEIPASS) / 'bundled-addons'
            present = read_index()
            for package in sorted(bundled.glob('*.zip')):
                identity = inspect_package(package)['id']
                if identity not in present:
                    install_package(package); present = read_index()
        root, index = storage_root(), read_index()
    except PackageError as error:
        _errors.append(str(error)); return _loaded
    namespace = sys.modules.setdefault('vi_al_addons', types.ModuleType('vi_al_addons'))
    namespace.__path__ = []
    for ident, row in sorted(index.items()):
        if not row['enabled']:
            continue
        try:
            package = root / 'packages' / row['directory']
            metadata = manifest((package / 'addon.json').read_bytes())
            if metadata['id'] != ident or metadata['version'] != row['version']:
                raise PackageError('Installed add-on identity differs from its index.')
            namespace.__path__.append(str(package / 'python/vi_al_addons'))
            module = importlib.import_module('vi_al_addons.' + ident + '.provider')
            spec = module.ADDON
            if not isinstance(spec, Addon) or spec.id != ident:
                raise PackageError('Invalid provider interface for ' + ident)
            _loaded.append(spec)
        except Exception as error:
            message = ident + ': ' + str(error)
            _errors.append(message); logging.exception('Cannot load add-on %s', ident)
    return _loaded


def load_errors():
    installed_addons()
    return tuple(_errors)


def create_keyboard(dev, *args, **kwargs):
    from protocol.keyboard_comm import Keyboard
    addons = tuple(installed_addons())
    mixins = tuple(a.keyboard_mixin for a in addons if a.keyboard_mixin is not None)
    if mixins not in _classes:
        _classes[mixins] = type('ExtendedKeyboard', (Keyboard, *mixins), {'_vi_al_addons': addons})
    return _classes[mixins](dev, *args, **kwargs)


def initialize_keyboard(keyboard):
    for addon in getattr(keyboard, '_vi_al_addons', ()):
        if addon.initialize_keyboard:
            addon.initialize_keyboard(keyboard)


def definition_loaded(keyboard):
    for addon in getattr(keyboard, '_vi_al_addons', ()):
        if addon.definition_loaded:
            addon.definition_loaded(keyboard)


def keyboard_loaded(keyboard):
    for addon in getattr(keyboard, '_vi_al_addons', ()):
        if addon.keyboard_loaded:
            addon.keyboard_loaded(keyboard)
