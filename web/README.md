# Vi_al Web

A native browser frontend for Vi_al, served as a static GitHub Pages site.
Keyboard traffic stays between the browser and USB device. There is no backend,
account, telemetry or cloud settings storage, and no desktop helper is required.
Use desktop Chrome or Edge over HTTPS, or `localhost` during development.

## Run locally

```sh
cd web
npm ci
npm run dev
```

Open the localhost address printed by Vite. Close desktop keyboard configurators
before connecting: competing HID readers can consume each other's replies.
Use **Explore demo** to inspect the core UI without granting USB access.

## Publish with GitHub Pages

1. Commit and push the `web` branch, including `web/package-lock.json`.
2. In the GitHub repository, open **Settings → Pages → Build and deployment**
   and choose **GitHub Actions** as the source.
3. Allow the `github-pages` environment to deploy from `web` if its branch
   policy is restricted. The **Vi_al web** workflow tests, builds and deploys
   this branch. Pull requests are tested but never deployed.

The normal project URL is `https://alectardy98.github.io/vi_al-gui/` unless the
repository has a custom domain. GitHub shows the actual URL after deployment.
All asset paths are relative, so the build also works below a repository path.
The workflow requires GitHub Pages to be enabled; local validation does not
prove that a GitHub deployment has occurred.

```sh
npm run build       # Output: web/dist/ — only this folder is published
npm run preview     # Serve the production output locally
npm test           # Codec, transport, corruption and transfer tests
npm run test:browser
npm run test:production  # After build: check the bundled site below /vi_al-gui/
```

Browser tests use simulated devices and never access connected keyboards.
Locally they use `/opt/google/chrome/chrome`, overridable with `CHROME_BIN`.
CI installs its own Chromium through Playwright.

## Structure

```text
web/
  src/                       Browser UI, WebHID and Vial core
    data/                    Keycodes, fonts, encoding and QMK settings
  addons/<id>/
    provider.js              Add-on identity matching and pages
    protocol.js              Browser implementation of the device protocol
  assets/                    Purple icons and other browser assets
  licenses/                  Notices included in the static build
  tests/                     Protocol fixtures and simulated browser tests
  scripts/                   Build checks and optional desktop-data exporters
  package.json               Build and test commands
  vite.config.js             Static-site build configuration
```

The website can be built and tested from a copy of `web/` alone. GitHub's
deployment workflow stays at `.github/workflows/web.yml`, where GitHub requires
it. The root `addons/` directory is exclusively for the desktop application.

Every browser add-on exports `{id, name, supports(keyboard), pages}`. A page is
`{id, title, render(container, context)}`. Use `context.run()` for user actions,
`context.read()` for polling, and stop work when `context.signal` is aborted.
These share a connection-wide operation queue, including across page changes.
`keyboard.request()` uses the single serialized 32-byte raw HID transport.
Timeouts invalidate the connection; mutation requests are never retried.

Browser providers are bundled at build time using Vite's local module discovery.
The core builds if `web/addons/` is absent. Desktop Python add-on ZIPs cannot
execute in a browser. Browser providers are kept separate from desktop package
sources, so the desktop packager needs no web-specific changes. Existing Python
providers and firmware are unchanged.

The optional Python exporters in `web/scripts/` refresh checked-in data from
the desktop source tree. They are developer synchronization tools, not required
by `npm ci`, the website build, or browser tests. The optional integration test
in `web/tests/desktop/` checks desktop ZIPs from the complete repository.
Icons and the QMK settings schema are local copies in `web/assets/` and
`web/src/data/`; refresh those copies deliberately when their desktop originals
change.

## Current controls and limits

| Area | Browser implementation |
|---|---|
| Vial core | Actual compressed definition, correctly placed layout alternatives and ISO/stepped keys, layers, categorized keycode tabs, firmware-defined User keycodes, modifier/layer-tap builder, encoders, keymap export, macros, Tap Dance, combos, key overrides, alternate repeat, QMK settings, generic lighting, unlock/lock and matrix tester |
| EC42 | Verified v2.9 identity, global/per-key actuation, atomic global reset, Rapid Trigger, live sensors, calibration backup/capture/review/apply and stored readback |
| MY-2K | RGB region effects/colors/brightness, Lock Lights, touch/jitter, visual sleep, Standard/High Performance selection, OLED message/label/overrides, clock sync, game bindings and ROM selection, GIF conversion, slot preview/upload/clear/play |
| AW768 | Explicit original-PCB selection, native group effects, Macro zone color, full two-pass onboard save and group readback |

USB grants are browser permissions, not website account permissions. MY-2K file
access needs a separate **WebUSB** grant; it uses the original AFB control/bulk
interface, including negotiated lossless RLE, instead of mounting the drive.
No flash/UF2 operation is implemented here. The browser cannot invoke the OS
mount/eject tools or independently prove internal USB hub topology for AW768;
the user must choose the correct native PCB. Legacy Macro color readback can be
unavailable even when the feature write completes, and the UI states this.

The Keymap picker has **Basic, ISO/JIS, Layers, Quantum, Backlight, Media & Mouse,
MIDI, Tap Dance, User and Macro** tabs, plus **All** and **Any**. Search checks
every category, including custom names and descriptions. The **User** tab reads
`customKeycodes` from the connected keyboard, preserving definition-order IDs
even when an optional `displayOrder` changes their presentation. Firmware counts
bound the Macro and Tap Dance entries; optional MIDI/Quantum features follow
the capabilities advertised by the device.

Modifier and layer-tap actions prompt for their inner basic key before saving.
**Any** accepts supported names and aliases, `USER00`, 16-bit values, and
expressions such as `LCTL(KC_A)` or `LT(1,KC_SPC)`. Selecting tabs, searching or
previewing physical layout options sends no settings writes. Use **Apply layout**
to save physical options; selecting a keycode saves that assignment and verifies
its readback.

Manual EC calibration requires the browser Save File Picker API to confirm a
recovery file was written before volatile capture starts. The original GPIO,
calibration rules and firmware remain unchanged. Browser rendering is not a
firmware or sensor-performance benchmark.

GIF conversion uses the browser's `ImageDecoder`, preserves source frame delays,
supports square crop or whole-image padding, and produces the existing 128×128
RGB565 CRS format (up to 512 frames). Browser file downloads are saved according
to the browser's configured location; the website cannot force the Desktop.
Clock-on-connect is an opt-in preference for this site/browser and requires the
page to be open. It cannot synchronize while the site is closed.

Desktop-only operations currently include firmware flashing/bootloader helpers,
OS storage maintenance and import of native `.vil` project files. Unknown or
unadvertised firmware features are rejected rather than sent guessed commands.
Physical browser access, LEDs, calibration, file throughput and persistence
still require hardware acceptance; simulated tests do not establish them.
See [validation and hardware checklist](VALIDATION.md) for the completed checks
and the remaining device tests.

Protocol references: existing Python modules in the repository's root
`addons/<id>/python/` directories,
[WebHID](https://developer.chrome.com/docs/capabilities/hid),
[WebUSB](https://developer.chrome.com/docs/capabilities/usb), and
[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).
XZ decoding uses [xz-decompress](https://github.com/httptoolkit/xz-decompress);
layout geometry uses [kle-serial](https://github.com/ijprest/kle-serial).
Their license notices and existing Vial/EC42 source notices apply.

## xwhatsit keyboards

The `addons/xwhatsit/` browser provider recognizes all 29 IBM Universal Vial
targets using UID **and** matrix dimensions. It uses the device’s live Vial layout
for Calibration, with signal numbers on keys, controls below and thresholds on
the right. Live sensors uses a chart above the matrix and follows pressed keys.

Utility 2.0.2+ firmware supports monitoring, its existing bootloader command and
EEPROM erase. XCAL v1 / utility 2.1.5 exposes six persistent calibration controls
with acknowledgement and independent readback. Unsupported sliders stay disabled.
Each save runs the existing calibration; there is no extra Recalibrate button.
The browser saves when a slider is released. Release every key before saving;
commands that fail are not retried. All USB operations use the selected Vial
transport queue; background sensor samples yield to typing and navigation.

No external program or layout table is needed. Signal charts stay in RAM only.
Close desktop Vi_al / Cap-Util before connecting. Browser WebHID access requires
a supported desktop Chromium browser and user permission. New board ports are
compile-verified; all physical variants still require their own hardware tests.
