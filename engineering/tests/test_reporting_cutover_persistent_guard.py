import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/codex_cutover_persistent_guard.py'
spec = importlib.util.spec_from_file_location('persistent_guard_fixture', path)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class Systemd:
    def __init__(self, unit):self.unit = unit;self.active = True
    def __call__(self, args, **_):
        operation = args[1]
        if operation == 'is-enabled':
            masked = self.unit.is_symlink()
            return SimpleNamespace(returncode=1 if masked else 0, stdout='masked' if masked else 'enabled')
        if operation == 'is-active':
            return SimpleNamespace(returncode=0 if self.active else 3, stdout='active' if self.active else 'inactive')
        if operation == 'stop':self.active = False
        return SimpleNamespace(returncode=0, stdout='')


def test_etc_unit_mask_and_restore_preserve_original_bytes(tmp_path):
    directory = tmp_path / 'units';directory.mkdir(mode=0o700)
    audit = tmp_path / 'audit';audit.mkdir(mode=0o700)
    unit = directory / 'fixture.service';unit.write_bytes(b'[Service]\nExecStart=/bin/true\n');unit.chmod(0o644)
    inode = unit.stat().st_ino
    guard = module.Guard('fixture.service', audit, directory=directory, owner=os.getuid(), run=Systemd(unit))
    guard.acquire()
    assert guard.verified() and os.readlink(unit) == '/dev/null'
    with pytest.raises(ValueError, match='mask retained'):guard.release(lambda:False)
    assert unit.is_symlink()
    guard.release(lambda:True)
    assert unit.read_bytes() == b'[Service]\nExecStart=/bin/true\n' and unit.stat().st_ino == inode
    assert len(list(audit.glob('*.unit-intent'))) == 1


def test_guard_refuses_changed_retained_unit(tmp_path):
    directory = tmp_path / 'units';directory.mkdir(mode=0o700)
    audit = tmp_path / 'audit';audit.mkdir(mode=0o700)
    unit = directory / 'fixture.service';unit.write_bytes(b'original');unit.chmod(0o644)
    guard = module.Guard('fixture.service', audit, directory=directory, owner=os.getuid(), run=Systemd(unit))
    guard.acquire()
    guard.backup.write_bytes(b'changed')
    with pytest.raises(ValueError, match='mask retained'):guard.release(lambda:True)
    assert unit.is_symlink()
