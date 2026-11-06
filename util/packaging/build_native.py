#!/usr/bin/env python3
"""Optional MY-2K RLE accelerator. Pure Python remains a bit-identical fallback."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
package=ROOT/'addons/my2k/python/vi_al_addons/my2k'
if not package.is_dir():raise SystemExit(0)
source=package/'animation_rle_native.c'
if sys.platform=='win32':
    if shutil.which('cl'):
        subprocess.run(['cl','/nologo','/LD','/O2',str(source),'/Fe:'+str(package/'_animation_rle.dll')],check=True,cwd=package)
    elif not (package/'_animation_rle.dll').exists():
        print('No native compiler; MY-2K will use the Python encoder.')
else:
    suffix='.dylib' if sys.platform=='darwin' else '.so'
    flags=['-dynamiclib'] if sys.platform=='darwin' else ['-shared','-fPIC']
    subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O3',*flags,'-Wall','-Wextra','-Werror',str(source),'-o',str(package/('_animation_rle'+suffix))],check=True)
