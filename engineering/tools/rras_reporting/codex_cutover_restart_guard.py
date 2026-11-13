"""Explicit systemd restart exclusion for a stopped cutover.

Caller must hold the separate operator lock throughout. A failure keeps a
successfully installed runtime mask in place for explicit reconciliation.
Nothing here starts the runtime or performs an automatic recovery.
"""
import re
import subprocess


class Guard:
    def __init__(self, unit, *, run=subprocess.run):
        if type(unit) is not str or not re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', unit):
            raise ValueError('exact service unit required')
        self.unit = unit
        self.run = run
        self.owned = False

    def command(self, *args):
        result = self.run(['/usr/bin/systemctl', *args, self.unit], capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout.strip()

    def acquire(self):
        code, state = self.command('is-enabled')
        if (code, state) not in ((0, 'enabled'), (1, 'disabled')):
            raise ValueError('unit enablement requires inspection before masking')
        code, _ = self.command('mask', '--runtime')
        if code != 0:
            raise ValueError('runtime mask could not be installed')
        self.owned = True
        code, _ = self.command('stop')
        if code != 0 or not self.verified():
            raise ValueError('mask retained; stopped service not verified')

    def verified(self):
        if not self.owned:
            return False
        mask_code, mask = self.command('is-enabled')
        active_code, active = self.command('is-active')
        return mask_code == 1 and mask == 'masked-runtime' and active_code == 3 and active in ('inactive', 'failed')

    def release(self, verify_consistent):
        if not callable(verify_consistent) or not self.verified() or verify_consistent() is not True:
            raise ValueError('mask retained; consistency verification required')
        code, _ = self.command('unmask', '--runtime')
        if code != 0:
            raise ValueError('mask removal uncertain; inspect before restart')
        self.owned = False
