#!/usr/bin/env python3
"""Native Linux/Windows/macOS packaging. Optional add-ons are ZIP data only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-addons',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    label='with-addons' if args.with_addons else 'core'
    system={'linux':'linux','win32':'windows','darwin':'macos'}.get(sys.platform)
    if not system:raise SystemExit('Unsupported native build platform: '+sys.platform)
    out=(args.output or ROOT/'artifacts'/system/label).resolve();out.mkdir(parents=True,exist_ok=True)
    settings=out/'build-settings.json'
    settings.write_text((ROOT/'src/build/settings/base.json').read_text())
    version=json.loads(settings.read_text())['version']
    env=os.environ.copy();env['VI_AL_BUILD_SETTINGS']=str(settings)
    if args.with_addons:
        if not list((ROOT/'dist/addons').glob('*.zip')):
            raise SystemExit('Build the optional add-on ZIPs first: python util/packaging/build_addons.py')
        env['VI_AL_BUNDLE_ADDONS']='1'
    else:env.pop('VI_AL_BUNDLE_ADDONS',None)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(out/'dist'),
             '--workpath',str(out/'work'),str(ROOT/'util/packaging/Vi_al.spec')]
    with (out/'pyinstaller.log').open('w') as log:
        subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    name='Vi_al-'+version+'-'+system+'-'+platform.machine()+'-'+label
    if system=='linux':
        # FUSE-free release alternative: extract and run Vi_al/Vi_al directly.
        portable=Path(shutil.make_archive(str(out/(name+'-portable')),'gztar',out/'dist','Vi_al'))
        appdir=out/'Vi_al.AppDir';(appdir/'usr/bin').mkdir(parents=True,exist_ok=True)
        shutil.copytree(out/'dist/Vi_al',appdir/'usr/bin',dirs_exist_ok=True)
        shutil.copy2(ROOT/'util/packaging/AppRun',appdir/'AppRun');(appdir/'AppRun').chmod(0o755)
        shutil.copy2(ROOT/'util/packaging/vi-al.desktop',appdir/'vi-al.desktop')
        shutil.copy2(ROOT/'src/main/icons/linux/256.png',appdir/'vi-al.png')
        artifact=out/(name+'.AppImage')
        runtime=ROOT/'.build-tools/runtime-x86_64'
        if not runtime.is_file():raise SystemExit('Missing AppImage runtime; see docs/BUILDING.md')
        subprocess.run([shutil.which('appimagetool') or str(ROOT/'.build-tools/appimagetool'),'--runtime-file',str(runtime),str(appdir),str(artifact)],
                       env=dict(env,ARCH='x86_64'),check=True)
    elif system=='windows':
        artifact=Path(shutil.make_archive(str(out/name),'zip',out/'dist','Vi_al'))
    else:
        artifact=out/(name+'.dmg')
        subprocess.run(['hdiutil','create','-volname','Vi_al','-srcfolder',str(out/'dist/Vi_al.app'),
                        '-ov','-format','UDZO',str(artifact)],check=True)
    digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
    (out/'SHA256SUMS').write_text(digest+'  '+artifact.name+'\n')
    metadata={'app':'Vi_al','version':version,'platform':system,
       'architecture':platform.machine(),'bundled_addons':args.with_addons,'artifact':artifact.name,
       'sha256':digest,'hardware_tested':False}
    if system=='linux':
        metadata.update(portable_artifact=portable.name,portable_sha256=hashlib.sha256(portable.read_bytes()).hexdigest())
    (out/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(artifact);print(digest)


if __name__=='__main__':main()
