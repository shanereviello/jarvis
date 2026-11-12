import copy
import importlib.util
from pathlib import Path
import pytest
from test_reporting_codex_runtime import policy,uid

root=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
def load(name):
    spec=importlib.util.spec_from_file_location('admission_test_'+name,root/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def inputs(tmp_path,policy):
    d=load('onboarding_drafts');org=uid(1);project=uid(10);issue=uid(11);plan='PLAN-01'
    policy=copy.deepcopy(policy);policy['contract']='codex-runtime-policy.v2'
    policy['workspaces']={uid(3):str(tmp_path/'old')}
    policy['native_sockets']={uid(3):str(tmp_path/('coding-'+uid(3)+'.sock'))}
    request=dict(issue_id=issue,organization_id=org,linear_project_id=project,team_id=uid(12),
        scope={'kind':'repository','id':'jarvis'},project_id=d.identity('prj_',org,project),
        work_id=d.work_identity('wrk_',org,project,plan),plan_id=plan,work_revision_sha256='a'*64,
        assignment_sha256='b'*64,architecture_version=1,architecture_sha256='c'*64,decision_receipt_sha256='d'*64,
        workspace=str(tmp_path/'new'),native_socket=str(tmp_path/('coding-'+issue+'.sock')),baseline_commit='e'*40)
    return policy,request


def test_candidate_requires_verified_exact_pins_and_preserves_existing_authority(tmp_path,policy):
    current,request=inputs(tmp_path,policy);original=copy.deepcopy(current);seen=[]
    result=load('onboarding_admission').candidate(current,request,lambda value:seen.append(value) or True)
    assert current==original and not result['policy_installed'] and not result['execution_authority_changed']
    assert result['policy']['execution_authorized']==current['execution_authorized']
    assert result['policy']['issues'][request['issue_id']]['architecture_sha256']==request['architecture_sha256']
    assert seen==[request]
    with pytest.raises(ValueError):load('onboarding_admission').candidate(current,request,lambda _:False)


@pytest.mark.parametrize('change',['scope','identity','digest','workspace','socket'])
def test_candidate_refuses_unverified_or_cross_workspace_admission(tmp_path,policy,change):
    current,request=inputs(tmp_path,policy)
    if change=='scope':request['scope']={'kind':'non_git','id':'jarvis-non-git'}
    elif change=='identity':request['work_id']='wrk_'+'0'*32
    elif change=='digest':request['decision_receipt_sha256']='not-a-digest'
    elif change=='workspace':request['workspace']=current['workspaces'][uid(3)]
    else:request['native_socket']=current['native_sockets'][uid(3)]
    with pytest.raises(ValueError):load('onboarding_admission').candidate(current,request,lambda _:True)
