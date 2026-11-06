#!/usr/bin/env python3
"""Fetch the pinned NSIS compiler for the build machine, never for app users."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
tools=ROOT/'.build-tools/nsis';tools.mkdir(parents=True,exist_ok=True)
archive=tools/'nsis-3.13.zip'
if not archive.is_file():
    urllib.request.urlretrieve('https://downloads.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip',archive)
if hashlib.sha256(archive.read_bytes()).hexdigest()!='ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8':
    raise SystemExit('NSIS archive digest differs from the reviewed download.')
with zipfile.ZipFile(archive)as source:source.extractall(tools)
print(tools/'nsis-3.13/makensis.exe')
