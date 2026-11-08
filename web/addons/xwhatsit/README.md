# xwhatsit browser add-on

- `provider.js`: Calibration, Live sensors and General pages.
- `protocol.js`: original 0x55AA utility protocol and capability-checked XCAL v1.
- `profiles.json`: the same 29 UID/matrix profiles as desktop add-on 1.0.4.

The provider is discovered by the existing browser add-on loader. Desktop Python
ZIPs are not browser executable; the browser implementation is compiled with
the site. No changes to keyboard firmware are necessary for existing monitoring.
Persistent sliders require the shared XCAL firmware extension. There is no
sensor logging, automatic EEPROM erase or automatic bootloader entry.
