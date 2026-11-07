#!/usr/bin/env python3
"""Run optional Linux development checks against a compiled Vi_al application."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent


def validation_environment(mode, output, packages=None):
    """Keep test preferences and installed add-ons away from the user's profile."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('VI_AL_')}
    env.update(
        VI_AL_VALIDATION_DIR=str(output),
        VI_AL_VALIDATION_SCRIPT_DIR=str(TOOLS),
        VI_AL_ADDON_DIR=str(output / 'profile/addons'),
        XDG_CONFIG_HOME=str(output / 'profile/config'),
        XDG_DATA_HOME=str(output / 'profile/data'),
        XDG_CACHE_HOME=str(output / 'profile/cache'),
    )
    scripts = {
        'runtime': ROOT / 'util/packaging/check_runtime.py',
        'pages': TOOLS / 'capture_pages.py',
        'switches': TOOLS / 'trace_device_switch.py',
        'install': TOOLS / 'install_via_menu.py',
    }
    env['VI_AL_TEST_BRIDGE'] = str(scripts[mode])
    if mode in ('pages', 'switches'):
        env['VI_AL_HID_READ_GUARD'] = str(TOOLS / 'hid_read_guard.py')
        env['QT_QPA_PLATFORM'] = 'xcb'
    else:
        env['VI_AL_SMOKE_TEST'] = '1'
        env['QT_QPA_PLATFORM'] = 'offscreen'
    if mode == 'install':
        env['VI_AL_PACKAGE_DIR'] = str(packages)
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('runtime', 'pages', 'switches', 'install'))
    parser.add_argument('--app', required=True, type=Path,
                        help='Compiled Linux AppImage or portable Vi_al executable')
    parser.add_argument('--packages', type=Path,
                        help='Directory containing the three add-on ZIPs (install mode)')
    parser.add_argument('--output', type=Path,
                        help='New output directory; defaults to artifacts/validation/')
    args = parser.parse_args()
    if not sys.platform.startswith('linux'):
        parser.error('This runner isolates Linux profiles. Use native CI checks on other systems.')
    app = args.app.expanduser().resolve()
    if not app.is_file() or not os.access(app, os.X_OK):
        parser.error('--app must be an executable compiled application')
    packages = args.packages.expanduser().resolve() if args.packages else None
    if args.mode == 'install' and (packages is None or not list(packages.glob('*.zip'))):
        parser.error('install mode requires --packages with the three add-on ZIPs')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = (args.output or ROOT / 'artifacts/validation' / (args.mode + '-' + stamp)).resolve()
    if output.exists():
        parser.error('--output must be a new directory to avoid mixing test profiles')
    output.mkdir(parents=True)
    env = validation_environment(args.mode, output, packages)
    print('Reports:', output, flush=True)
    with (output / 'application.log').open('w') as log:
        try:
            result = subprocess.run([str(app)], env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=300)
        except subprocess.TimeoutExpired:
            print('Timed out. See application.log.', file=sys.stderr)
            return 124
    print('PASS' if result.returncode == 0 else 'FAILED; see application.log', flush=True)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
