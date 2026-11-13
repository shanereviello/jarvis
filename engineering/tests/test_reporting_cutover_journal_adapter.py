from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from test_reporting_onboarding_admission import inputs, policy, AUTH
from test_reporting_codex_runtime import m as runtime

base = Path(__file__).resolve().parents[1] / 'tools/rras_reporting'


def load(name):
    spec = importlib.util.spec_from_file_location('integrated_fixture_' + name, base / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Files:
    def __init__(self, root, old):
        self.root = root
        self.path = root / 'policy.json'
        self.path.write_bytes(runtime.encoded(old))
        self.path.chmod(0o600)
        self.audit = root / 'audit'
        self.audit.mkdir(mode=0o700)
        self.ops = load('codex_cutover_files')

    def digest(self):
        return hashlib.sha256(runtime.encoded(runtime.policy(json.loads(self.path.read_bytes())))).hexdigest()

    def retain_intent(self, sha, plan, old, new):
        self.ops.retain(self.audit, sha + '.intent', {'plan': plan, 'old': old, 'new': new}, owner=os.geteuid())

    def install(self, old_sha, new):
        self.ops.install(self.path, old_sha, new, owner=os.geteuid())

    def retain_completion(self, sha):
        self.ops.retain(self.audit, sha + '.complete', {'plan_sha256': sha}, owner=os.geteuid())


@contextmanager
def fixture_lock():
    yield


def setup(tmp_path, policy, verify, authority):
    old, request = inputs(tmp_path, policy)
    journal = tmp_path / 'journal'
    instance = runtime.Runtime(journal, old, create=True, issue_client_factory=lambda *_:None)
    instance.close()
    files = Files(tmp_path, old)
    adapter = load('codex_cutover_journal_adapter').Adapter(journal, request, verify, authority, files, fixture_lock)
    plan = load('codex_issue_admission_migration').plan(journal, request, verify, authority)
    return adapter, files, plan


def test_combined_journal_and_policy_transition(tmp_path, policy):
    adapter, files, plan = setup(tmp_path, policy, lambda _:True, lambda _:AUTH)
    result = load('codex_issue_cutover').execute(adapter, expected_plan_sha256=plan['expected_sha256'])
    assert result['cutover_complete'] and not result['models_started']
    assert files.digest() == plan['new_policy_sha256']
    assert len(list(files.audit.glob('*.intent'))) == len(list(files.audit.glob('*.complete'))) == 1
    with adapter.exclusive_stopped():
        assert adapter.journal_digest() == files.digest()


def test_revocation_leaves_durable_journal_ahead_for_inspection(tmp_path, policy):
    checks = []
    def verify(_):
        checks.append(1)
        return len(checks) < 4
    adapter, files, plan = setup(tmp_path, policy, verify, lambda _:AUTH)
    with pytest.raises(ValueError, match='revoked'):
        load('codex_issue_cutover').execute(adapter, expected_plan_sha256=plan['expected_sha256'])
    assert files.digest() == plan['old_policy_sha256']
    assert len(list(files.audit.glob('*.intent'))) == 1
    assert not list(files.audit.glob('*.complete'))
    with adapter.exclusive_stopped():
        assert adapter.journal_digest() == plan['new_policy_sha256']


def test_fixed_broker_and_journal_client_use_same_transition(tmp_path, policy):
    adapter, files, plan = setup(tmp_path, policy, lambda _:True, lambda _:AUTH)
    with adapter.exclusive_stopped():
        value, old, new = adapter.revalidate()
    def check_journal(digest, receipt):
        if adapter.journal_digest() != digest:
            return False
        if receipt is None:
            return True
        rows = adapter.db.execute('SELECT plan_sha256 FROM policy_issue_admissions').fetchall()
        return len(rows) == 1 and rows[0][0] == receipt
    broker = load('codex_cutover_fixed_broker').Broker(
        peer_uid=1234, transition={'plan':value,'old':old,'new':new}, files=files,
        verify_stopped=lambda:True, verify_journal=check_journal, verify_evidence=lambda _:True)
    client = load('codex_cutover_broker_client').Files('fixture', request=lambda _, op:broker.call(1234, op))
    adapter.files = client
    result = load('codex_issue_cutover').execute(adapter, expected_plan_sha256=plan['expected_sha256'])
    assert result['cutover_complete'] and files.digest() == plan['new_policy_sha256']
    assert broker.stage == 'complete'


def test_client_refuses_a_different_privileged_transition(tmp_path, policy):
    adapter, files, plan = setup(tmp_path, policy, lambda _:True, lambda _:AUTH)
    calls = []
    def request(_, operation):
        calls.append(operation)
        if operation == 'digest':
            return files.digest()
        if operation == 'transition':
            return {'plan_sha256':'0' * 64, 'old_sha256':plan['old_policy_sha256'],
                    'new_sha256':plan['new_policy_sha256']}
        raise AssertionError('mismatched broker must not receive a mutation')
    adapter.files = load('codex_cutover_broker_client').Files('fixture', request=request)
    with pytest.raises(ValueError, match='transition differs'):
        load('codex_issue_cutover').execute(adapter, expected_plan_sha256=plan['expected_sha256'])
    assert 'intent' not in calls and files.digest() == plan['old_policy_sha256']
