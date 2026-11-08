# Leyden Jar add-on · 1.0.0

Native Leyden Jar controller diagnostics inside Vi_al. Install this ZIP through
**Add-ons → Install from ZIP…**, restart, and select the controller. No extra
Python package or diagnostic utility is required by the compiled app. Installing
it does not flash firmware or write keyboard settings.

## Pages

- **General:** protocol/version, Vial UID, matrix sizes, Model F/Beamspring type,
  native/xwhatsit/wcass mapping, calibration bins, split side when reported,
  explicit keyboard-output enable/disable, reboot, bootloader and EEPROM clear.
  Reboot, BOOT and clear require confirmation and disconnect without an ACK;
  the UI reports “command sent,” not a verified restart.
- **Calibration:** keyboard geometry from the device's Vial definition, signal
  numbers on keys, bin reference/threshold/population table, native 10-bit DAC
  threshold editing with acknowledgement and RAM readback, and explicit level sweep.
  Layout variants follow Vi_al's Layout tab. Thresholds are **session-only** in
  native firmware; restart restores automatic calibration. No persistent override
  or AVR timing setting is invented.
- **Live Sensors:** keyboard, QMK matrix and physical-controller matrix views;
  automatic pressed-key following, signal graph, per-pad minimum/maximum, three-sample stable low/high estimates and
  threshold-distance indication. Hover a key or matrix cell for bin/margin data. Graph history is bounded to 160 samples in RAM, never logged.
- **Keypress Monitor:** the same three views, without continuous signal sweeps.
  Vi_al's existing Matrix Tester remains available.

## Native-tool coverage

`Leyden_Jar_Diagnostic_Tool/src/LeydenJarProtocol.cpp` and the board-local QMK
`leyden_jar/util_protocol.c` define the packet format. The add-on implements all
native actions: details, mapping, bins, DAC references/thresholds, output state,
logical/physical snapshots, full level sweep, reboot, EEPROM clear and BOOT.
Split side is queried only for protocol 1.x. Core Vi_al supplies USB discovery,
VIA/Vial negotiation, compressed-definition decoding and Layout controls.

Detection requires a known Leyden Jar Vial UID **and** matching logical dimensions,
then validates native protocol 0.9.1/1.x and returned mappings before diagnostics.
It never sends capacitive commands to a keyboard based only on a shared VID/PID.
`profiles.json` covers the native repository definitions and new original-IBM
ports. Regenerate it after adding native firmware targets with:

```sh
python3 util/packaging/update_leyden_profiles.py /path/to/vial-qmk
```

Unlike the standalone utility, merely selecting the device does **not** disable
keyboard output. The explicit output button provides that capability. Threshold
editing does not automatically erase or persist EEPROM.

## Timing and ownership

One bounded worker owns the selected Vial HID handle per operation. Navigation
that would replace/close that handle is deferred until the operation finishes;
regular discovery is paused during exchanges. There is no independent USB handle
or competing background scanner. Writes are not automatically retried. Threshold readback verifies the firmware's
RAM setting; it is not an independent measurement of DAC output voltage. The new
IBM firmware rejects a threshold command if its DAC write returns an I2C error;
older native firmware may acknowledge that error without reporting it.

Native full-level acquisition changes the DAC temporarily and scans 150 values
(350–499), with 100 µs settling per value plus I2C/scan time. This is a native
**blocking keyboard operation**, even though the GUI worker stays responsive.
Live Sensors requests one sweep after the previous sample and a 400 ms interval;
other pages do not continuously sweep. Leave Live Sensors for normal typing.
Keypress-only pages use completed snapshot requests with a 70 ms interval.
These host intervals do not change the controller's ordinary scan cadence.

## Validation and limits

Host tests cover native packet encoding, readback, stale/short/rejected replies,
identity gating, split version, polarity, unused pads, page rendering, worker
lifecycle and stopping polling. The new IBM firmware targets use the existing
native peripheral implementation. Physical wiring, threshold margins and real
keyboard latency remain to be tested on each installed controller.

For the requested Rev 3 Model F AT, build:

```sh
make leyden_jar/ibm/fat:vial_alec
```

The AVR xwhatsit firmware and this RP2040 firmware are different targets. Use the
preserved matching Leyden Jar UF2 to roll back, not an AVR HEX.
