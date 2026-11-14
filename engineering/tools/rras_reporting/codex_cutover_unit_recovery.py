"""Explicitly restore a retained unit after independent cutover reconciliation.

This does not decide whether policy state is safe, retry work, or start a unit.
The protected caller must hold the admission lock and provide that decision.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess


def local(name):
    spec = importlib.util.spec_from_file_location('unit_recovery_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def restore(intent_path, unit, verify_consistent, *, directory='/etc/systemd/system', owner=0, run=subprocess.run):
    if (os.geteuid() != owner or not callable(verify_consistent) or type(unit) is not str or
            not re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', unit)):
        raise ValueError('protected unit and independent consistency check required')
    intent = Path(intent_path)
    match = re.fullmatch(r'([0-9a-f]{32})\.unit-intent', intent.name)
    if match is None:
        raise ValueError('exact retained unit intent required')
    audit = local('codex_cutover_files').private_directory(intent.parent, owner)
    raw = local('protected_config').read(intent, maximum=4096, require_root=owner == 0)
    value = json.loads(raw)
    root = Path(directory)
    if root.resolve() != root or root.lstat().st_uid != owner or root.lstat().st_mode & 0o022:
        raise ValueError('protected unit directory required')
    backup = root / ('.rras-cutover-' + match.group(1) + '.unit')
    target = root / unit
    if (type(value) is not dict or set(value) != {'unit', 'backup', 'unit_sha256', 'enablement'} or
            value['unit'] != unit or value['backup'] != str(backup) or value['enablement'] not in ('enabled','disabled') or
            type(value['unit_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['unit_sha256'])):
        raise ValueError('retained unit intent differs')
    info = backup.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_nlink != 1 or
            info.st_mode & 0o022 or info.st_size > 1024 * 1024 or
            hashlib.sha256(backup.read_bytes()).hexdigest() != value['unit_sha256']):
        raise ValueError('retained unit differs')
    if not target.is_symlink() or os.readlink(target) != '/dev/null':
        raise ValueError('expected unit mask unavailable')
    if verify_consistent() is not True:
        raise ValueError('unit mask retained; independent consistency check required')
    local('codex_cutover_files').retain(audit, match.group(1) + '.unit-restore',
        {'unit':unit, 'unit_sha256':value['unit_sha256']}, owner=owner)
    os.replace(backup, target)
    local('codex_cutover_files').directory_sync(root)
    reload = run(['/usr/bin/systemctl', 'daemon-reload'], capture_output=True, text=True, timeout=30)
    status = run(['/usr/bin/systemctl', 'is-enabled', unit], capture_output=True, text=True, timeout=30)
    expected = (0, 'enabled') if value['enablement'] == 'enabled' else (1, 'disabled')
    if reload.returncode != 0 or (status.returncode, status.stdout.strip()) != expected:
        raise ValueError('unit restored; manager state requires inspection')
    return {'restored':True, 'service_started':False, 'models_started':0}
