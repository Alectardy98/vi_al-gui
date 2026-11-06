# SPDX-License-Identifier: GPL-2.0-or-later
"""Capability-gated whole-Main EEPROM reset. No retries of the reset request."""
class UnsupportedFactoryReset(RuntimeError):
    pass


class FactoryResetClient:
    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.uncertain = False

    def request(self, operation):
        if operation not in (0, 1) or self.uncertain:
            raise RuntimeError('Refresh before another request; a reset is never retried automatically.')
        packet = bytes((253, 236, operation, 1, 1 if operation else 0))
        if operation:
            packet += b'CLR1MAIN'
        try:
            if self.keyboard.dev.write(b'\0' + packet.ljust(32, b'\0')) != 33:
                raise RuntimeError('Short HID request.')
            r = bytes(self.keyboard.dev.read(32, timeout_ms=1000))
            if operation == 0 and (len(r) != 32 or r[:6] != bytes((253, 236, 170, 1, 0, 0))):
                raise UnsupportedFactoryReset('GUI Clear EEPROM requires the new Main firmware. The Clear EEPROM keycode remains available.')
            if len(r) != 32 or r[:2] != b'\xfd\xec' or r[3:6] != bytes((1, operation, 1 if operation else 0)):
                raise RuntimeError('Missing or mismatched reset response; check the keyboard before trying again.')
            if r[2] != 170:
                raise RuntimeError({1:'Unsupported reset protocol.',2:'Keyboard locked, storage mode or a file/display operation is busy.',3:'Invalid reset confirmation.',4:'Main settings storage could not queue the reset.'}.get(r[6], 'Reset rejected.'))
            return r
        except UnsupportedFactoryReset:
            raise
        except (OSError, RuntimeError, TypeError) as error:
            self.uncertain = True
            raise RuntimeError(str(error) + ' No request was retried.') from error

    def capabilities(self):
        r = self.request(0)
        if r[6:12] != b'CLR1' + bytes((32, 7)):
            raise UnsupportedFactoryReset('Unknown whole-Main reset capabilities; no reset is available.')
        return dict(ready=bool(r[12]))

    def clear(self):
        if not self.capabilities()['ready']:
            raise RuntimeError('Keyboard is busy or locked. Finish storage/display operations and try later.')
        r = self.request(1)
        if r[6] != 1:
            raise RuntimeError('Main did not confirm that the reset was queued.')
        return True
