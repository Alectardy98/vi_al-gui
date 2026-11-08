# Optional live calibration for Vi_al

Board-local extension for the `xwhatsit/vial/*/universal` targets. See `PORTS.md` for the complete IBM port/build table. Existing
sensing GPIO, DAC format and sampling assembly are retained. The original
startup calibration still runs; saved tuning parameters are loaded first.
`matrix.c` now clears assignment masks before every calibration, so runtime
recalibration cannot retain assignments from earlier groups.

## Builds

From the QMK repository root, use the board's normal command, for example:

```sh
make xwhatsit/vial/fat/universal:vial_alec
make xwhatsit/vial/fat/universal:vial
```

Both requested keymaps enable the extension through each controller folder’s `rules.mk`. Other
keymaps retain the original constant calibration path. For the original utility
command set and smaller image:

```sh
make xwhatsit/vial/fat/universal:vial_alec XWHATSIT_RUNTIME_CALIBRATION=no
```

All seven boards × both keymaps are build-checked with the installed AVR
compiler. HEX files are application images, not UF2. The connected FAT uses its
existing Caterina bootloader. Application records must stay below `0x7000`;
the build reserves the existing 4096-byte bootloader. Do not flash another
board's image. Some targets have very little spare flash; check size on every
compiler/build change. Runtime settings cost eight additional SRAM bytes.

## Storage and recovery

The eight-byte record uses QMK's existing adjacent `EECONFIG_KEYBOARD` and
`EECONFIG_USER` words (current addresses 15–22). These words were unused by the
supported Vial keymaps. Compile-time assertions reject relocated/nonadjacent
words or added keyboard/user data blocks. Vial keymap and macro addresses stay
unchanged; no larger EEPROM allocation is made.

| Byte | Encoding |
|---|---|
| 0 | `0xA7` format/commit marker |
| 1 | DAC settling delay, 1–32 µs |
| 2 | Original sampler step argument, 1–32 |
| 3 | Low/high nibble: log2 startup/per-key averaging, each 0–5 |
| 4 | Active calibration groups, 1–compiled capacity |
| 5–6 | Threshold margin, little-endian, 0–DAC maximum |
| 7 | CRC-8 polynomial `0x07` of bytes 0–6 |

Save invalidates byte 0, updates bytes 1–7, then commits byte 0 last. Invalid,
missing or torn records load compiled defaults on startup. EEPROM update calls
avoid programming unchanged bytes; Vi_al debounces slider movement. Calibration
thresholds are recomputed in RAM, not persisted per key.

Restore calibration defaults (`0x33`) preserves all other EEPROM bytes. It
intentionally works even if poor tuning reports phantom held keys: physically
release every key first. Full erase (`0x18`) clears **all** bytes through `E2END`,
including the last byte; reconnect afterward to initialize defaults.

Rollback: enter Caterina using the unchanged utility boot command, flash the
archived original board/keymap HEX, and optionally restore the backed-up EEPROM
through the bootloader. Older firmware ignores the new record and uses its
compiled sensing constants. The reserved record does not relocate Vial addresses within this source version.
QMK/Vial can nevertheless initialize defaults when its EEPROM format or Vial
build marker changes. The connected FAT originally used marker `0xFEE5`, while
this source uses `0xFEE3`: first boot therefore initialized current defaults, as
authorized. Its complete pre-update flash/EEPROM backup is retained. Restore
the original application and original EEPROM together for exact old settings;
do not assume a raw EEPROM from another QMK version is format compatible. Never
replace bootloader/fuses to install this feature.

## Utility protocol

Framing remains a 32-byte raw HID report beginning `55 AA`; byte 2 is opcode.
Host writes include HID report ID zero. Replies use byte 2 `22` for success,
`23` for rejected request, or `24` for explicitly held keys. No transaction ID
exists in the original framing: exactly one host operation owns the handle.
Do not replay an uncertain save timeout.

Version is **2.1.5**. The old essential version, matrix, threshold, details,
signal, boot and erase operations remain. To save AVR space, extension builds
omit legacy filename and raw shift-register/DAC engineering commands. Therefore
old Cap-Util's complete UI is not supported by extension firmware. Its existing
boot opcode remains available. Build with the extension disabled for the full
legacy command set.

| Opcode | Operation |
|---|---|
| `30` | XCAL descriptor: bytes 3–6 `XCAL`, 7 schema 1, 8 compiled group capacity, 9 auto/debug flags, 10–11 DAC maximum LE, 12–19 default record |
| `31` | Read current record in bytes 3–10 |
| `32` | Validate record in request bytes 3–10, reject held keys, apply, recalibrate, persist, echo current record |
| `33` | Restore compiled defaults, recalibrate, persist and echo record |
| `34` | Reject held keys, recalibrate, echo record; no EEPROM save |

Vi_al checks descriptor, UID/dimensions, validation, acknowledgement and a
separate readback. Calibration runs synchronously in firmware, so scanning can
pause while it measures; the GUI worker keeps the window responsive. Release
all keys and allow completion. Startup/per-key averaging is bounded to 32 to
limit work. No GPIO or electrical redesign is included.

`CAPSENSE_CAL_ENABLED` and `CAPSENSE_CAL_DEBUG` remain compile-time capabilities;
the maximum bin array size remains compiled. Do not present unsupported live
switches. Existing protocol 2.0.2+ can use monitoring in the add-on without
flashing; only adjustable/persistent parameters require the extension.

## Tests and acceptance

```sh
python3 /path/to/vi_al-gui/util/dev/xwhatsit_firmware/run_native.py /path/to/vial-qmk
```

The test tools are maintained on Vi_al’s `dev` branch, not required to build QMK. This command runs actual settings/protocol C and the actual calibration function body with
simulated GPIO/EEPROM under AddressSanitizer and UndefinedBehaviorSanitizer.
Covers invalid records, interrupted commits, held-key rejection, assignment
reset, signal request bounds, defaults, complete erase and boot entry.

Hardware evidence and the build/memory table accompany the release. Hardware
signal sweeps, persistence/reflash and bootloader preservation are distinct from
human press/release acceptance. Test real keys, typing, modifiers, threshold
changes and replug behavior before declaring all mechanical layouts accepted.
Exact electrical timing/noise tolerances are not established by compilation or
simulated GPIO. Vendor-document lookup was unavailable in this environment;
this change retains the existing electrical routines rather than assuming new
hardware timing requirements.
