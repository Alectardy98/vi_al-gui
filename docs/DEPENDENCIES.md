# Vi_al 1.0.1 · self-contained release audit

End users do not install Python, pip packages, Qt, HIDAPI, PyUSB, libusb,
Microsoft Visual C++ redistributables, Dell AWCC or EC42 utilities. These runtimes
and modules are included in the frozen application. Add-on ZIP installation runs
no dependency installer and downloads no code.

## Custom pages

| Add-on / pages | Runtime used |
|---|---|
| EC42 Calibration, Actuation, Live Sensors | Bundled Qt/HIDAPI; EC42 commands go directly over the selected HID connection |
| AW768 Lighting, zones, effects and native saving | Bundled HIDAPI and pure Python protocol; native OS USB ancestry APIs verify the companion PCB |
| MY-2K RGB Strips, RGB Grids, Lock Lights | Bundled Qt/HIDAPI; live settings and persistence use existing firmware commands |
| MY-2K Touch Bar | Bundled Qt/HIDAPI; sensitivity, jitter and bindings use existing firmware commands |
| MY-2K General, performance, sleep and reset controls | Direct HID commands; no QMK Toolbox, OpenOCD, flashing script or shell helper |
| MY-2K Auxiliary Display | Bundled Qt fonts/rendering and HID configuration protocol; no external image converter |
| MY-2K Animations | Bundled GIF/image plugins, Python/native encoder and HID/PyUSB file transport |
| MY-2K Gaming: NES, GBC and Doom controls | Direct HID and existing firmware file protocol; game execution remains on the keyboard |
| Bootloader entry | Direct HID command on matching firmware; no external flashing program is invoked |

User-provided GIFs, ROMs and game assets remain user content, not software
dependencies. Firmware features still require matching keyboard capabilities.

## Removed host-tool dependencies

MY-2K no longer runs `findmnt` to discover/verify mounted storage: it uses
`QStorageInfo`. Linux maintenance mounting calls UDisks2 directly through bundled
QtDBus, instead of running `udisksctl`. It retains filesystem readiness checks,
verified USB identity and one explicit mount attempt. It never formats a disk.

AW768 companion verification uses Linux sysfs, Windows CfgMgr32, or macOS IOKit
and CoreFoundation. The Windows and Mac adapters use OS APIs through `ctypes`;
no PowerShell, WMI command, `ioreg` executable or Dell utility is needed. Pairing
continues to require exact interface identity and a shared immediate USB hub.
Windows/macOS physical acceptance remains pending; native adapters are not a
claim that every USB topology has been tested on those operating systems.

## Operating-system requirements are still real

- A supported graphical desktop OS is required. Local Linux builds use this
  Manjaro host's glibc; Ubuntu 22.04 CI builds are intended for distribution.
- The FUSE-free Linux archive runs its `Vi_al/Vi_al` executable after extraction.
  The optional AppImage embeds its runtime/libfuse, but mounting may still need
  the OS FUSE helper. Its extract-and-run alternative avoids that requirement.
- Linux HID/USB access needs appropriate OS permissions. An app cannot bypass
  these by bundling libraries. Existing desktop UDisks2/authorization services
  are used for privileged maintenance mounting; ordinary GIF transfers do not
  need a mounted drive. This explicit maintenance integration remains Linux-specific.
- Upstream Vial's global Linux macro recorder uses the OS `pkexec` and `dumpkeys`
  helpers for authorization/key translation. This is outside the custom add-ons;
  the app does not embed a setuid
  privilege-escalation helper. Ordinary macro editing needs no such helper.
- macOS may request input/USB access and approval for unsigned software. Windows
  may show SmartScreen for the unsigned installer. These are OS security checks.
- Windows/macOS use MY-2K's existing bounded HID fallback where the Linux-specific
  fast vendor transport cannot be selected; transfer speeds are not guaranteed
  equal across platforms.

Manufacturer/OS API references: [UDisks2 Filesystem](https://storaged.org/udisks/docs/gdbus-org.freedesktop.UDisks2.Filesystem.html),
[Microsoft device ancestry](https://learn.microsoft.com/en-us/windows/win32/api/cfgmgr32/nf-cfgmgr32-cm_get_parent),
[Apple registry ancestry](https://developer.apple.com/documentation/iokit/1514454-ioregistryentrygetparententry),
[AppImage's static runtime](https://github.com/AppImage/type2-runtime).

## What has been checked

The release is exercised as a frozen app with an empty executable `PATH`, rather
than running from the development Python environment. All custom pages are
opened on the three connected keyboards with a read-only HID guard. Separate
packaged checks validate the actual purple window icon, image codecs and bundled
USB backend. Protocol/GUI tests exercise settings encoders, acknowledgements,
readback, error handling and persistence against controlled fixtures.

Settings saves, EEPROM clearing and bootloader entry are not automatically
triggered on connected hardware just to prove the absence of a dependency.
No keyboard settings or firmware need changing for this packaging audit.
Historical hardware reports are archived separately from the source checkout.
macOS packaging and physical Windows/macOS checks require their native machines.
