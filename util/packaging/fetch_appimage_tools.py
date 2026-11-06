#!/usr/bin/env python3
"""Fetch the reviewed AppImage tools; refuse a changed upstream asset."""
import hashlib
from pathlib import Path
import urllib.request
ROOT=Path(__file__).resolve().parents[2]
tools=ROOT/'.build-tools';tools.mkdir(exist_ok=True)
assets={
 'runtime-x86_64':('https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64','617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46'),
 'appimagetool.AppImage':('https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage','e8c1169c4af66c3184d7ee110713d4be04befe671fa358e2c1591ee840553b03')}
for name,(url,digest) in assets.items():
 p=tools/name
 if not p.exists():urllib.request.urlretrieve(url,p)
 if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
  raise SystemExit('Upstream asset changed: '+name+'. Review its release and update the pinned digest.')
 p.chmod(0o755)
wrapper=tools/'appimagetool'
wrapper.write_text('#!/bin/sh\nexec "$(dirname "$0")/appimagetool.AppImage" --appimage-extract-and-run "$@"\n')
wrapper.chmod(0o755)
