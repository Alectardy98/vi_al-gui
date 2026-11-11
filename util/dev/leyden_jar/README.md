# Leyden Jar development tools

These helpers are on `dev`; desktop builds do not need them. Run from the
repository root with the normal build virtual environment.

```sh
python -m pytest tests/leyden_jar
python util/dev/leyden_jar/update_profiles.py /path/to/vial-qmk
# Also synchronize a separate web checkout, if desired:
python util/dev/leyden_jar/update_profiles.py /path/to/vial-qmk --web /path/to/web-checkout
python util/dev/leyden_jar/hid_diagnostics.py --list
python util/dev/leyden_jar/hid_diagnostics.py --uid 394a0ea2c1df5e5d
```

The diagnostic CLI defaults to one bounded status read. `--levels` explicitly
requests one native DAC sweep; it can temporarily pause keyboard scanning.
`--capture-seconds 10 --output /path/to/run` records a finite signal capture.
It does not flash, erase EEPROM, change thresholds, or disable typing.

Close Vi_al, browser configurators and other HID tools before diagnostics.
The CLI refuses a running Vi_al process on Linux. Match the exact Vial UID;
VID/PID alone is never enough. Graph and protocol tests use simulated devices.
Keep large captures, screenshots, build environments and historical firmware
archives outside the checkout. They are evidence, not release source files.
