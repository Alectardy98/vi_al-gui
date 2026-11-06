#!/usr/bin/env python3
"""Collect native outputs into three platform downloads plus Windows Setup."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'artifacts')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/release')
    parser.add_argument('--require-all',action='store_true')
    args=parser.parse_args()
    version=json.loads((ROOT/'src/build/settings/base.json').read_text())['version']
    found={};installers=[];appimages=[]
    for manifest in args.input.rglob('manifest.json'):
        row=json.loads(manifest.read_text())
        if not row.get('bundled_addons')or row.get('version')!=version:continue
        portable=row['platform']=='linux' and 'portable_artifact'in row
        source=manifest.parent/row['portable_artifact'if portable else'artifact']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=row['portable_sha256'if portable else'sha256']:
            raise SystemExit('Artifact checksum mismatch: '+str(source))
        found[(row['platform'],row['architecture'].lower())]=source
        if row['platform']=='linux':
            appimage=manifest.parent/row['artifact']
            if hashlib.sha256(appimage.read_bytes()).hexdigest()!=row['sha256']:
                raise SystemExit('AppImage checksum mismatch: '+str(appimage))
            appimages.append(appimage)
        installers.extend(manifest.parent.glob(f'Vi_al-{version}-windows-x86_64-Setup.exe'))
    macs={arch:p for(system,arch),p in found.items()if system=='macos'}
    linux=next((p for(system,_),p in found.items()if system=='linux'),None)
    windows=next((p for(system,_),p in found.items()if system=='windows'),None)
    complete=bool(linux and windows and installers and {'arm64','x86_64'}<=macs.keys())
    if args.require_all and not complete:
        raise SystemExit('Native Linux, Windows + Setup, and both Mac builds are required. No placeholder package was created.')
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    # Keep the download folder unambiguous without discarding older releases.
    older=[p for p in out.glob('Vi_al-*')if p.is_file()and not p.name.startswith(f'Vi_al-{version}-')]
    for old in older:
        old_version=old.name.split('-',2)[1]
        history=ROOT/'artifacts/release-history'/old_version
        history.mkdir(parents=True,exist_ok=True)
        for name in ('SHA256SUMS','BUILD-STATUS.txt'):
            if(out/name).is_file()and not(history/name).exists():
                shutil.copy2(out/name,history/name)
        destination=history/old.name
        if destination.exists():
            destination=history/(old.stem+'-'+hashlib.sha256(old.read_bytes()).hexdigest()[:12]+old.suffix)
        old.replace(destination)
    outputs=[]
    for platform,source,suffix in [('linux-x86_64',linux,'.tar.gz'),('windows-x86_64',windows,'.zip')]:
        if source:
            target=out/f'Vi_al-{version}-{platform}{suffix}'
            shutil.copy2(source,target);outputs.append(target)
    if installers:
        target=out/installers[0].name;shutil.copy2(installers[0],target);outputs.append(target)
    if appimages:
        target=out/f'Vi_al-{version}-linux-x86_64.AppImage'
        shutil.copy2(appimages[0],target);outputs.append(target)
    if {'arm64','x86_64'}<=macs.keys():
        target=out/f'Vi_al-{version}-macos.zip'
        with zipfile.ZipFile(target,'w',zipfile.ZIP_STORED)as archive:
            archive.write(macs['arm64'],'Apple-Silicon.dmg')
            archive.write(macs['x86_64'],'Intel.dmg')
            archive.writestr('START-HERE.txt','Vi_al for macOS\n\nOpen Apple-Silicon.dmg on M-series Macs, or Intel.dmg on Intel Macs.\nDrag Vi_al.app into Applications. No Python or Qt installation is needed.\nUnsigned builds may require approval in macOS Privacy & Security.\n')
        outputs.append(target)
    lines=[hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name for p in outputs]
    (out/'SHA256SUMS').write_text('\n'.join(lines)+'\n')
    (out/'BUILD-STATUS.txt').write_text('All three platform packages and Windows Setup are present.\n'if complete else 'Partial local build. macOS requires the native CI runners; no Mac package has been fabricated.\n')
    print('\n'.join(str(p)for p in outputs))


if __name__=='__main__':main()
