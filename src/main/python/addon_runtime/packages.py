# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded ZIP installation; immutable versions and an atomic activation index.

Packages contain trusted Python code, not sandboxed scripts. Installation only
writes the application's add-on directory; it neither imports code nor opens USB.
"""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

MAX_FILES, MAX_BYTES = 2048, 64 * 1024 * 1024


class PackageError(ValueError):
    pass


def storage_root():
    override = os.environ.get('VI_AL_ADDON_DIR')
    if override:
        return Path(override).expanduser().resolve()
    from PyQt5.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / 'addons'


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


def manifest(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_json)
    except (ValueError, UnicodeError) as error:
        raise PackageError('Invalid addon.json: ' + str(error)) from error
    if not isinstance(value, dict) or type(value.get('api')) is not int or value['api'] != 1:
        raise PackageError('This add-on needs an unsupported Vi_al API version.')
    if not isinstance(value.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', value['id']):
        raise PackageError('Invalid add-on ID.')
    if not isinstance(value.get('version'), str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?', value['version']):
        raise PackageError('Invalid add-on version.')
    if not isinstance(value.get('name'), str) or not 1 <= len(value['name']) <= 100:
        raise PackageError('Invalid add-on name.')
    if value.get('entrypoint', 'provider') != 'provider':
        raise PackageError('The supported entrypoint is provider.py.')
    return value


def inspect_package(path):
    if isinstance(path, bytes):
        payload = path
    else:
        with Path(path).open('rb') as stream:
            payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise PackageError('Package is too large.')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_BYTES:
                raise PackageError('Too many files or expanded package is too large.')
            seen = set()
            for member in members:
                name = member.filename.rstrip('/')
                parts = PurePosixPath(name).parts
                if (not parts or name.startswith('/') or '\\' in name or ':' in name or
                        any(p in ('.', '..') or p.rstrip(' .') != p or
                            p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} or
                            any(ord(c)<32 for c in p) for p in name.split('/')) or
                        stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1 or
                        name.casefold() in seen):
                    raise PackageError('Unsafe, duplicate or encrypted ZIP entry: ' + member.filename)
                seen.add(name.casefold())
            info = archive.getinfo('addon.json')
            if info.file_size > 16384:
                raise PackageError('Manifest is too large.')
            value = manifest(archive.read(info))
            prefix = 'python/vi_al_addons/' + value['id']
            for member in members:
                name = member.filename.rstrip('/')
                if member.is_dir() and name in ('python', 'python/vi_al_addons', prefix, 'resources'):
                    continue
                if not (name == 'addon.json' or name in ('README.md', 'LICENSE', 'COPYING') or
                        name.startswith(prefix + '/') or name.startswith('resources/')):
                    raise PackageError('Unexpected package entry: ' + name)
            archive.getinfo(prefix + '/provider.py')
            archive.getinfo(prefix + '/__init__.py')
            return value
    except (zipfile.BadZipFile, KeyError, OSError) as error:
        raise PackageError('Cannot read add-on ZIP: ' + str(error)) from error


def read_index(root=None):
    root = Path(root) if root is not None else storage_root()
    path = root / 'index.json'
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_unique_json)
        if not isinstance(value, dict):
            raise ValueError('expected object')
        for ident, row in value.items():
            if (not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', ident) or not isinstance(row, dict) or
                    not isinstance(row.get('directory'), str) or
                    not re.fullmatch(re.escape(ident)+r'-[A-Za-z0-9._+-]+', row['directory']) or
                    type(row.get('enabled')) is not bool):
                raise ValueError('invalid package index')
        return value
    except (OSError, ValueError, TypeError) as error:
        raise PackageError('Cannot read add-on index: ' + str(error)) from error


def _write_index(root, index):
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'index.json'
    if target.exists():
        shutil.copy2(target, root / 'index.previous.json')
    fd, name = tempfile.mkstemp(prefix='.index-', dir=root)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(index, stream, indent=2); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def install_package(path, root=None):
    # Verify before acquiring the lock or writing any state.
    with Path(path).open('rb') as stream:
        payload = stream.read(MAX_BYTES + 1)
    value = inspect_package(payload)
    digest = hashlib.sha256(payload).hexdigest()
    root = Path(root) if root is not None else storage_root()
    root.mkdir(parents=True, exist_ok=True)
    from PyQt5.QtCore import QLockFile
    lock = QLockFile(str(root / '.install.lock')); lock.setStaleLockTime(30000)
    if not lock.tryLock(0):
        raise PackageError('Another Vi_al instance is changing add-ons.')
    try:
        index = read_index(root)
        directory = value['id'] + '-' + value['version'] + '-' + digest[:16]
        packages = root / 'packages'; packages.mkdir(exist_ok=True)
        target = packages / directory
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix='.install-', dir=packages) as stage:
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    archive.extractall(stage)  # Entries were bounded and validated above.
                os.replace(stage, target)
        previous = index.get(value['id'])
        index[value['id']] = {'directory': directory, 'version': value['version'],
                              'enabled': True, 'sha256': digest,
                              'previous': previous.get('directory') if previous else None}
        _write_index(root, index)
        return value
    finally:
        lock.unlock()


def set_enabled(ident, enabled, root=None):
    root = Path(root) if root is not None else storage_root()
    from PyQt5.QtCore import QLockFile
    lock = QLockFile(str(root / '.install.lock')); lock.setStaleLockTime(30000)
    if not lock.tryLock(0):
        raise PackageError('Another Vi_al instance is changing add-ons.')
    try:
        index = read_index(root)
        if ident not in index:
            raise PackageError('Unknown installed add-on.')
        index[ident]['enabled'] = bool(enabled); _write_index(root, index)
    finally:
        lock.unlock()
