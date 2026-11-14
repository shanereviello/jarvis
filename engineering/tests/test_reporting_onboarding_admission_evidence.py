"""Admission requires independently checked current evidence, not assertions."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import pytest
from test_reporting_onboarding_admission import inputs,policy

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_admission_evidence.py'
spec=importlib.util.spec_from_file_location('admission_evidence_test',path)
evidence=importlib.util.module_from_spec(spec);spec.loader.exec_module(evidence)


def fixture(tmp_path,policy):
    current,v=inputs(tmp_path,policy);markdown='# Approved architecture\n';v['architecture_sha256']=hashlib.sha256(markdown.encode()).hexdigest()
    arch=dict(document_id='doc_'+'a'*32,version=1,markdown_sha256=v['architecture_sha256'])
    source=dict(kind='imported',namespace='operator_decision',id=v['decision_receipt_sha256'])
    project=dict(scope=v['scope'],governing_version=1,architecture=[arch],designations=[dict(version=1,markdown_sha256=v['architecture_sha256'],source=source)])
    assignment=dict(project_id=v['project_id'],architecture_version=1,assignment_sha256=v['assignment_sha256'])
    work=dict(work_revision_sha256=v['work_revision_sha256'],work=dict(repository_id='jarvis'),assignment=assignment)
    decision=dict(submission=dict(body=dict(decision_id='decision',kind='architecture',state='approved'),context=dict(project_id=v['project_id'],architecture=arch)),receipt=dict(request_sha256=v['decision_receipt_sha256']))
    mapping=dict(submission=dict(body=dict(kind='execution',plan_id=v['plan_id'],linear=dict(organization_id=v['organization_id'],team_id=v['team_id'],project_id=v['linear_project_id'],issue_id=v['issue_id'])),
        context=dict(architecture=arch,work=dict(work_item_id=v['work_id'],work_revision_sha256=v['work_revision_sha256'],assignment_sha256=v['assignment_sha256']))))
    pages=dict(project=project,architecture=dict(markdown=markdown),work=work,decision=decision,mapping=mapping)
    def rpc(request):
        q=request['query'];view=q['view'];base=dict(snapshot='fixed')
        if view=='project':return dict(base,project=pages['project'])
        assert q['snapshot']=='fixed'
        if view=='architecture':return dict(base,document=pages['architecture'])
        if view=='work':return dict(base,**pages['work'])
        selected=pages['decision'] if q['operation']=='decision.observe' else pages['mapping']
        return dict(base,items=selected if isinstance(selected,list) else [selected],available=True,has_more=False,next_offset=1)
    native={k:v[k] for k in ('organization_id','team_id','linear_project_id','issue_id')}
    return v,pages,rpc,native


def test_valid_snapshot_and_independent_checks(tmp_path,policy):
    v,pages,rpc,native=fixture(tmp_path,policy)
    verifier=evidence.Verifier(rpc,lambda _:native,lambda _:True,lambda _:True)
    assert verifier(v) is True


@pytest.mark.parametrize('change',['designation','document','assignment','revision','decision','revoked','mapping','linear','human','workspace'])
def test_refuses_stale_or_unverified_evidence(tmp_path,policy,change):
    v,pages,rpc,native=fixture(tmp_path,policy)
    human=lambda _:True;workspace=lambda _:True
    if change=='designation':pages['project']['designations'][0]['source']['id']='0'*64
    elif change=='document':pages['architecture']['markdown']='changed'
    elif change=='assignment':pages['work']['assignment']['architecture_version']=2
    elif change=='revision':pages['work']['work_revision_sha256']='0'*64
    elif change=='decision':pages['decision']['submission']['body']['state']='rejected'
    elif change=='revoked':
        newer=copy.deepcopy(pages['decision']);newer['receipt']['request_sha256']='f'*64;newer['submission']['body']['state']='rejected'
        pages['decision']=[newer,pages['decision']]
    elif change=='mapping':pages['mapping']['submission']['body']['linear']['issue_id']='wrong'
    elif change=='linear':native['team_id']='wrong'
    elif change=='human':human=lambda _:False
    else:workspace=lambda _:False
    with pytest.raises(ValueError):evidence.Verifier(rpc,lambda _:native,human,workspace)(v)


def test_actual_history_snapshot_and_receipts_are_compatible(setup_work):
    from test_reporting_onboarding_decisions import decisions,evidence_for
    from test_reporting_onboarding_drafts import REPO,module
    writer,history,origin,issue,detail,draft,access=setup_work
    work=writer.save(1234,object(),object(),detail)
    observed=evidence_for(history,draft)
    grants=dict(contract='engineering-history-access.v3',principals=[dict(uid=999,private_read=['jarvis'],write=['jarvis'],
        category_read=[],category_write=[],planning_agent=None,planning_organization_id=None,planning_teams=[],planning_repositories=[],planning_categories=[])])
    operator_access=module('access').Access(history.projects.store,grants)
    operator_path=path.with_name('onboarding_operator_history.py')
    operator_spec=importlib.util.spec_from_file_location('admission_operator_fixture',operator_path)
    operator=importlib.util.module_from_spec(operator_spec);operator_spec.loader.exec_module(operator)
    adapter=operator.Adapter(lambda request:operator_access.dispatch(999,request),[REPO])
    approved=decisions.DecisionRecorder(lambda _:observed,adapter,[REPO]).approve(object())
    retained=writer.store.work(REPO,work['work_id'])
    value=dict(organization_id=origin['organization_id'],team_id=origin['team_id'],linear_project_id=origin['project_id'],
        issue_id=issue['id'],scope=REPO,project_id=draft['project_id'],work_id=work['work_id'],plan_id=detail['plan_id'],
        work_revision_sha256=retained['work_revision_sha256'],assignment_sha256=retained['assignment']['assignment_sha256'],
        architecture_version=1,architecture_sha256=draft['markdown_sha256'],decision_receipt_sha256=approved['decision_receipt_sha256'],
        workspace='/fixture/workspace',native_socket='/fixture/socket',baseline_commit='e'*40)
    def rpc(request):return history.projects.read(request['scope'],request['query'])
    native={k:value[k] for k in ('organization_id','team_id','linear_project_id','issue_id')}
    assert evidence.Verifier(rpc,lambda _:native,lambda _:True,lambda _:True)(value)

from test_reporting_onboarding_work import setup_work
from test_reporting_onboarding_drafts import setup_draft,store,projects
