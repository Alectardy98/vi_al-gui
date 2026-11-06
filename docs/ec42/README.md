# EC42 add-on

The EC42 controls are a GUI port of **qmk-ec-util / EC42 v2.9**: calibration,
per-key actuation, Rapid Trigger and live sensor views. They use the selected
keyboard's existing HID connection and do not change firmware or bootloaders.

Implementation lives in `addons/ec_42/python/vi_al_addons/ec_42/`. Supported board
identities and record layouts are defined in `protocol.py`; `provider.py` exposes
the three pages through the common add-on API.

Original source provenance is recorded in [PROVENANCE.json](PROVENANCE.json).
The upstream GPL-3.0-or-later terms are retained in [COPYING](COPYING) and in the
source notices. Tests are documented in [TESTING.md](../TESTING.md).
