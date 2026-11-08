# xwhatsit capacitive keyboards

Install the ZIP once through **Add-ons → Install from ZIP…**, then restart Vi_al.
The bundled edition installs it automatically when it is not already installed.

- **Calibration:** the actual Vial layout/options with measured signal numbers
  on the keys, controls below, and a position/threshold table on the right.
  Six tuning sliders remain available. Changes save after 500 ms without further edits.
- **Live Sensors:** the same stacked layout as EC42/Pro X: signal chart above
  the matrix, each using about half the available space. The graph follows
  the selected/pressed key, showing released noise and its last held reading. The 10 Hz host view keeps only a
  short RAM graph; it does not write logs or record every matrix scan.
- **General:** enter the existing bootloader, or explicitly erase all EEPROM.

All 29 IBM `xwhatsit/vial` Universal targets are recognized by Vial UID and matrix dimensions. The original seven identities remain unchanged; each of the 22 new targets has a unique UID. New ports provide a `vial` keymap; they do not add `vial_alec` keymaps.
Geometry and layout options come from the connected keyboard, not bundled pictures.

## Firmware compatibility

Existing utility protocol 2.0.2+ supports read-only signals/thresholds and its
existing boot/erase commands. Unsupported sliders stay disabled. No automatic
firmware update or undocumented GPIO command is sent.

Optional utility protocol 2.1.5 adds the capability-checked **XCAL v1** extension.
The matching firmware is in the QMK repository’s `keyboards/xwhatsit` directory.
It retains automatic startup calibration, loading saved parameters first.
Compile-time calibration/debug switches and maximum group capacity remain build
capabilities; they are not exposed as fake live settings.

| Control | Range | Meaning |
|---|---|---|
| DAC settling time | 1–32 µs | Wait after setting the sensing threshold |
| Sample timing | 1–32 steps | Sampling position in the original sensing routine |
| Startup / per-key averaging | 1, 2, 4, 8, 16, 32 | Measurement repetitions during calibration |
| Calibration groups | 1–compiled maximum | Number of shared released-signal thresholds |
| Threshold margin | 0–device DAC maximum | Distance from released signal to activation threshold |

These are tuning limits, not a guarantee that every extreme works on every PCB.
Release all keys while applying/recalibrating. Calibration briefly interrupts
keyboard scanning; it runs off the GUI thread so the window remains responsive.
Only an explicit “keys held” reply is retried. A timed-out mutation is not replayed.

**Restore calibration defaults** resets only the eight-byte calibration record
and recalibrates, preserving keymaps. It can recover from settings that report
false held keys; physically release every key before using it.
**Erase all EEPROM** removes keymaps/macros and calibration overrides. Reconnect to
initialize defaults. Calibration runs again at each startup.

XCAL firmware omits the legacy filename/raw GPIO/DAC engineering commands to fit
small AVR images. The old Cap-Util’s complete UI is not compatible with this
reduced command set; boot entry is retained. Vi_al monitoring works with both
old firmware and the extension. No new runtime dependency is required.

Settings use existing fixed QMK keyboard/user EEPROM bytes with CRC and a final
commit marker. Vial keymap/macro addresses are unchanged. A torn record falls
back to compiled calibration defaults at next startup. See the board firmware’s
`README_CALIBRATION.md` for protocol, builds and rollback.

## Display sampling

Initial values load promptly during idle time using short single-value reads,
with checks of keyboard activity between measurements and brief yields to the
device's normal loop. Background loading pauses while keys are held and for
350 ms after release. The followed key remains live; other values are cached
and refreshed in rotation. USB polling and normal matrix scan rates are not
capped by the GUI. Active signal measurement still has diagnostic overhead.

Where supported and already unlocked, activity checks use Vial's cached matrix
state, rather than forcing extra capacitive scans. Legacy firmware keeps the
original utility fallback. The add-on does not unlock a board automatically.

The old Cap-Util requests 14 values at once. On the FAT that request measured
about 69 ms; a single-value request measured about 9 ms. This reader avoids
those long measurement batches. Minimum/maximum overlays show measured
extremes in the visible graph history. No unsupported Rapid Trigger/actuation
controls are added. This UI revision changes no EEPROM layout or save protocol.

Calibration descriptions are spaced into separate sections. Slider changes
already recalibrate when saved, so the only calibration action button is the
centered **Restore calibration defaults** button.
