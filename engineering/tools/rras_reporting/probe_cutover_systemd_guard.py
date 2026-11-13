"""Verify the restart guard against one temporary, unrelated systemd unit."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid


def main():
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('root required for temporary systemd unit')
    token = uuid.uuid4().hex
    unit = 'rras-cutover-guard-probe-' + token + '.service'
    path = Path('/etc/systemd/system') / unit
    content = ('[Unit]\nDescription=Temporary isolated RRAS cutover guard probe\n'
               '[Service]\nType=simple\nExecStart=/usr/bin/sleep 300\n'
               '[Install]\nWantedBy=multi-user.target\n').encode()
    expected = hashlib.sha256(content).hexdigest()
    spec = importlib.util.spec_from_file_location('cutover_guard_probe', Path(__file__).with_name('codex_cutover_restart_guard.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def systemctl(*args, check=True):
        return subprocess.run(['/usr/bin/systemctl', *args], capture_output=True, text=True, check=check, timeout=30)
    created = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        systemctl('daemon-reload')
        systemctl('start', unit)
        guard = module.Guard(unit)
        guard.acquire()
        blocked = systemctl('start', unit, check=False)
        if blocked.returncode == 0 or not guard.verified():
            raise ValueError('masked temporary unit unexpectedly started')
        guard.release(lambda:True)
        systemctl('start', unit)
        if systemctl('is-active', unit).stdout.strip() != 'active':
            raise ValueError('temporary unit did not restart after release')
        print(json.dumps(dict(temporary_unit_guard_verified=True, restart_blocked_while_masked=True,
            restart_allowed_after_verified_release=True, production_services_changed=False,
            models_started=0), sort_keys=True))
    finally:
        if created:
            systemctl('stop', unit, check=False)
            systemctl('unmask', '--runtime', unit, check=False)
            if not path.is_symlink() and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                path.unlink()
            else:
                raise ValueError('temporary unit changed; preserve for inspection')
            systemctl('daemon-reload')


if __name__ == '__main__':
    main()
