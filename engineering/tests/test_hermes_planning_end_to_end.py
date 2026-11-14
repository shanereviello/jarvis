"""Disposable owned-history acceptance; external Linear reads are fixtures."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sqlite3

from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO,history,module


def load(name):
    path=Path(__file__).resolve().parents[1]/'tools/rras_reporting'/(name+'.py')
    spec=importlib.util.spec_from_file_location('hermes_e2e_'+name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def test_jarvis_draft_issue_and_review_never_grant_authority(tmp_path,setup_draft):
    _,fixture,old_origin,proposal=setup_draft
    origin=dict(old_origin,agent='jarvis');session=origin['source_session']
    native=dict(organization_id=origin['organization_id'],session_id=session,
        hermes_session_id='linear:'+origin['organization_id']+':'+session,run_id='run_'+'a'*32)
    access=module('access').Access(fixture.projects.store,dict(contract='engineering-history-access.v3',principals=[
        dict(uid=1234,private_read=['jarvis'],write=[],category_read=[],category_write=[],planning_agent='jarvis',
             planning_organization_id=origin['organization_id'],planning_teams=[origin['team_id']],planning_repositories=['jarvis'],planning_categories=[])]))
    rpc=lambda message:access.dispatch(1234,message)
    adapter=history.HistoryAdapter(rpc,lambda org,project:rpc(dict(method='planning_binding',organization_id=org,linear_project_id=project)),
        lambda org,linear,team,project,scope:rpc(dict(method='planning_reserve',organization_id=org,linear_project_id=linear,team_id=team,project_id=project,scope=scope)),[REPO])
    @contextmanager
    def journal():
        db=sqlite3.connect(tmp_path/'issues.sqlite3')
        try:yield db
        finally:db.close()
    issue_journal=load('onboarding_issue_journal').IssueJournal(journal)
    with journal() as db:issue_journal.initialize(db)
    issue=dict(organization_id=origin['organization_id'],team_id=origin['team_id'],project_id=origin['project_id'],
        id=uid(6),identifier='ENG-1',url='https://linear.app/fixture/issue/ENG-1')
    grants={1234:dict(agent='jarvis',organization_id=origin['organization_id'],team_id=origin['team_id'],scopes=[REPO])}
    calls=[];broker_module=load('hermes_planning_broker')
    broker=broker_module.Broker(grants,lambda peer,run:origin,lambda run,selected,key:issue,adapter,issue_journal=issue_journal,
        issue_create=lambda run,selected,plan,body:calls.append(body) or issue['id'])
    dispatch=broker_module.dispatch_id(native)
    def submit(operation,**values):return broker.submit(1234,dict(contract='hermes-planning-submit.v1',native=native,
        message=dict(operation=operation,dispatch_id=dispatch,**values)))
    draft=submit('draft.project',proposal=proposal)
    work=dict(plan_id='PLAN-01',title='Investigation',objective='Determine behavior',rationale='Draft work',
        allowed_paths=['engineering'],acceptance_criteria=[dict(id='PLAN-01-AC1',description='Verify behavior')])
    first=submit('draft.issue',proposal=work)
    assert first['state']=='complete' and submit('draft.issue',proposal=work)==first and len(calls)==1
    assert draft['execution_authorized'] is False and first['execution_authorized'] is False
    assert fixture.project(REPO,draft['project_id'])['governing_version'] is None
    @contextmanager
    def reviews():
        db=sqlite3.connect(tmp_path/'reviews.sqlite3')
        try:yield db
        finally:db.close()
    with reviews() as db:load('onboarding_review_store').ReviewStore.initialize(db)
    class History:
        def project(self,scope,pid):return fixture.project(scope,pid)
        def architecture(self,scope,pid,version):
            return fixture.projects.read(scope,dict(view='architecture',project_id=pid,version=version))['document']
    review=load('hermes_planning_review_broker').Broker(1234,lambda peer,run:origin,
        lambda run,selected,key:issue,reviews,History(),[REPO],origin['team_id'])
    result=review.dispatch(1234,dict(operation='review.prepare',native=native,issue_id=issue['id'],version=1))
    assert result['markdown_sha256']==draft['markdown_sha256']
    assert result['human_approval_inferred'] is False and result['execution_authorized'] is False
    assert fixture.project(REPO,draft['project_id'])['governing_version'] is None
