# Vi_al

<img src="src/main/icons/linux/128.png" width="88" alt="Original shaded Vial logo in dark purple">

**Vial keyboard configuration, with optional keyboard add-ons.**

Vi_al works on its own. Add-ons provide extra controls for supported keyboards
without changing the core application. Install each add-on once; it loads
automatically on future launches. The bundled release includes all three.

## Add-ons

| Package | Features |
|---|---|
| `ec_42` | Topre / electrocapacitive calibration, actuation, Rapid Trigger and live sensors |
| `alienware_aw768` | AW768 zones, effects, macro-area lighting and onboard saving |
| `my2k` | MY-2K RGB, touch, displays, GIF transfers and gaming controls |

All packages use the same versioned format and appear only for supported devices.
Add-ons run local Python code; install packages you trust. Installing an add-on
never flashes keyboard firmware.

## Project layout

```text
addons/                         Optional keyboard package sources
  ec_42/
  alienware_aw768/
  my2k/
src/main/python/                Core Vial application
  addon_runtime/                Shared installer, loader and add-on API
util/packaging/                 Builds, release packaging and add-on templates
tests/                          Optional focused regression tests, grouped by add-on
```

Every package follows this layout:

```text
addons/<id>/
  addon.json                          Name, version and API compatibility
  python/vi_al_addons/<id>/provider.py  Keyboard detection and extra pages
  resources/                          Optional assets
```

The core builds without the `addons/` directory. See the [add-on guide](docs/ADDONS.md)
for creating new packages.

## Install

Download the package for your operating system from the **[Releases tab](../../releases)**.
Python, Qt and the app's USB libraries are included; end users do not install
build tools. Normal OS USB permissions and security checks still apply.

| System | Installation |
|---|---|
| **Linux / Manjaro — AppImage** | Download `.AppImage`, enable **Allow executing as a program** in its file properties, then double-click. |
| **Linux — portable fallback** | Extract `.tar.gz`, open the `Vi_al` folder and run `Vi_al`. This option needs no FUSE mounting helper. |
| **Windows — installer** | Run `Vi_al-…-Setup.exe`, then open **Vi_al** from the Start menu. |
| **Windows — portable** | Extract `.zip` and run `Vi_al\Vi_al.exe`. |
| **macOS** | Extract the Mac ZIP, open the **Apple Silicon** or **Intel** DMG for your Mac, and drag `Vi_al.app` into **Applications**. Approve unsigned builds through the normal macOS security controls if prompted. |

Mac packages require the native release workflow; a Mac binary is not produced
by the local Linux build. See [OS requirements](docs/DEPENDENCIES.md) for remaining
platform limitations and Linux USB access.

### Install another add-on

1. Open **Add-ons → Install from ZIP…**.
2. Choose the package and confirm.
3. Restart Vi_al. Its pages appear when the supported keyboard is selected.

Use **Add-ons → Manage Add-ons…** to enable or disable installed packages.

## Build

Build from the repository root using **Python 3.11**, on the target OS.
These are developer requirements; the compiled applications include their runtimes.

### Linux / Manjaro

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r util/packaging/requirements-build.txt
.venv/bin/python util/packaging/fetch_appimage_tools.py
.venv/bin/python util/packaging/build_addons.py
.venv/bin/python util/packaging/build.py --with-addons
```

Creates an AppImage and a portable archive under `artifacts/linux/with-addons/`.

### Windows

Run in PowerShell or Command Prompt:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r util/packaging/requirements-build.txt
.\.venv\Scripts\python.exe util/packaging/build_addons.py
.\.venv\Scripts\python.exe util/packaging/build.py --with-addons
.\.venv\Scripts\python.exe util/packaging/fetch_nsis.py
.\.venv\Scripts\python.exe util/packaging/build_windows_installer.py
```

Creates a portable ZIP and offline installer under `artifacts/windows/with-addons/`.
NSIS is downloaded for the build machine only.

### macOS

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r util/packaging/requirements-build.txt
.venv/bin/python util/packaging/build_addons.py
.venv/bin/python util/packaging/build.py --with-addons
```

Creates a native DMG under `artifacts/macos/with-addons/`. Build on each architecture
or use CI for both Intel and Apple Silicon.

### Build options and GitHub releases

- **Core only:** omit `build_addons.py` and run `build.py` without `--with-addons`.
- **Optional encoder acceleration:** run `build_native.py` before `build_addons.py`;
  this requires a C compiler. The Python encoder remains available without it.
- **New add-on:** run `new_addon.py my_keyboard --name "My Keyboard"` from
  `util/packaging/`, then implement its provider and build the add-on ZIP.
- **All systems:** open **Actions → Vi_al native releases → Run workflow**.
  Download **Vi_al-release-downloads** and attach its files to your GitHub release.
  It includes the platform packages, Windows installer, Linux fallback and checksums.
  The workflow does not publish a release automatically.

See [detailed build instructions](docs/BUILDING.md) and [testing guide](docs/TESTING.md).

Based on [Vial](https://github.com/vial-kb/vial-gui). Original copyright notices
and [COPYING](COPYING) are retained.
