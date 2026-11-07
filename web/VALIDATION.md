# Web preview validation

Validated on the `web` branch with Node 26.8.1 and local headless Chrome.
The GitHub workflow uses Node 24 and Playwright Chromium. CI execution and
GitHub Pages publication have not yet been verified remotely.

| Check | Result |
|---|---|
| `npm test` | 24 passed |
| `npm run test:browser` | 14 passed |
| `npm run build` | Passed; static output in `web/dist/` |
| `npm run test:production` | Passed under `/vi_al-gui/`, including all three providers; no external requests or browser errors |
| Core build with `addons/` absent | Passed in an isolated copy |
| Existing desktop regression suite | 170 tests and 365 subtests passed |
| Desktop add-on ZIP boundary | All three packages validated; browser sources excluded |

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
