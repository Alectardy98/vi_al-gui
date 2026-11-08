# xwhatsit firmware validation

These tools operate on a separate QMK checkout and never open a keyboard or flash hardware.

```sh
python util/dev/xwhatsit_firmware/run_native.py /path/to/vial-qmk
python util/dev/xwhatsit_firmware/build_ports.py /path/to/vial-qmk --output /tmp/xwhatsit-builds
python util/dev/xwhatsit_firmware/verify_ports.py /path/to/vial-qmk --output /tmp/xwhatsit-verified.json
```

The native tests compile the actual settings/protocol/calibration C with simulated GPIO/EEPROM and sanitizers. The build runner compiles all new ports from `keyboards/xwhatsit/vial/ports.json`. The verifier checks ELF usage, Intel HEX checksums, the 0x7000 boot boundary, and embedded Vial layouts. Compiling does not establish physical wiring or typing acceptance.
