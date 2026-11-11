# Web preview validation

Validated locally on 2026-11-11 with Node 26.8.1 and headless Chrome.
The GitHub workflow uses Node 24 and Playwright Chromium. This update is
prepared on the local `web` branch; publishing requires a push/deployment.

| Check | Result |
|---|---|
| `npm test` | 49 passed |
| Browser regression suite | 25 passed, plus the new sixteen-group layout test |
| `npm run build` | Passed; static output in `web/dist/` |
| `npm run test:production` | Passed below `/vi_al-gui/`, exercising all five providers with no external requests or page errors |
| Desktop regression suite on `dev` | 280 tests and 365 subtests passed; 55 targeted Leyden Jar tests passed after descriptor additions |
| Desktop bundles | Linux and Windows startup with all five add-ons passed |
| Windows installer | Install, 188 payload files, startup and safe uninstall passed under Wine |

Earlier core-only/standalone website and layout checks are recorded below.

Browser-only source, assets, licenses, fixtures, tests and configuration now
live under `web/`, including `web/addons/`. The GitHub Pages workflow remains
in `.github/workflows/`. Desktop packaging uses its original implementation;
it no longer needs an exclusion for browser files. Website build and runtime
data do not import files from the desktop tree.
The moved desktop-package integration test passed after this reorganization.

Protocol vectors come from the existing Python codecs and captured Dell packet
fixtures. Tests cover CRC corruption, HID report IDs/serialization, stalled
sends, disconnects, rejected transfers, settings acknowledgements/readback,
macro and dynamic-action encoding, and calibration safety boundaries. A failed
backup or changed proposal prevents activation; failed active verification
cancels volatile calibration without sending SAVE. GIF conversion is exercised
in Chrome with two actual source frames and preserved frame delays.

Browser tests use simulated USB peers. They prove frontend behavior against
those peers, not that a physical device or its firmware accepts every operation.
No firmware was built or flashed and no connected keyboard settings were changed
while implementing or running these tests.

### Zenithal layout and keycode picker

`IMG_8962.jpg` exposed a reproducible browser geometry defect. The packaged
`kle-serial` parser did not reset its coordinate cursor when `rx`/`ry` changed,
even though Vial uses those cluster origins for unrotated keys too. With the
Rev3 definition, the spacebar appeared at row 21.25 and bottom numpad at row
26.25 instead of row 4. Their off-screen placement also stretched the keymap
card and pushed the keycode picker far below the visible keyboard.

The browser now corrects the cluster cursor, places each selected layout group
relative to option 0 as desktop Vial does, includes secondary key rectangles and
rotated bounds, and fits wide layouts within the available space. Very narrow
views retain horizontal scrolling instead of shrinking keys indefinitely. The
Layout page previews changes without writing them until Apply.

Independent fixtures generated from the desktop Python/Qt renderer cover 58
placements across Zenithal Rev1, Rev3/Pico and the DC2014 custom definition.
Tests compare source coordinates and displayed key positions, including every
individual option and a combined-options case. Browser tests confirm the full
spacebar/numpad are visible, keycode controls are no longer pushed down by the
bad geometry, ISO Enter retains its shape, and layout persistence uses the same
acknowledgement/readback commands.

The picker now uses the desktop category metadata and versioned wire encodings,
including aliases and modifier/layer-tap masks. The 120-result cutoff is removed.
Tests cover all tabs, capability filtering, v5/v6 encodings, custom presentation
order versus immutable numeric identity, all 39 User entries in the Alec
definition, descriptions, and assignment/readback. Browsing, searching and
choosing a wrapper before its inner key do not issue settings writes.

These tests use real source definitions and simulated device replies. The
remote Zenithal PCB was not connected for physical acceptance; no keyboard
firmware or EEPROM was changed.

### Pro X connection follow-up

The reported `get_next_output ... error code 7` occurred while a desktop Vi_al
process still held `/dev/hidraw21`. That process was closed. A read-only probe
then retrieved a valid 1,156-byte XZ definition from the connected Pro X,
SHA256 `df8d78c0c74350b01e1459cd633f5f711445caef9118c8b7a3fac4f82b3e9a43`.
The same JavaScript Vial loader completed against the real device through a
diagnostic hidraw adapter: Vial 6, UID `4d2d00bcadf8b927`, 5×15 matrix, four
layers. The JavaScript EC42 client identified `A98-prox-UF2-2.9g` and read its
status and actuation. No settings, calibration-control or persistence command
was sent. The static definition is now a browser regression fixture.

These observations establish that the device definition and decoder are
compatible. Competing desktop traffic is a plausible explanation for the
original corrupt stream; the original failing packets were not captured, so
this does not establish that cause conclusively. A physical connection through
the browser's own WebHID picker still needs user confirmation. Invalid streams
now produce an actionable close-other-configurators message and abort before
any settings write; no decompression checks are bypassed and no write is retried.

## Physical acceptance

Use desktop Chrome or Edge. Close other keyboard configurators first. Keep
existing desktop releases and settings backups available for comparison.

1. Connect each actual board using the browser picker. Check its displayed
   identity, physical layout/options, custom keycodes and layer count.
2. Change one spare key, read it back, test the physical key, then restore it.
   Repeat an encoder assignment if present. Check macros and layout options.
3. EC42: compare stored actuation with desktop Vi_al, test global and per-key
   changes, and verify live sensor tracking. Restore settings. Exercise manual
   calibration separately with the recovery file saved, released-key checks,
   review and persistent readback; a simulated test is not physical calibration.
4. AW768: explicitly choose the original lighting PCB, compare groups, effects
   and Macro colors, save, reconnect and verify persistence. Macro readback is
   limited on legacy controllers; use physical observation for that zone.
5. MY-2K: compare RGB, Lock Lights, touch, sleep, OLED and game bindings with the
   desktop app. Check persistence and restore test settings. Test a spare GIF
   slot through the separate WebUSB grant: upload, fresh preview, playback and
   clear. Check both USB performance modes after reconnecting. Do not change
   firmware merely to test this website.
6. Disconnect during a nonessential operation. The site must stop and require
   reconnection after an uncertain transfer, never silently repeat a write.
   Inspect slot/settings state after reconnecting before another mutation.

Linux USB permissions and Windows binding of the vendor WebUSB interface may
still require OS configuration. Browser grants cannot override OS access rules.
Safari and Firefox do not provide the WebHID path used here. Filesystem downloads
and calibration backup pickers remain subject to browser permissions.

## Scope differences from desktop

- Browser providers are build-time JavaScript modules. Desktop Python add-on
  ZIPs are not browser-installable packages.
- There is no UF2 flashing, OS mount/eject integration or native `.vil` import.
- MY-2K file access and AW768 native lighting require separate device grants.
  With multiple identical boards, select the matching device explicitly; browser
  APIs do not expose enough topology to independently prove the association.
- Clock-on-connect requires this site to be open and explicitly opted in.
- Lock Lights and touch changes use explicit Apply actions in this web preview.
- OLED font rendering uses available browser fonts; an existing saved bitmap is
  preserved until its message/font/size is edited. Typing uses the firmware's
  fixed glyphs, with no unsupported independent font control.

The unmodified desktop app remains the fallback for unsupported operations.

## xwhatsit add-on port

- 39 Node tests passed, including XCAL records/CRC/ranges, readback, held-key
  rejection, legacy firmware, 16-row/wide matrices and no mutation retries.
- 20 browser tests passed, including F50's actual compiled XZ definition and
  50-key layout, calibration save/defaults, automatic sensor following and
  capability-disabled legacy sliders. USB is simulated for these tests.
- Production build passed under a GitHub Pages-style subpath, loading all four
  bundled providers without external requests or page errors.
- The 29 profiles match desktop add-on 1.0.4. The original seven identities are
  retained (some historical UIDs overlap); new targets have distinct UIDs.
- Physical WebHID acceptance for each board is still required. This port neither
  flashes firmware nor changes bootloaders. Close desktop configurators before
  browser access.

## Leyden Jar port · 2026-11-11

- Native protocol tests cover exact UID/matrix gates, signed offsets, separate
  acknowledgement/readback, both polarities, reversed and unused mappings,
  temporary legacy firmware, split 1.x, direct switches and four-row expanded
  scanners. Invalid/short/rejected replies do not retry configuration writes.
- Browser tests exercise live values, group selection, explicit Apply, restore
  defaults, automatic following, coordinate labels, controller matrix views,
  polling cancellation and output enable/readback. Simulated peers also cover
  the 3178 digital switch and current 4×20 descriptor.
- No real keyboard configuration was changed by these tests. USB grants, actual
  signals, persistence after restart and physical key behaviour require manual
  browser acceptance with the corresponding keyboard connected.
