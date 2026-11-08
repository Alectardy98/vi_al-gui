# IBM xwhatsit Vial targets

All 29 IBM board names have a `universal:vial` target. The 22 added Vial ports retain their original Universal wiring and default base keymaps. The older controller revisions and original sources are preserved in QMK Git history; these images are **only** for the Universal controller variant.

```sh
make xwhatsit/ibm/f50/universal:vial
```

Each port includes Vial remapping/macros and the shared live XCAL extension. New ports omit Tap Dance, combos, key overrides and QMK settings to keep AVR flash/EEPROM usage bounded; original mouse/media/solenoid configuration is retained. They use the existing Vial insecure convention. No bootloader image is included.

## New ports and compiled sizes

| Board | Layers | Flash / 28,672 B | Free flash | Static RAM / 2,560 B |
|---|---:|---:|---:|---:|
| `3101_3727_3278_87key` | 3 | 23666 | 5006 | 702 |
| `3277_66key` | 3 | 23522 | 5150 | 693 |
| `3277_78key` | 3 | 23568 | 5104 | 696 |
| `3277_split_66key` | 3 | 23570 | 5102 | 693 |
| `3278_3279_led_78key` | 3 | 23978 | 4694 | 741 |
| `4978` | 2 | 24020 | 4652 | 1036 |
| `5251` | 3 | 23620 | 5052 | 702 |
| `5251_hebrew` | 3 | 23674 | 4998 | 702 |
| `beamal_badpinout` | 1 | 22008 | 6664 | 1053 |
| `bigfoot_fxt_type_1` | 1 | 23114 | 5558 | 522 |
| `displaywriter` | 3 | 23662 | 5010 | 702 |
| `f104` | 3 | 23628 | 5044 | 528 |
| `f107` | 3 | 23640 | 5032 | 531 |
| `f50` | 3 | 23058 | 5614 | 435 |
| `f62` | 3 | 23174 | 5498 | 438 |
| `fext` | 1 | 22966 | 5706 | 531 |
| `fssk` | 1 | 22878 | 5794 | 522 |
| `fssk_v1_0b` | 1 | 22898 | 5774 | 522 |
| `fxt_type_2` | 1 | 22926 | 5746 | 522 |
| `test` | 1 | 23246 | 5426 | 1066 |
| `test2` | 1 | 22784 | 5888 | 702 |
| `xtant` | 1 | 22878 | 5794 | 522 |

The link-time EEPROM assertion also reserves at least 100 bytes beyond the keymap for Vial macro storage. Static RAM excludes stack/USB interrupt peaks; successful compilation is not physical acceptance.

## Layout and compatibility notes

- `4978`: FN2 maintenance keys moved directly to FN; transparent intermediate layer removed (2 EEPROM layers).
- `f104`: Empty FN3 consolidated into FN2 (3 EEPROM layers).
- `f107`: Empty FN2/FN3 consolidated; former FN4 maintenance keys are FN2 (3 EEPROM layers).
- `xtant`: Only the original base initializer exists; one remappable layer.
- `beamal_badpinout`, `test` and `test2` retain their original experimental wiring; they are not general-purpose BEAMal replacements.

- The imported `test2` layout had an invalid trailing comma; the Vial copy is valid JSON. Original IBM sources are preserved in Git history.

- New UIDs are unique and deterministic, shared by desktop/browser profiles. Existing seven ports keep their UIDs, layer counts and settings layout. Changing keyboard target or keymap defaults may require EEPROM reset; back up Vial settings before flashing another target.

- All 22 images compiled and passed HEX checksum/address and compiled-XZ-layout verification. No hardware was flashed for this porting task; each newly supported physical board still needs typing, calibration, solenoid/LED and recovery testing.

- Regression tools and firmware-image verification live on Vi_al’s `dev` branch under `util/dev/xwhatsit_firmware/`. Build logs and HEX images are packaged separately on the Desktop.

## Existing-target regression

All 14 original `vial` / `vial_alec` combinations also compile after these ports
(36 successful builds in total). No `vial_alec` keymaps were added for the new
boards. Existing target defaults and dynamic EEPROM layouts are retained.

The firmware folder was renamed from `xwhatsit/vial/` to `xwhatsit/ibm/`. Only build paths changed: Vial UIDs and EEPROM layouts are retained, and IDs must not be regenerated from the new paths.
