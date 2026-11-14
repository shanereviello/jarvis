import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/codex_cutover_restart_guard.py'
spec = importlib.util.spec_from_file_location('restart_guard_fixture', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Systemd:
    def __init__(self):
        self.enabled = 'enabled'
        self.active = 'active'
        self.commands = []

    def __call__(self, args, **kwargs):
        operation = args[1]
        self.commands.append(operation)
        if operation == 'mask':
            self.enabled = 'masked-runtime'
        elif operation == 'stop':
            self.active = 'inactive'
        elif operation == 'unmask':
            self.enabled = 'enabled'
        if operation == 'is-enabled':
            return SimpleNamespace(returncode=0 if self.enabled == 'enabled' else 1, stdout=self.enabled)
        if operation == 'is-active':
            return SimpleNamespace(returncode=0 if self.active == 'active' else 3, stdout=self.active)
        return SimpleNamespace(returncode=0, stdout='')


def test_mask_blocks_restart_until_consistency_verified():
    systemd = Systemd()
    guard = module.Guard('rras-codex-runtime.service', run=systemd)
    guard.acquire()
    assert guard.verified() and systemd.enabled == 'masked-runtime'
    with pytest.raises(ValueError, match='mask retained'):
        guard.release(lambda:False)
    assert systemd.enabled == 'masked-runtime' and 'unmask' not in systemd.commands
    guard.release(lambda:True)
    assert not guard.verified() and 'start' not in systemd.commands


def test_existing_mask_or_unexpected_restart_refused():
    systemd = Systemd()
    systemd.enabled = 'masked-runtime'
    guard = module.Guard('rras-codex-runtime.service', run=systemd)
    with pytest.raises(ValueError, match='inspection'):
        guard.acquire()
    assert 'unmask' not in systemd.commands
    systemd.enabled = 'enabled'
    guard.acquire()
    systemd.active = 'active'
    assert not guard.verified()
    with pytest.raises(ValueError, match='mask retained'):
        guard.release(lambda:True)
