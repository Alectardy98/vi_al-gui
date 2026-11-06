# AW768 lighting add-on

The supported custom keyboard has two boards behind the same internal USB hub:
an RP2040 runs QMK/Vial, and the original AW768 PCB controls lighting. The add-on
verifies their interface identities and shared hub before opening lighting.
It uses the native lighting protocol, without Dell AWCC or a firmware update.

The Lighting page exposes supported key groups, the macro area, colors, effects,
tempo and brightness. **Save changes to keyboard** writes the native onboard
profile. Expanded zones are capability-gated; old PCB firmware keeps its supported
controls rather than receiving unsupported commands.

Linux may need the supplied [udev rules](70-vial-astro-aw768.rules) for the native
lighting interface. Standard Vial USB access is separate. See the project's
[OS requirements](../DEPENDENCIES.md) and [add-on API](../ADDONS.md).
