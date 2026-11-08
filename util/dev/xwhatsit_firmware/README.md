# xwhatsit firmware validation

These tools operate on a separate QMK checkout and never open a keyboard or flash hardware.

```sh
python util/dev/xwhatsit_firmware/run_native.py /path/to/vial-qmk
python util/dev/xwhatsit_firmware/build_ports.py /path/to/vial-qmk --output /tmp/xwhatsit-builds
python util/dev/xwhatsit_firmware/verify_ports.py /path/to/vial-qmk --output /tmp/xwhatsit-verified.json
```

The native tests compile the actual settings/protocol/calibration C with simulated GPIO/EEPROM and sanitizers. The build runner compiles all new ports from the adjacent developer-only `ports.json`. The verifier checks ELF usage, Intel HEX checksums, the 0x7000 boot boundary, and embedded Vial layouts. Compiling does not establish physical wiring or typing acceptance.

The QMK `vial/` directory needs only keyboard folders. Each controller folder owns its calibration build rule and user README. `ports.json` and `PORTS.md` here contain developer metadata and cross-board notes; QMK never reads them.

`XCAL.md` documents the shared runtime settings record/protocol; `PORTS.md` records the port history and layer/memory tradeoffs.

## Offline visual review

No connected keyboard is used. Prepare cases with compiled default keycodes:

```sh
python util/dev/xwhatsit_firmware/review_layouts.py /path/to/vial-qmk --output /tmp/layout-review
python util/dev/xwhatsit_firmware/analyze_layouts.py /tmp/layout-review
python util/dev/xwhatsit_firmware/fetch_layout_photos.py /tmp/layout-review
```

Launch a frozen **core** Vi_al build with `VI_AL_SMOKE_TEST=1`,
`VI_AL_LAYOUT_REVIEW=/tmp/layout-review`, an isolated `VI_AL_ADDON_DIR`,
`VI_AL_TEST_BRIDGE` pointing to `capture_layouts.py`, and
`QT_QPA_PLATFORM=offscreen`. This uses the built-in dummy JSON loader and denies
USB access. It captures all actual Qt layouts and exits. Use the core build: the
current bundled MY-2K add-on assumes real-device mixin attributes when a dummy
keyboard loads. That is a separate add-on compatibility issue.

After captures, run `layout_gallery.py /tmp/layout-review` to make the HTML
gallery, independent QMK diagrams and contact sheets. The photo/gallery tools
need Pillow. Original source photo links are pinned to a historical QMK commit;
`--reference-revision` can select another archive. Downloads can be missing or
placeholder images. Photos of a PCB or a modified specimen are not evidence of
an unmodified keyboard's keycap layout. A source-geometry match is not physical
acceptance or electrical matrix verification.
