import hashlib
import importlib.util
import os
from pathlib import Path

import pytest

from test_reporting_onboarding_admission import inputs, policy

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/codex_cutover_files.py'
spec = importlib.util.spec_from_file_location('cutover_files_fixture', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
runtime = module.local('codex_runtime')


def digest(value):
    return hashlib.sha256(runtime.encoded(value)).hexdigest()


def test_retained_intent_is_exclusive_and_private(tmp_path):
    root = tmp_path / 'audit'
    root.mkdir(mode=0o700)
    result = module.retain(root, 'intent.json', {'plan': 'p'}, owner=os.geteuid())
    assert result == digest({'plan': 'p'})
    assert (root / 'intent.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        module.retain(root, 'intent.json', {'plan': 'different'}, owner=os.geteuid())
    assert (root / 'intent.json').read_bytes() == runtime.encoded({'plan': 'p'})
    with pytest.raises(ValueError):
        module.retain(root, '../outside', {}, owner=os.geteuid())


def test_atomic_policy_replacement_checks_digest_and_preserves_mode(tmp_path, policy):
    old, _ = inputs(tmp_path, policy)
    new = dict(old, execution_authorized=not old['execution_authorized'])
    path = tmp_path / 'policy.json'
    path.write_bytes(runtime.encoded(old))
    path.chmod(0o600)
    with pytest.raises(ValueError, match='changed'):
        module.install(path, '0' * 64, new, owner=os.geteuid())
    assert path.read_bytes() == runtime.encoded(old)
    result = module.install(path, digest(old), new, owner=os.geteuid())
    assert result == digest(new)
    assert path.read_bytes() == runtime.encoded(new)
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob('.policy.json.*.tmp'))


def test_rejects_symlinks_and_writable_audit_directory(tmp_path, policy):
    root = tmp_path / 'audit'
    root.mkdir(mode=0o755)
    with pytest.raises(ValueError, match='private'):
        module.retain(root, 'intent.json', {}, owner=os.geteuid())
    old, _ = inputs(tmp_path, policy)
    target = tmp_path / 'target'
    target.write_bytes(runtime.encoded(old))
    target.chmod(0o600)
    link = tmp_path / 'link'
    link.symlink_to(target)
    with pytest.raises(ValueError):
        module.install(link, digest(old), old, owner=os.geteuid())


def test_fixed_file_adapter_retains_transition_and_completion(tmp_path, policy):
    old, _ = inputs(tmp_path, policy)
    new = dict(old, execution_authorized=not old['execution_authorized'])
    installed = tmp_path / 'policy.json'
    installed.write_bytes(runtime.encoded(old));installed.chmod(0o600)
    audit = tmp_path / 'audit';audit.mkdir(mode=0o700)
    adapter = module.local('codex_cutover_root_files').Files(installed, audit, owner=os.geteuid())
    plan = {'old_policy_sha256': digest(old), 'new_policy_sha256': digest(new)}
    sha = digest(plan)
    adapter.retain_intent(sha, plan, old, new)
    adapter.install(digest(old), new)
    adapter.retain_completion(sha)
    assert adapter.digest() == digest(new)
    assert (audit / (sha + '.intent')).is_file() and (audit / (sha + '.complete')).is_file()
    with pytest.raises(FileExistsError):
        adapter.retain_intent(sha, plan, old, new)
