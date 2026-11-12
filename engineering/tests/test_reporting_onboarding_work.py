"""Draft work mapping is distinct from human agreement and execution."""
import copy
import importlib.util
from pathlib import Path
import pytest
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO,history,module

PATH=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_work.py'
spec=importlib.util.spec_from_file_location('onboarding_work_fixture',PATH)
work=importlib.util.module_from_spec(spec);spec.loader.exec_module(work)


@pytest.fixture
def setup_work(setup_draft):
    initial,fixture,origin,data=setup_draft
    access=module('access').Access(fixture.projects.store,dict(contract='engineering-history-access.v3',principals=[
        dict(uid=1234,private_read=['jarvis'],write=[],category_read=[],category_write=[],planning_agent='codex',
             planning_organization_id=uid(1),planning_teams=[uid(2)],planning_repositories=['jarvis'],planning_categories=[])]))
    rpc=lambda message:access.dispatch(1234,message)
    adapter=history.HistoryAdapter(rpc,lambda org,project:rpc(dict(method='planning_binding',organization_id=org,linear_project_id=project)),
        lambda org,linear,team,project,scope:rpc(dict(method='planning_reserve',organization_id=org,linear_project_id=linear,team_id=team,project_id=project,scope=scope)),[REPO])
    initial.store=adapter;draft=initial.save(1234,object(),data)
    issue=dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),id=uid(6),identifier='ENG-1',url='https://linear.app/fixture/issue/ENG-1')
    detail=dict(plan_id='PLAN-01',title='Investigation',objective='Determine the behavior',rationale='Draft work item',
                allowed_paths=['engineering'],acceptance_criteria=[dict(id='PLAN-01-AC1',description='Verify behavior')])
    grants={1234:dict(agent='codex',organization_id=uid(1),team_id=uid(2),scopes=[REPO])}
    writer=work.DraftWorkWriter(grants,lambda evidence:origin,lambda evidence:issue,adapter)
    return writer,fixture,origin,issue,detail,draft,access


def test_draft_work_is_mapped_but_cannot_authorize_execution(setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    first=writer.save(1234,object(),object(),detail)
    assert writer.save(1234,object(),object(),detail)==first
    assert first['designation']=='draft' and first['execution_authorized'] is False
    assert fixture.project(REPO,draft['project_id'])['governing_version'] is None
    stored=writer.store.work(REPO,first['work_id'])
    assert stored['assignment']['architecture_version']==1
    assert writer.store.issue_binding(origin,issue['id'])['plan_id']=='PLAN-01'


@pytest.mark.parametrize('change',['issue_project','issue_team','plan','peer','scope'])
def test_foreign_or_unplanned_work_is_refused(setup_work,change):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    issue=copy.deepcopy(issue);detail=copy.deepcopy(detail);peer=1234
    if change=='issue_project':issue['project_id']=uid(99)
    elif change=='issue_team':issue['team_id']=uid(99)
    elif change=='plan':detail['plan_id']='OTHER-01'
    elif change=='peer':peer=9999
    else:writer.verify_origin=lambda evidence:dict(origin,scope={'kind':'repository','id':'other'})
    writer.verify_issue=lambda evidence:issue
    with pytest.raises(ValueError):writer.save(peer,object(),object(),detail)
    assert fixture.project(REPO,draft['project_id'])['governing_version'] is None


def test_planning_peer_cannot_create_unplanned_work_by_calling_history_directly(setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    from test_engineering_history_local import request
    value=request();value['body']['repository_id']='jarvis'
    value['source']=dict(kind='agent_reported',namespace='linear_codex',id=uid(4))
    with pytest.raises(ValueError):
        access.dispatch(1234,dict(method='planning_work_submit',project_id=draft['project_id'],plan_id='OTHER-01',request=value))


def test_invalid_work_does_not_consume_identity(setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    invalid=copy.deepcopy(detail);invalid['allowed_paths']=['../outside']
    with pytest.raises(ValueError):writer.save(1234,object(),object(),invalid)
    with fixture.projects.store.connection() as db:
        assert db.execute('SELECT count(*) FROM onboarding_work_reservations').fetchone()[0]==0
    assert writer.save(1234,object(),object(),detail)['execution_authorized'] is False


def test_same_plan_cannot_be_rebound_to_another_issue(setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    writer.save(1234,object(),object(),detail)
    writer.verify_issue=lambda evidence:dict(issue,id=uid(7),identifier='ENG-2')
    with pytest.raises(ValueError,match='planning binding unavailable'):
        writer.save(1234,object(),object(),detail)
