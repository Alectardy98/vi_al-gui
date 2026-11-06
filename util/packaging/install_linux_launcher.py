#!/usr/bin/env python3
"""Install a per-user Vi_al launcher/icon pointing to an existing AppImage."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('appimage', type=Path)
    args = parser.parse_args()
    if not sys.platform.startswith('linux'):
        parser.error('The desktop launcher is for Linux.')
    target = args.appimage.expanduser().resolve()
    if not target.is_file() or any(c in str(target) for c in '\n\r'):
        parser.error('Choose an existing AppImage with a single-line path.')
    data = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    icons = data / 'icons/hicolor'
    for size in (128, 256, 512, 1024):
        folder = icons / f'{size}x{size}/apps'
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f'src/main/icons/linux/{size}.png', folder / 'vi-al.png')
    # Desktop Exec is tokenized by the launcher, not passed to a shell.
    executable = str(target).replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        executable = executable.replace(char, '\\' + char)
    text = (ROOT / 'util/packaging/vi-al.desktop').read_text()
    text = text.replace('Exec=Vi_al', f'Exec="{executable}"')
    applications = data / 'applications'
    applications.mkdir(parents=True, exist_ok=True)
    launcher = applications / 'vi-al.desktop'
    launcher.write_text(text)
    for command in (('gtk-update-icon-cache', '-f', '-t', str(icons)),
                    ('update-desktop-database', str(applications))):
        if shutil.which(command[0]):
            subprocess.run(command, check=False, capture_output=True)
    if shutil.which('gio'):
        # File managers otherwise show a generic executable for AppImages.
        subprocess.run(['gio', 'set', str(target), 'metadata::custom-icon',
                        (icons / '256x256/apps/vi-al.png').as_uri()],
                       check=False, capture_output=True)
    print(launcher)


if __name__ == '__main__':
    main()
