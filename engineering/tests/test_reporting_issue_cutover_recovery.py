import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/codex_issue_cutover_recovery.py'
spec=importlib.util.spec_from_file_location('cutover_recovery_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


@pytest.mark.parametrize('journal,file,expected',[('a','a','not_started'),('b','b','consistent_new'),('b','a','journal_ahead'),('a','b','file_ahead'),('c','a','conflict')])
def test_only_classifies_without_changing_state(journal,file,expected):
    result=module.classify(old_policy_sha256='a'*64,new_policy_sha256='b'*64,journal_policy_sha256=journal*64,
                           file_policy_sha256=file*64,runtime_stopped=True)
    assert result['state']==expected and not result['automatic_change'] and not result['automatic_retry']


def test_refuses_running_runtime_or_ambiguous_transition():
    values=dict(old_policy_sha256='a'*64,new_policy_sha256='b'*64,journal_policy_sha256='a'*64,file_policy_sha256='a'*64)
    with pytest.raises(ValueError):module.classify(**values,runtime_stopped=False)
    with pytest.raises(ValueError):module.classify(**dict(values,new_policy_sha256='a'*64),runtime_stopped=True)
