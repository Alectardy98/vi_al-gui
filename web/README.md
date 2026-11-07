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
web/src/                    Browser UI, serialized WebHID, Vial core
web/src/data/               Checked-in versioned keycode/font/encoding data
addons/<id>/web/provider.js  Add-on ID, identity matching and pages
addons/<id>/web/protocol.js  Browser implementation of that add-on's protocol
web/tests/                  Protocol vectors and simulated browser tests
```

Every browser add-on exports `{id, name, supports(keyboard), pages}`. A page is
`{id, title, render(container, context)}`. Use `context.run()` for user actions,
`context.read()` for polling, and stop work when `context.signal` is aborted.
These share a connection-wide operation queue, including across page changes.
`keyboard.request()` uses the single serialized 32-byte raw HID transport.
Timeouts invalidate the connection; mutation requests are never retried.

Browser providers are bundled at build time using Vite's local module discovery.
The core builds if `addons/` is absent. Desktop Python add-on ZIPs cannot execute
in a browser. The desktop ZIP packager excludes `web/`, preserving its existing
package format. Existing Python providers and firmware are unchanged.

## Current controls and limits

| Area | Browser implementation |
|---|---|
| Vial core | Actual compressed definition, layout options, layers, keycodes, encoders, keymap export, macros, Tap Dance, combos, key overrides, alternate repeat, QMK settings, generic lighting, unlock/lock and matrix tester |
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

Protocol references: existing Python modules beside each provider,
[WebHID](https://developer.chrome.com/docs/capabilities/hid),
[WebUSB](https://developer.chrome.com/docs/capabilities/usb), and
[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).
XZ decoding uses [xz-decompress](https://github.com/httptoolkit/xz-decompress);
layout geometry uses [kle-serial](https://github.com/ijprest/kle-serial).
Their license notices and existing Vial/EC42 source notices apply.
