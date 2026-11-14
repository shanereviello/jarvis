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
    audit = Path('/run') / ('rras-cutover-guard-probe-' + token)
    content = ('[Unit]\nDescription=Temporary isolated RRAS cutover guard probe\n'
               '[Service]\nType=simple\nExecStart=/usr/bin/sleep 300\n'
               '[Install]\nWantedBy=multi-user.target\n').encode()
    expected = hashlib.sha256(content).hexdigest()
    spec = importlib.util.spec_from_file_location('cutover_guard_probe', Path(__file__).with_name('codex_cutover_persistent_guard.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def systemctl(*args, check=True):
        return subprocess.run(['/usr/bin/systemctl', *args], capture_output=True, text=True, check=check, timeout=30)
    created = False
    audit_created = False
    guard = None
    try:
        audit.mkdir(mode=0o700);audit_created = True
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        systemctl('daemon-reload')
        systemctl('start', unit)
        guard = module.Guard(unit, audit)
        try:
            guard.acquire()
        except ValueError:
            print(json.dumps(dict(temporary_unit=unit,
                enabled_status=guard.command('is-enabled'), active_status=guard.command('is-active'),
                unit_mask_symlink=path.is_symlink(),
                temporary_unit_preserved_until_cleanup=True, production_services_changed=False), sort_keys=True), flush=True)
            raise
        blocked = systemctl('start', unit, check=False)
        if blocked.returncode == 0 or not guard.verified():
            raise ValueError('masked temporary unit unexpectedly started')
        guard.release(lambda:True)
        systemctl('start', unit)
        if systemctl('is-active', unit).stdout.strip() != 'active':
            raise ValueError('temporary unit did not restart after release')
        # Simulate an interrupted second cutover using the same isolated unit.
        before = set(audit.iterdir())
        guard = module.Guard(unit, audit)
        guard.acquire()
        created_intents = [item for item in audit.iterdir() if item not in before and item.name.endswith('.unit-intent')]
        if len(created_intents) != 1:
            raise ValueError('exact recovery intent required')
        recovery_spec = importlib.util.spec_from_file_location('unit_recovery_probe', Path(__file__).with_name('codex_cutover_unit_recovery.py'))
        recovery = importlib.util.module_from_spec(recovery_spec);recovery_spec.loader.exec_module(recovery)
        try:
            recovery.restore(created_intents[0], unit, lambda:False)
        except ValueError:
            pass
        else:
            raise ValueError('recovery accepted unverified consistency')
        if not guard.verified():
            raise ValueError('failed consistency check did not retain mask')
        restored = recovery.restore(created_intents[0], unit, lambda:True)
        if not restored['restored'] or restored['service_started']:
            raise ValueError('explicit recovery outcome differs')
        print(json.dumps(dict(temporary_unit_guard_verified=True, restart_blocked_while_masked=True,
            restart_allowed_after_verified_release=True, explicit_recovery_verified=True,
            failed_consistency_retained_mask=True, production_services_changed=False,
            models_started=0), sort_keys=True))
    finally:
        if created:
            systemctl('stop', unit, check=False)
            # The test owns this unique unit. Restore only its exact retained
            # inode and bytes if an interrupted probe left it masked.
            if path.is_symlink() and os.readlink(path) == '/dev/null' and guard and guard.backup:
                backup = guard.backup
                info = backup.lstat()
                if ((info.st_dev, info.st_ino) != guard.identity or not backup.is_file() or
                        hashlib.sha256(backup.read_bytes()).hexdigest() != expected):
                    raise ValueError('temporary backup differs; preserve for inspection')
                os.replace(backup, path)
            if guard and guard.backup and guard.backup.exists():
                info = guard.backup.lstat()
                current = path.lstat()
                if ((info.st_dev, info.st_ino) != guard.identity or
                        (current.st_dev, current.st_ino) != guard.identity or
                        hashlib.sha256(guard.backup.read_bytes()).hexdigest() != expected):
                    raise ValueError('temporary backup differs; preserve for inspection')
                guard.backup.unlink()
            if not path.is_symlink() and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                path.unlink()
            else:
                raise ValueError('temporary unit changed; preserve for inspection')
            systemctl('daemon-reload')
        if audit_created:
            for item in audit.iterdir():
                if not item.is_file() or item.is_symlink() or not item.name.endswith(('.unit-intent', '.unit-restore')):
                    raise ValueError('unexpected probe audit file; preserve for inspection')
                item.unlink()
            audit.rmdir()


if __name__ == '__main__':
    main()
