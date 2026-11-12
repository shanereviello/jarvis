import importlib.util
from pathlib import Path
import sqlite3
import pytest
from test_reporting_onboarding_admission import inputs,policy
from test_reporting_codex_runtime import m

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/codex_issue_admission_migration.py'
spec=importlib.util.spec_from_file_location('issue_admission_migration_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_offline_one_issue_admission_is_audited_and_preserves_prior_state(tmp_path,policy):
    current,request=inputs(tmp_path,policy);root=tmp_path/'state'
    runtime=m.Runtime(root,current,create=True,issue_client_factory=lambda *_:None);runtime.close()
    checks=[]
    def evidence(v):checks.append(('evidence',v['issue_id']));return True
    def authority(v):checks.append(('authority',v['issue_id']));return True
    plan=module.plan(root,request,evidence,authority)
    with pytest.raises(ValueError,match='plan differs'):module.apply(root,request,evidence,authority,'0'*64)
    result=module.apply(root,request,evidence,authority,plan['expected_sha256'])
    assert result['journal_updated'] and not result['policy_installed'] and result['models_started']==0
    recovered=module.reconcile(root,request,plan['expected_sha256'])
    assert recovered['retained'] and recovered['current_issue_pins_match'] and recovered['current_policy_matches']
    with pytest.raises(ValueError):module.reconcile(root,dict(request,baseline_commit='0'*40),plan['expected_sha256'])
    assert len(checks)==6
    with sqlite3.connect(root/'runtime.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM policy_issue_admissions').fetchone()[0]==1
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM policy_issue_admissions')
    with pytest.raises(ValueError,match='already admitted'):module.plan(root,request,evidence,authority)


def test_admission_refuses_unverified_or_unsettled_runtime(tmp_path,policy):
    current,request=inputs(tmp_path,policy);root=tmp_path/'state'
    active=m.Runtime(root,current,create=True,issue_client_factory=lambda *_:None)
    with pytest.raises(ValueError,match='stop the runtime'):module.plan(root,request,lambda _:True,lambda _:True)
    active.close()
    with pytest.raises(ValueError,match='execution evidence'):module.plan(root,request,lambda _:False,lambda _:True)
    with pytest.raises(ValueError,match='execution authority'):module.plan(root,request,lambda _:True,lambda _:False)
