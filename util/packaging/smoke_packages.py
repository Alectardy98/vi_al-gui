#!/usr/bin/env python3
"""Run frozen core/bundled checks without keyboards or host command tools."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
system={'linux':'linux','win32':'windows','darwin':'macos'}[sys.platform]
addon_count = len(list((ROOT/'addons').glob('*/addon.json')))
for edition,count in [('core',0),('with-addons',addon_count)]:
    base=ROOT/'artifacts'/system/edition
    executable=(base/'dist/Vi_al.app/Contents/MacOS/Vi_al'if system=='macos'else
                base/'dist/Vi_al'/('Vi_al.exe'if system=='windows'else'Vi_al'))
    with tempfile.TemporaryDirectory(prefix='vi-al-smoke-')as temporary:
        temp=Path(temporary)
        empty=temp/'empty_path.py'
        # QSettings(org, app) uses NativeFormat even after setDefaultFormat.
        # Redirect this constructor too, keeping Wine's registry and the user's
        # real preferences out of both fresh-profile and upgrade checks.
        empty.write_text('import os\nfrom PyQt5 import QtCore\nos.environ["PATH"]=""\n'
                         'OriginalSettings=QtCore.QSettings\n'
                         'class QSettings(OriginalSettings):\n'
                         '    def __init__(self,*args,**kwargs):\n'
                         '        if args==("Vi_al","Vi_al"):\n'
                         '            super().__init__('+repr(str(temp/'theme.ini'))+',OriginalSettings.IniFormat)\n'
                         '        else:\n'
                         '            super().__init__(*args,**kwargs)\n'
                         'QtCore.QSettings=QSettings\n')
        if edition == 'with-addons':
            # Existing installations must receive the new default too.
            with empty.open('a') as guard:
                guard.write('settings=QSettings("Vi_al","Vi_al")\n'
                            'settings.setValue("theme","Dark")\nsettings.sync()\n')
        env=dict(os.environ,VI_AL_SMOKE_TEST='1',VI_AL_EXPECT_ADDONS=str(count),
                 VI_AL_HID_READ_GUARD=str(empty),VI_AL_ADDON_DIR=str(temp/'addons'),
                 VI_AL_TEST_BRIDGE=str(ROOT/'util/packaging/check_runtime.py'),
                 VI_AL_VALIDATION_DIR=str(base/'runtime-check'),
                 QT_QPA_PLATFORM='offscreen',XDG_CONFIG_HOME=str(temp/'config'))
        subprocess.run([str(executable)],env=env,timeout=60,check=True)
        print('PASS:',system,edition)
