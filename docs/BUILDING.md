# Building Vi_al

Use Python 3.11 and build on the target operating system. Linux builds produce
AppImages and a FUSE-free portable archive, Windows produces a portable ZIP
containing `Vi_al.exe`, and macOS produces `Vi_al.app` in a DMG. All use the same
purple vector-derived logo. Runtime libraries are bundled; see the
[dependency audit and OS requirements](DEPENDENCIES.md).

```sh
python -m venv .venv
# Linux/macOS:
.venv/bin/python -m pip install -r util/packaging/requirements-build.txt
# Windows: use .venv\Scripts\python.exe instead.
```

## Core only

```sh
python util/packaging/build.py
```

This needs no `addons/` folder and creates no keyboard-specific tabs. The built
app can later install ZIP extensions through its Add-ons menu.

## Add-on packages / bundled edition

```sh
python util/packaging/build_native.py       # Optional RLE acceleration
python util/packaging/build_addons.py
python util/packaging/build.py --with-addons
```

The bundled edition contains the same installable ZIPs; it installs missing
packages on first start and never replaces an existing installed version.
Artifacts, manifests and SHA256 checksums go under `artifacts/<platform>/`;
standalone extension ZIPs go under `dist/addons/`.

Linux packaging requires `appimagetool`, a type-2 AppImage runtime, a native C
compiler only for optional acceleration, and the usual Qt X11 libraries.
`fetch_appimage_tools.py` provisions pinned packaging tools for CI. Current local
Linux builds use this host's glibc; the Ubuntu 22.04 CI build is the distribution
build for wider Linux compatibility.

## Tests

```sh
python -m pip install -r test-requirements.txt
QT_QPA_PLATFORM=offscreen PYTHONPATH=src/main/python python -m pytest tests src/main/python/test -q
```

Tests package the current add-on sources into a temporary profile. The focused
suite uses simulated devices and requires no external firmware/C harness.
See [TESTING.md](TESTING.md) for the test layout and core-only checks.

Packaged smoke tests disable all HID enumeration/open operations:

```sh
QT_QPA_PLATFORM=offscreen VI_AL_SMOKE_TEST=1 VI_AL_EXPECT_ADDONS=0 \
  VI_AL_ADDON_DIR=/tmp/vi-al-core-check ./Vi_al-*-core.AppImage
```

Use a fresh profile and `VI_AL_EXPECT_ADDONS=3` for the bundled edition. Never
point test fixtures at an actual keyboard or a live settings directory.

## Windows and macOS

The GitHub Actions workflow builds Windows x64, Linux x64, macOS arm64 and macOS
x64 natively. Core builds verify add-on independence; only bundled editions are
collected for release downloads. Publish the fork and run **Vi_al native releases**.
The final **Vi_al-release-downloads** artifact contains:

- Linux: `Vi_al-<version>-linux-x86_64.AppImage` — allow execution, then double-click.
- Linux fallback: `Vi_al-<version>-linux-x86_64.tar.gz` — extract and run `Vi_al/Vi_al` without FUSE.
- Windows: `Vi_al-<version>-windows-x86_64.zip` — extract and run `Vi_al.exe`.
- macOS: `Vi_al-<version>-macos.zip` — choose the included Apple Silicon or Intel DMG.
- Optional Windows installer: `Vi_al-<version>-windows-x86_64-Setup.exe`.
- `SHA256SUMS` and a build-status note.

These cover three platforms, with a Windows installer and a FUSE-free Linux fallback. The two
native Mac builds share one download rather than claiming a universal binary.
Artifacts remain workflow downloads unless you separately publish a release;
the workflow does not automatically publish anything to GitHub Releases.

To build the offline Windows installer on a Windows build machine:

```sh
python util/packaging/fetch_nsis.py
python util/packaging/build_windows_installer.py
```

NSIS is needed only while building. The installer includes the entire application,
needs no downloads, installs for the current user, and preserves add-ons/settings
when uninstalled. Collect available native outputs locally with
`python util/packaging/assemble_release.py`. Its `--require-all` option refuses an
incomplete release; it never substitutes a source archive for a Mac application.

Windows binaries can additionally be built/tested through Wine with a Windows
Python installation; that is not a replacement for a physical Windows test.
macOS requires its native runner for PyInstaller and `hdiutil`. No Mac runner is
available on this development host, so local macOS packaging remains pending.
Mac builds are unsigned unless you add your own signing/notarization configuration.

The logo source is `util/packaging/vi_al_logo.svg`: original upstream Vial artwork
with a dark-purple color transform, preserving its shading and transparency.
Its rendered master `vi_al_logo.png` is checked in, so normal builds require no
artwork tools. ICO/ICNS/PNG representations are in `src/main/icons/`; regenerate
them with `python util/packaging/build_icons.py`. If editing the SVG itself,
render its master first (for example with `rsvg-convert`).
No firmware is built or flashed by this repository.

To add the Linux AppImage to your application menu with its own purple icon:

```sh
python util/packaging/install_linux_launcher.py /path/to/Vi_al.AppImage
```

This installs only per-user desktop/icon files. If you move the AppImage, rerun
the command with its new path. Some file managers show a generic executable icon
until a launcher or custom file icon has been registered.
