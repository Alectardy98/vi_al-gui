# Testing Vi_al

The optional regression suite is grouped by the code it protects:

```text
tests/core/              Add-on installation and page ownership
tests/ec_42/             EC42 records, actuation and navigation
tests/alienware_aw768/   Lighting packets, readback and USB pairing
tests/my2k/              GIFs, OLED, gaming and persistent-settings codecs
src/main/python/test/   Upstream Vial core tests
```

Run from the repository root with the development environment active:

```sh
python -m pip install -r test-requirements.txt
QT_QPA_PLATFORM=offscreen python -m pytest tests src/main/python/test -q
```

On Windows set `QT_QPA_PLATFORM=offscreen` in your terminal environment first.
Tests build add-on ZIPs into a temporary directory, install them into a temporary
profile, and use simulated devices. They need no firmware repositories, ROMs,
external C harnesses or connected keyboards. GUI preference files are isolated.
No tests are required to build or run the application.

For core-only testing without any optional add-on sources:

```sh
VI_AL_TEST_ADDONS=0 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/main/python \
  python -m pytest src/main/python/test tests/core -q
```

After building core and bundled packages, run
`python util/packaging/smoke_packages.py`. It checks the actual frozen application,
icon, image codecs and bundled libraries while blocking hardware access. CI runs
these checks on the native build platforms.
