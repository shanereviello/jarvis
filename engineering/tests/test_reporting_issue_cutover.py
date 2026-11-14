import hashlib
import importlib.util
from contextlib import contextmanager
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/codex_issue_cutover.py'
spec = importlib.util.spec_from_file_location('issue_cutover_fixture', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
runtime = module.local('codex_runtime')


def digest(value):
    return hashlib.sha256(runtime.encoded(value)).hexdigest()


class Fixture:
    def __init__(self, failure=None):
        self.old, self.new = {'issue': 'old'}, {'issue': 'new'}
        self.plan = {'old_policy_sha256': digest(self.old), 'new_policy_sha256': digest(self.new)}
        self.journal, self.file = digest(self.old), digest(self.old)
        self.failure = failure
        self.calls = []
        self.locked = False

    @contextmanager
    def exclusive_stopped(self):
        self.locked = True
        try:
            yield
        finally:
            self.locked = False

    def mark(self, name):
        assert self.locked
        self.calls.append(name)
        if self.failure == name:
            raise ValueError(name)

    def revalidate(self):
        self.mark('revalidate')
        return self.plan, self.old, self.new

    def journal_digest(self):
        assert self.locked
        return self.journal

    def file_digest(self):
        assert self.locked
        return self.file

    def retain_intent(self, *args):
        self.mark('intent')

    def update_journal(self, *args):
        self.mark('journal')
        self.journal = digest(self.new)

    def recheck_authority_and_evidence(self, *args):
        self.mark('recheck')

    def install_policy_atomically(self, old_sha, new):
        self.mark('install')
        assert self.file == old_sha
        self.file = digest(new)

    def retain_completion(self, *args):
        self.mark('completion')


def test_cutover_orders_durable_intent_journal_recheck_and_file():
    adapter = Fixture()
    result = module.execute(adapter, expected_plan_sha256=digest(adapter.plan))
    assert adapter.calls == ['revalidate', 'intent', 'journal', 'recheck', 'install', 'completion']
    assert adapter.journal == adapter.file == digest(adapter.new)
    assert result['cutover_complete'] and not result['service_started'] and not adapter.locked


@pytest.mark.parametrize('failure', ['intent', 'journal', 'recheck', 'install', 'completion'])
def test_failed_cutover_leaves_evidence_for_inspection_without_retry(failure):
    adapter = Fixture(failure)
    with pytest.raises(ValueError):
        module.execute(adapter, expected_plan_sha256=digest(adapter.plan))
    assert not adapter.locked
    if failure in ('recheck', 'install'):
        assert adapter.journal == digest(adapter.new) and adapter.file == digest(adapter.old)
        with pytest.raises(ValueError, match='not pristine'):
            module.execute(adapter, expected_plan_sha256=digest(adapter.plan))
    if failure == 'completion':
        assert adapter.journal == adapter.file == digest(adapter.new)
        with pytest.raises(ValueError, match='not pristine'):
            module.execute(adapter, expected_plan_sha256=digest(adapter.plan))


def test_changed_plan_or_existing_partial_state_never_mutates():
    adapter = Fixture()
    with pytest.raises(ValueError, match='plan changed'):
        module.execute(adapter, expected_plan_sha256='a' * 64)
    assert adapter.calls == ['revalidate']
    adapter.journal = digest(adapter.new)
    with pytest.raises(ValueError, match='not pristine'):
        module.execute(adapter, expected_plan_sha256=digest(adapter.plan))
    assert 'intent' not in adapter.calls
