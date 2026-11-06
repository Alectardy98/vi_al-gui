#!/usr/bin/env python3
"""Package the built Windows payload as a self-contained offline NSIS installer."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def quote_path(path):
    return str(path).replace('$', '$$').replace('"', '$\\"')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--makensis', type=Path)
    parser.add_argument('--payload', type=Path, default=ROOT/'artifacts/windows/with-addons/dist/Vi_al')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/windows/with-addons')
    args = parser.parse_args()
    payload = args.payload.resolve()
    if not (payload/'Vi_al.exe').is_file():
        parser.error('Build the Windows bundled edition first.')
    compiler = args.makensis or shutil.which('makensis') or ROOT/'.build-tools/nsis/nsis-3.13/makensis.exe'
    if not Path(compiler).is_file():
        parser.error('NSIS is required on the build machine only; it is not an app dependency.')
    out = args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    version = json.loads((ROOT/'src/build/settings/base.json').read_text())['version']
    artifact = out/f'Vi_al-{version}-windows-x86_64-Setup.exe'
    entries = sorted(payload.rglob('*'))
    commands = ['Delete "$INSTDIR\\'+quote_path(p.relative_to(payload)).replace('/', '\\')+'"'
                for p in entries if p.is_file()]
    commands.extend('RMDir "$INSTDIR\\'+quote_path(p.relative_to(payload)).replace('/', '\\')+'"'
                    for p in sorted((p for p in entries if p.is_dir()),key=lambda p:len(p.parts),reverse=True))
    uninstall = out/'uninstall-files.nsh';uninstall.write_text('\n'.join(commands)+'\n')
    prefix = '/' if str(compiler).lower().endswith('.exe') else '-'
    definitions = {'VERSION':version,'OUTPUT':artifact,'PAYLOAD':payload,
                   'APPICON':ROOT/'src/main/icons/Icon.ico','UNINSTALL_FILES':uninstall}
    cmd = [str(compiler),prefix+'V2']
    cmd.extend(prefix+'D'+key+'='+str(value) for key,value in definitions.items())
    cmd.append(str(ROOT/'util/packaging/windows_installer.nsi'))
    subprocess.run(cmd,check=True)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (out/'INSTALLER-SHA256SUMS').write_text(digest+'  '+artifact.name+'\n')
    print(artifact);print(digest)


if __name__ == '__main__':
    main()
