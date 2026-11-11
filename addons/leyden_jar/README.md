# Leyden Jar add-on · 1.1.3

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
- **Calibration:** keyboard geometry from the device's Vial definition, automatically updated signal
  numbers on keys, group membership colouring, startup reference/trigger/live-range
  table showing every group without an internal vertical scrollbar, and
  click-a-key group selection. A linked slider and number field edit
  the group trigger. Firmware 0.10.0 adds **Apply and save**, which stores the
  offset from the startup reference in QMK EEPROM and checks acknowledgement
  and readback. **Restore calibration defaults** clears only these overrides;
  keymaps and macros are preserved. Editing alone sends no configuration
  update. Live reads can be paused. Layout variants follow Vi_al's Layout tab.
  Older native firmware keeps threshold edits in RAM until restart; the UI
  identifies that limitation and disables the unsupported defaults action.
- **Live Sensors:** keyboard, QMK matrix and physical-controller matrix views;
  keyboard keys show their QMK row,column above the live signal reading;
  automatic pressed-key following, signal graph, per-pad minimum/maximum, three-sample stable low/high estimates and
  threshold-distance indication. Hover a key or matrix cell for bin/margin data. Graph history is bounded to 160 samples in RAM, never logged.

Vi_al's existing **Matrix Tester** remains available for keypress testing.

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
ports. The profile exporter lives on the `dev` branch at
`util/dev/leyden_jar/update_profiles.py`; it is not needed to build or run Vi_al.

Unlike the standalone utility, merely selecting the device does **not** disable
keyboard output. The explicit output button provides that capability. Threshold
editing does not automatically erase or persist EEPROM.

## Timing and ownership

One bounded worker owns the selected Vial HID handle per operation. Navigation
that would replace/close that handle is deferred until the operation finishes;
regular discovery is paused during exchanges. There is no independent USB handle
or competing background scanner. Writes are not automatically retried. Threshold readback verifies the firmware's
logical setting; it is not an independent measurement of DAC output voltage. The new
IBM firmware rejects a threshold command if its DAC write returns an I2C error;
older native firmware may acknowledge that error without reporting it.

Native full-level acquisition changes the DAC temporarily. Most targets scan
150 values (350–499); the 3178 uses 550 values (350–899) to capture its higher
released baselines. Each value adds 100 µs settling plus I2C/scan time. This is a native
**blocking keyboard operation**, even though the GUI worker stays responsive.
Calibration and Live Sensors request one sweep after the previous sample and a
400 ms interval. Calibration can pause the sweeps while retaining press
highlighting. Leave either live page or pause Calibration for normal typing.
Keypress-only pages use completed snapshot requests with a 70 ms interval.
These host intervals do not change the controller's ordinary scan cadence.

## Validation and limits

Host tests cover native packet encoding, readback, stale/short/rejected replies,
identity gating, split version, polarity, unused pads, page rendering, worker
lifecycle and stopping polling. The new IBM firmware targets use the existing
native peripheral implementation. Physical wiring, threshold margins and real
keyboard latency remain to be tested on each installed controller.

## Persistent calibration

Firmware 0.10.0 keeps automatic released-key calibration on every startup. Each
saved group offset is added to its newly measured reference, rather than
reusing an absolute threshold. Model F offsets must be positive; Beamspring
offsets must be negative. The protocol advertises its extension before the GUI
offers saving. Native 1.x split firmware retains its existing behavior unless
it implements a compatible negotiated extension.

Preferences use a versioned, checksummed 48-byte keyboard EEPROM record with a
compiled configuration signature. Corrupt/incompatible records use firmware
defaults. QMK EEPROM clear resets these preferences too. Ordinary reads and
slider edits never write EEPROM; Apply writes only the chosen group's offset.
Repeated saves of the same preference skip the EEPROM update. QMK wear-levelled
storage supplies the underlying flash writes; readback verifies the logical
record, while persistence must also be tested across a hardware restart.

Sorted groups may contain different keys after another startup calibration;
their overrides follow group IDs. Explicit custom groups, such as FAT
`vial_alec` Group 1 for QMK 5,2, remain tied to their configured controller pad.
Restore defaults does not recalibrate or restart, so a held key cannot become
a new released-key reference. Releasing every key is still required when
using **Restart and recalibrate**.

For the requested Rev 3 Model F AT, build:

```sh
make leyden_jar/ibm/fat:vial_alec
```

The AVR xwhatsit firmware and this RP2040 firmware are different targets. Use the
preserved matching Leyden Jar UF2 to roll back, not an AVR HEX.

## Using Calibration

1. Open the page: readings start automatically. Green keys are pressed; blue
   keys share the selected sensitivity group; amber is within three counts of
   the trigger. The displayed refresh count shows that sampling is running.
2. Click a key, or click a group row. The page shows which group is selected,
   the latest signal, its trigger, and how many keys share that setting.
3. Adjust the trigger slider or number. On Model F, lower is more sensitive;
   on Beamspring, higher is more sensitive. The page shows the correct direction.
4. Click **Apply and save** on compatible firmware, or **Apply to this group**
   on older firmware. It affects all keys in that group, not just the clicked
   key. The page confirms readback and states whether it saved the offset.
5. **Restart and recalibrate** measures new references and reapplies saved
   offsets. Release every key first. **Restore calibration defaults** clears
   the saved offsets without restarting. **Live readings on/paused** controls
   only measurements.

**Rest** is a fixed startup reference, not a live signal. **Live** shows the
current minimum–maximum reading across the group. These controls adjust an
electrical trigger, not a physical distance or percentage.

Version 1.1.0 adds support for the persistent-calibration extension in board
firmware 0.10.0. Export your Vial settings before upgrading the firmware:
four layers and expanded Vial feature capacities change its EEPROM layout.

## 3178 blue switch

Firmware 0.10.1 can advertise one direct switch in a ninth logical row. The
3178 retains its 9×13 Vial layout, eight capacitive rows and separate blue switch
at `(8,12)`, wired from GPIO27/COL17/J2.30 to GND. The add-on identifies it as a
digital switch and does not invent a DAC signal or calibration threshold. Other
eight-row targets and older native protocol versions retain their existing
behavior. Updating the add-on does not change keyboard firmware or settings.
## Expanded 3276 matrix

Native protocol 0.10.2 can advertise a four-row, twenty-column scanner. The
add-on validates that descriptor and reads four signal values per column.
The current modified Rev 3 firmware drives its four extra columns through
GPIO4–7 after the documented U6 hardware changes; the descriptor's old 31/32
markers are retained for wire compatibility and do not describe current wiring.
Ordinary eight-row controllers and the 3178 direct switch keep their native
formats. The add-on reads mappings from firmware rather than guessing wiring.

Development tests, captures and profile-generation tools are maintained on
`dev`. Browser support is maintained on `web` under `web/addons/leyden_jar/`;
Python add-on ZIPs remain desktop packages.
