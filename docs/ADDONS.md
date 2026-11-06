# Vi_al add-on format · API 1

The three shipped keyboard extensions use exactly the same package contract.
Their implementation sizes differ, but none is hardcoded into the host window.
The repository-level `addons/` directory is optional build input, not a runtime
Python import path. The bare app never scans that directory.

## Package layout

```text
addon.json
README.md                         optional
python/vi_al_addons/<id>/
  __init__.py
  provider.py
  ... implementation modules ...
resources/                        optional
```

ZIP the contents above, not an extra enclosing directory. `build_addons.py` does
this automatically for every `addons/*/addon.json`. Native helpers are optional;
MY-2K's Python encoder is a bit-identical fallback.

```json
{
  "api": 1,
  "id": "my_keyboard",
  "name": "My Keyboard",
  "version": "1.0.0",
  "entrypoint": "provider",
  "description": "Extra controls for this keyboard."
}
```

IDs are lowercase snake_case and also name the Python package. Versions use
`major.minor.patch` with an optional suffix. The provider exports an `ADDON`
instance from `addon_runtime.Addon` whose ID matches the manifest.

## Provider hooks

| Hook | Purpose |
|---|---|
| `create_session(window, appctx)` | Return a per-window `Session` with `Page(editor, title, order)` entries |
| `keyboard_mixin` | Optional protocol methods composed into the selected keyboard object |
| `initialize_keyboard(keyboard)` | Initialize extension state; no discovery or device writes |
| `definition_loaded(keyboard)` | Read metadata/capabilities after the Vial definition is decoded |
| `keyboard_loaded(keyboard)` | Load advertised extension state using the selected connection |

Sessions may implement `filter_event(watched, event)` and `before_close()`. The
latter returns false while an owned worker is finishing, then requests
`window.close()` again when safe. EC42 retains exclusive ownership of the selected
HID handle while polling; AW768 owns its separately verified lighting interface.

Editors use the normal `BasicEditor` lifecycle: `rebuild`, `valid`, `activate`,
`deactivate`. `valid()` must match verified keyboard identity/capabilities.
Unknown devices must remain unsupported. Do not query arbitrary vendor commands
simply because a device uses Vial.

Pages sort by `order`; core Keymap/Layout/Macros use 10/20/30, ordinary extension
pages use 40–269, Firmware Updater 270 and Matrix Tester 280. Shared-controller
pages can set `editor.addon_controller` to the same object to retain their worker
when moving between those pages. Shared keyboard drawing is available in
`addon_runtime.widgets`.

The host supplies Python 3.11+, PyQt5 Core/Gui/Widgets/Svg/Network, HIDAPI, PyUSB,
libusb-package, and the core Vial modules. Add-ons do not run pip or download code.
Vendor any other pure-Python dependency inside the add-on, or coordinate a new
host API/runtime version. AppImage/EXE/DMG builds do not embed extension Python
modules, so a newly installed package can load without recompiling the app.

## Create and install

```sh
python util/packaging/new_addon.py my_keyboard --name "My Keyboard"
# Add verified UIDs and implement controls in the generated provider/package.
python util/packaging/build_addons.py
```

Install `dist/addons/Vi_al-my_keyboard-1.0.0.zip` through the Add-ons menu and
restart the application. Installing a ZIP validates/extracts it but never imports
it in the running session. Existing keyboard operations continue with the old
code until restart.

## Storage, updates and recovery

Packages live under Qt's per-user application-data directory, in `addons/`.
`VI_AL_ADDON_DIR` can select an isolated testing profile. Neither EEPROM nor
keyboard asset storage is used for installing add-ons.

Each content-addressed version gets a separate directory. A lock serializes
changes, and the activation index is replaced atomically only after extraction.
Previous versions and the previous index are retained; loaded libraries are never
overwritten in place. Disabling a package takes effect after restart. The bundled
edition installs only absent IDs and respects disabled or newer installed copies.

ZIP validation rejects unsupported API versions, missing provider files,
traversal/absolute/Windows-device paths, symlinks, duplicate case-insensitive
names, encrypted entries, foreign Python packages and excessive file/expanded
sizes. It validates the same immutable bytes that it extracts. This is packaging
validation, **not a Python sandbox or a digital signature**. Installed providers
have the user's process permissions.

## Existing platform limits

The AW768 companion-pairing proof uses Linux sysfs, Windows CfgMgr32, or macOS
IOKit to verify the two boards share the same internal hub. Windows/macOS native
adapters still require physical acceptance. MY-2K's fastest bulk transport uses
Linux hidraw/sysfs; other platforms retain the bounded HID transport where
supported. Explicit maintenance mounting remains Linux-specific. See
[Dependency audit](DEPENDENCIES.md). Do not infer cross-platform hardware
acceptance from successful packaging.
