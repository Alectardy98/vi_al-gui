# Development tools

Optional helpers for the `dev` branch. These are not included in the application
or required for a release build. Reports, screenshots and temporary profiles are
generated under the ignored `artifacts/validation/` directory.

Run from the repository root on Linux:

```sh
# Check the packaged purple icon, image codecs and bundled libraries; no hardware.
python util/dev/run.py runtime --app /path/to/Vi_al.AppImage

# Test installation through the real Add-ons menu; no hardware.
# Use a core-only app and a directory with our three add-on ZIPs.
python util/dev/run.py install --app /path/to/Vi_al-core.AppImage --packages /path/to/addons

# Capture every page for connected keyboards using the bundled app.
python util/dev/run.py pages --app /path/to/Vi_al.AppImage

# Trace unexpected popup windows while switching MY-2K and two other devices.
python util/dev/run.py switches --app /path/to/Vi_al.AppImage
```

Close other Vial/Vi_al applications before `pages` or `switches` so HID replies
are not consumed by another process. These modes use the known protocol request
allowlist in `hid_read_guard.py` and `readonly_amk_commands.json`; unknown requests
are rejected and recorded in `hid-requests.json`. Extend that allowlist only
after checking the corresponding protocol. The tools do not flash firmware.

Every run uses a separate settings/add-on profile. Use `--output /new/directory`
to choose where reports go. Page capture and switching open a test window and
close it when finished; the installation check operates on temporary add-ons.
These operations never install packages into your normal Vi_al profile.

The scripts run through the existing packaged test bridge. The shared runtime
check remains in `util/packaging/check_runtime.py`; there is no duplicate copy.
Native Linux/Windows/macOS packaging is documented in [BUILDING.md](../../docs/BUILDING.md).
Build environments, captured evidence and old revision-specific tests stay out
of the source tree. The runner itself needs only Python's standard library.
