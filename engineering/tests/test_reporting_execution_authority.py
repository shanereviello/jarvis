from datetime import datetime,timezone
import copy
import importlib.util
from pathlib import Path
import pytest
from test_reporting_onboarding_admission import inputs,policy

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_execution_authority.py'
spec=importlib.util.spec_from_file_location('execution_authority_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def grant(value):
    return dict(grant_id='approved-project',organization_id=value['organization_id'],linear_project_id=value['linear_project_id'],
        project_id=value['project_id'],repository_id=value['scope']['id'],architecture_version=value['architecture_version'],
        architecture_sha256=value['architecture_sha256'],issue_ids=None,authorization_reference='Operator scoped project authorization',expires_at=None)


def test_scoped_project_grant_does_not_require_reapproval_per_mapped_issue(tmp_path,policy):
    current,value=inputs(tmp_path,policy);record=grant(value);v=module.Verifier(dict(contract='codex-execution-grants.v1',grants=[record]))
    result=v(value);assert result['authorized'] and result['grant_id']=='approved-project' and len(result['policy_sha256'])==64
    other=dict(value,issue_id='00000000-0000-4000-8000-000000000099');assert v(other)['authorized']
    # The caller must independently verify each issue's exact history mapping.
    for key in ('organization_id','linear_project_id','project_id','architecture_sha256'):
        assert v(dict(value,**{key:'different'})) is False
    assert v(dict(value,scope={'kind':'repository','id':'other'})) is False


def test_issue_list_expiry_and_ambiguous_grants_refuse(tmp_path,policy):
    _,value=inputs(tmp_path,policy);record=grant(value);record['issue_ids']=[value['issue_id']];record['expires_at']='2030-01-01T00:00:00Z'
    at=lambda year:lambda:datetime(year,1,1,tzinfo=timezone.utc)
    v=module.Verifier(dict(contract='codex-execution-grants.v1',grants=[record]),clock=at(2029))
    assert v(value)['authorized'] and v(dict(value,issue_id='00000000-0000-4000-8000-000000000099')) is False
    assert module.Verifier(dict(contract='codex-execution-grants.v1',grants=[record]),clock=at(2030))(value) is False
    overlap=copy.deepcopy(record);overlap['grant_id']='second'
    assert module.Verifier(dict(contract='codex-execution-grants.v1',grants=[record,overlap]),clock=at(2029))(value) is False
    with pytest.raises(ValueError):module.Verifier(dict(contract='codex-execution-grants.v1',grants=[record,record]))


def test_scoped_grant_is_retained_in_offline_admission_audit(tmp_path,policy):
    from test_reporting_codex_issue_admission_migration import module as migration
    from test_reporting_codex_runtime import m
    import json,sqlite3
    current,value=inputs(tmp_path,policy);root=tmp_path/'journal'
    runtime=m.Runtime(root,current,create=True,issue_client_factory=lambda *_:None);runtime.close()
    authority=module.Verifier(dict(contract='codex-execution-grants.v1',grants=[grant(value)]))
    plan=migration.plan(root,value,lambda _:True,authority)
    assert plan['authority']['policy_sha256']==authority.sha
    migration.apply(root,value,lambda _:True,authority,plan['expected_sha256'])
    with sqlite3.connect(root/'runtime.sqlite3') as db:
        retained=json.loads(db.execute('SELECT authority_body FROM policy_issue_admissions').fetchone()[0])
    assert retained['grant_id']=='approved-project' and retained['policy_sha256']==authority.sha
