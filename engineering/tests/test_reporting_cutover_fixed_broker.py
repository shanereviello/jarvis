import importlib.util
from pathlib import Path

import pytest

from test_reporting_onboarding_admission import inputs, policy
from test_reporting_cutover_journal_adapter import Files
from test_reporting_codex_runtime import m as runtime

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/codex_cutover_fixed_broker.py'
spec = importlib.util.spec_from_file_location('fixed_broker_fixture', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(tmp_path, policy):
    old, _ = inputs(tmp_path, policy)
    new = dict(old, execution_authorized=not old['execution_authorized'])
    import hashlib
    digest = lambda x: hashlib.sha256(runtime.encoded(x)).hexdigest()
    plan = {'old_policy_sha256': digest(old), 'new_policy_sha256': digest(new)}
    files = Files(tmp_path, old)
    state = {'stopped': True, 'journal': digest(old), 'receipt': None, 'evidence': True}
    broker = module.Broker(peer_uid=1234, transition={'plan': plan, 'old': old, 'new': new}, files=files,
        verify_stopped=lambda:state['stopped'],
        verify_journal=lambda digest, receipt:state['journal'] == digest and state['receipt'] == receipt,
        verify_evidence=lambda _:state['evidence'])
    return broker, files, state


def test_fixed_broker_restricts_peer_operations_and_transition(tmp_path, policy):
    broker, files, state = fixture(tmp_path, policy)
    with pytest.raises(ValueError, match='access'):
        broker.call(9876, 'digest')
    with pytest.raises(ValueError, match='unexpected'):
        broker.call(1234, 'install')
    broker.call(1234, 'intent')
    with pytest.raises(ValueError, match='evidence'):
        broker.call(1234, 'install')
    state.update(journal=broker.new, receipt=broker.plan_sha)
    broker.call(1234, 'install')
    broker.call(1234, 'complete')
    assert files.digest() == broker.new
    with pytest.raises(ValueError, match='unexpected'):
        broker.call(1234, 'install')


def test_broker_refuses_restarted_runtime_or_revoked_evidence(tmp_path, policy):
    broker, files, state = fixture(tmp_path, policy)
    broker.call(1234, 'intent')
    state.update(journal=broker.new, receipt=broker.plan_sha, stopped=False)
    with pytest.raises(ValueError, match='stopped'):
        broker.call(1234, 'install')
    state.update(stopped=True, evidence=False)
    with pytest.raises(ValueError, match='evidence'):
        broker.call(1234, 'install')
    assert files.digest() == broker.old
