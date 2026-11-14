"""Fail-closed exclusion for a root-owned unit installed under /etc.

The caller must hold the root-private admission lock. Interrupted changes are
left for explicit inspection; this code never starts a service or auto-recovers.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess


def local(name):
    spec = importlib.util.spec_from_file_location('persistent_guard_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Guard:
    def __init__(self, unit, audit, *, directory='/etc/systemd/system', owner=0, run=subprocess.run):
        if type(unit) is not str or not re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', unit):
            raise ValueError('exact service unit required')
        self.unit, self.directory, self.owner, self.run = unit, Path(directory), owner, run
        self.audit = local('codex_cutover_files').private_directory(audit, owner)
        self.path = self.directory / unit
        self.backup = None
        self.initial_state = None
        self.sha = None
        self.identity = None

    def command(self, *args):
        result = self.run(['/usr/bin/systemctl', *args], capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout.strip()

    def acquire(self):
        if os.geteuid() != self.owner or self.directory.resolve() != self.directory:
            raise ValueError('protected unit owner required')
        parent = self.directory.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != self.owner or parent.st_mode & 0o022:
            raise ValueError('protected unit directory required')
        state = self.command('is-enabled', self.unit)
        if state not in ((0, 'enabled'), (1, 'disabled')):
            raise ValueError('unit enablement requires inspection')
        self.initial_state = state
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner or info.st_nlink != 1 or
                    info.st_mode & 0o022 or info.st_size > 1024 * 1024):
                raise ValueError('single protected unit file required')
            with os.fdopen(fd, 'rb', closefd=False) as stream: raw = stream.read(1024 * 1024 + 1)
            self.sha = hashlib.sha256(raw).hexdigest()
            self.identity = (info.st_dev, info.st_ino)
        finally:os.close(fd)
        token = secrets.token_hex(16)
        self.backup = self.directory / ('.rras-cutover-' + token + '.unit')
        temporary = self.directory / ('.rras-cutover-' + token + '.mask')
        local('codex_cutover_files').retain(self.audit, token + '.unit-intent',
            {'unit':self.unit, 'backup':str(self.backup), 'unit_sha256':self.sha, 'enablement':state[1]}, owner=self.owner)
        os.link(self.path, self.backup, follow_symlinks=False)
        local('codex_cutover_files').directory_sync(self.directory)
        linked = self.backup.lstat();current = self.path.lstat()
        if ((linked.st_dev, linked.st_ino) != self.identity or (current.st_dev, current.st_ino) != self.identity):
            raise ValueError('unit changed; retained backup requires inspection')
        os.symlink('/dev/null', temporary)
        os.replace(temporary, self.path)
        local('codex_cutover_files').directory_sync(self.directory)
        if self.command('daemon-reload')[0] != 0 or self.command('stop', self.unit)[0] != 0 or not self.verified():
            raise ValueError('mask retained; stopped service not verified')

    def verified(self):
        if self.backup is None or not self.path.is_symlink() or os.readlink(self.path) != '/dev/null':return False
        return (self.command('is-enabled', self.unit) == (1, 'masked') and
                self.command('is-active', self.unit) in ((3, 'inactive'), (3, 'failed')))

    def release(self, verify_consistent):
        if not callable(verify_consistent) or not self.verified() or verify_consistent() is not True:
            raise ValueError('mask retained; consistency verification required')
        info = self.backup.lstat()
        if (not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != self.identity or
                hashlib.sha256(self.backup.read_bytes()).hexdigest() != self.sha):
            raise ValueError('retained unit differs; mask retained')
        os.replace(self.backup, self.path)
        local('codex_cutover_files').directory_sync(self.directory)
        if self.command('daemon-reload')[0] != 0 or self.command('is-enabled', self.unit) != self.initial_state:
            raise ValueError('unit restored but manager state uncertain; inspect before start')
