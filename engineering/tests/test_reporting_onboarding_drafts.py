"""Disposable owned-history tests for the non-networked v0.5 draft boundary."""
import copy
import importlib.util
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from test_history_projects import projects, REPO
from test_history_reporting_contract import request
from test_engineering_history_local import module, store
from test_engineering_history_unix import env, running, rpc


PATH = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/onboarding_drafts.py'
spec = importlib.util.spec_from_file_location('onboarding_drafts_fixture', PATH)
drafts = importlib.util.module_from_spec(spec);spec.loader.exec_module(drafts)
spec = importlib.util.spec_from_file_location('onboarding_history_fixture', PATH.with_name('onboarding_history.py'))
history = importlib.util.module_from_spec(spec);spec.loader.exec_module(history)


def uid(n): return str(uuid.UUID(int=n))


class FixtureStore:
    """Trusted test adapter; production transport and origin verification remain unimplemented."""
    def __init__(self, projects):
        self.projects=projects
        scopes=module('scopes').Scopes(projects.store);scopes.migrate(scopes.migration_plan()['expected_sha256'])
        self.reporting=module('reporting').Reporting(projects.store)
        self.reporting.migrate(self.reporting.migration_plan()['expected_sha256'])
        evidence=module('evidence').Evidence(projects.store);evidence.migrate(evidence.migration_plan()['expected_sha256'])
        self.reservations=module('onboarding_reservations').Reservations(projects.store)
        self.reservations.migrate(self.reservations.migration_plan()['expected_sha256'])
        self.fail_after_save=False
        self.fail_after_mapping=False

    def reserve(self,origin,project_id):
        return self.reservations.reserve(origin['organization_id'],origin['project_id'],origin['team_id'],project_id,origin['scope'])

    def binding(self, organization, linear_project):
        with self.projects.store.connection() as db: rows=self.reporting.events(db)
        matches=[r for r,_ in rows if r['operation']=='mapping.record' and r['body']['kind']=='project'
                 and r['body']['linear']['organization_id']==organization and r['body']['linear']['project_id']==linear_project]
        if len(matches)>1:raise ValueError('conflicting bindings')
        if not matches:return None
        r=matches[0]
        return dict(project_id=r['context']['project_id'],scope=r['scope'],team_id=r['body']['linear']['team_id'])

    def project(self, scope, project_id):
        listing=self.projects.read(scope,dict(view='projects',limit=50,offset=0))
        if listing['has_more']:raise ValueError('incomplete fixture enumeration')
        if not any(item['project_id']==project_id for item in listing['items']):return None
        return self.projects.read(scope,dict(view='project',project_id=project_id))['project']

    def submit_project(self, value):
        result=self.projects.submit(value,peer_uid=1234)
        if self.fail_after_save and value['operation']=='architecture.save':
            self.fail_after_save=False
            raise OSError('simulated lost response after commit')
        return result

    def submit_mapping(self, origin, project_id, document_id, digest):
        value=request('mapping.record')
        value.update(client_event_key='onboard-map:'+project_id,scope=origin['scope'],
                     source=dict(kind='agent_reported',namespace='fixture',id=origin['source_session']),
                     context=dict(project_id=project_id,architecture=dict(document_id=document_id,version=1,markdown_sha256=digest),work=None))
        value['body'].update(mapping_id=drafts.identity('map_',origin['organization_id'],origin['project_id']),
            kind='project',plan_id=None,linear=dict(organization_id=origin['organization_id'],team_id=origin['team_id'],
            project_id=origin['project_id'],issue_id=None,identifier='P-ENG-1',url=origin['project_url']))
        result=self.reporting.submit(value,peer_uid=1234)
        if self.fail_after_mapping:
            self.fail_after_mapping=False
            raise OSError('simulated lost mapping response after commit')
        return result


@pytest.fixture
def setup_draft(projects):
    store=FixtureStore(projects)
    origin=dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),project_identifier='P-ENG-1',project_url='https://linear.app/fixture/project/example',
                scope=REPO,source_session=uid(4),source_actor=uid(5),agent='codex')
    grants={1234:dict(agent='codex',organization_id=uid(1),team_id=uid(2),scopes=[REPO])}
    data=dict(name='Fixture project',overview='An investigation',intended_outcome='Retained knowledge',in_scope='Engineering',
              out_of_scope='Unrelated work',markdown='# Architecture\n\n## PLAN-01\n\nInvestigate.\n',plan_ids=['PLAN-01'])
    writer=drafts.DraftWriter(grants,lambda evidence:origin,store)
    return writer,store,origin,data


def test_exact_draft_and_mapping_retained_without_governing_design(setup_draft):
    writer,store,origin,data=setup_draft
    first=writer.save(1234,object(),data);second=writer.save(1234,object(),data)
    assert first==second and first['designation']=='draft' and first['execution_authorized'] is False
    project=store.project(REPO,first['project_id'])
    assert project['governing_version'] is None
    assert project['architecture'][0]['markdown_sha256']==first['markdown_sha256']
    assert store.binding(uid(1),uid(3))['project_id']==first['project_id']


def test_lost_save_response_is_reconciled_without_duplicate(setup_draft):
    writer,store,origin,data=setup_draft;store.fail_after_save=True
    with pytest.raises(OSError,match='lost response'):writer.save(1234,object(),data)
    result=writer.save(1234,object(),data)
    project=store.project(REPO,result['project_id'])
    assert len(project['architecture'])==1 and project['governing_version'] is None


def test_lost_mapping_response_is_reconciled_from_a_new_session(setup_draft):
    writer,store,origin,data=setup_draft;store.fail_after_mapping=True
    with pytest.raises(OSError,match='lost mapping response'):writer.save(1234,object(),data)
    writer.verify_origin=lambda evidence:dict(origin,source_session=uid(77))
    result=writer.save(1234,object(),data)
    assert store.binding(uid(1),uid(3))['project_id']==result['project_id']
    with store.projects.store.connection() as db:
        assert len([r for r,_ in store.reporting.events(db) if r['operation']=='mapping.record'])==1


@pytest.mark.parametrize('change',['peer','scope','agent','team','draft','plan','project_url'])
def test_untrusted_or_conflicting_input_is_refused_before_writing(setup_draft,change):
    writer,store,origin,data=setup_draft;origin=copy.deepcopy(origin);data=copy.deepcopy(data);peer=1234
    if change=='peer':peer=9999
    elif change=='scope':origin['scope']={'kind':'repository','id':'other'}
    elif change=='agent':origin['agent']='jarvis'
    elif change=='team':origin['team_id']=uid(50)
    elif change=='draft':data['approval']=True
    elif change=='plan':data['plan_ids']=['PLAN-02']
    else:origin['project_url']='https://linear.app/fixture/project?secret=x'
    writer.verify_origin=lambda evidence:origin
    with pytest.raises(ValueError):writer.save(peer,object(),data)
    assert store.project(REPO,drafts.identity('prj_',uid(1),uid(3))) is None


def test_changed_draft_requires_explicit_revision_and_never_designates(setup_draft):
    writer,store,origin,data=setup_draft;result=writer.save(1234,object(),data)
    changed=dict(data,markdown=data['markdown']+'Changed.\n')
    with pytest.raises(ValueError,match='draft differs'):writer.save(1234,object(),changed)
    assert store.project(REPO,result['project_id'])['governing_version'] is None


def test_history_adapter_uses_real_access_dispatch_and_keeps_design_undesignated(setup_draft):
    writer,fixture,origin,data=setup_draft
    access=module('access').Access(fixture.projects.store,dict(contract='engineering-history-access.v3',principals=[
        dict(uid=1234,private_read=['jarvis'],write=[],category_read=[],category_write=[],
             planning_agent='codex',planning_organization_id=uid(1),planning_teams=[uid(2)],planning_repositories=['jarvis'],planning_categories=[])]))
    rpc=lambda message:access.dispatch(1234,message)
    adapter=history.HistoryAdapter(rpc,lambda organization,project:rpc(dict(method='planning_binding',organization_id=organization,linear_project_id=project)),
        lambda org,linear,team,project,scope:rpc(dict(method='planning_reserve',organization_id=org,linear_project_id=linear,team_id=team,project_id=project,scope=scope)),[REPO])
    writer.store=adapter
    first=writer.save(1234,object(),data)
    assert writer.save(1234,object(),data)==first
    assert adapter.project(REPO,first['project_id'])['governing_version'] is None
    assert adapter.binding(uid(1),uid(3))['project_id']==first['project_id']
    with pytest.raises(ValueError,match='draft operations only'):
        adapter.submit_project(dict(operation='architecture.designate',scope=REPO))
    project=adapter.project(REPO,first['project_id'])
    from test_history_projects import envelope
    designate=envelope(first['project_id'],'architecture.designate',
        dict(version=1,markdown_sha256=first['markdown_sha256'],reason='forged'),project['head'])
    designate['source']=dict(kind='agent_reported',namespace='linear_codex',id=uid(4))
    for method in ('project_submit','planning_project_submit'):
        with pytest.raises(ValueError):access.dispatch(1234,dict(method=method,request=designate))
    for organization,team in ((uid(99),uid(2)),(uid(1),uid(99))):
        with pytest.raises(ValueError):
            access.dispatch(1234,dict(method='planning_reserve',organization_id=organization,linear_project_id=uid(3),
                team_id=team,project_id=drafts.identity('prj_',organization,uid(3)),scope=REPO))
    from test_history_scopes import envelope as scope_envelope
    with pytest.raises(ValueError):access.dispatch(1234,dict(method='scope_submit',request=scope_envelope()))
    with pytest.raises(ValueError,match='scope refused'):
        adapter.project(dict(kind='repository',id='other'),first['project_id'])
    with pytest.raises(ValueError,match='planning binding unavailable'):
        fixture.reporting.planning_project_binding(uid(1),uid(3),[{'kind':'repository','id':'other'}])
    assert fixture.reporting.planning_project_binding(uid(1),uid(33),[REPO]) is None


@pytest.mark.parametrize('field',['write','private_read','agent'])
def test_planning_identity_cannot_receive_broader_privileges(setup_draft,field):
    _,fixture,_,_=setup_draft
    entry=dict(uid=1234,private_read=['jarvis'],write=[],category_read=[],category_write=[],
               planning_agent='codex',planning_organization_id=uid(1),planning_teams=[uid(2)],planning_repositories=['jarvis'],planning_categories=[])
    if field=='write':entry['write']=['jarvis']
    elif field=='private_read':entry['private_read'].append('other')
    else:entry['planning_agent']=None
    with pytest.raises(ValueError):
        module('access').Access(fixture.projects.store,dict(contract='engineering-history-access.v3',principals=[entry]))


def test_global_conflict_never_returns_cross_scope_details(setup_draft):
    writer,fixture,origin,data=setup_draft
    adapter=history.HistoryAdapter(lambda message:None,
        lambda organization,project:dict(project_id='prj_'+'f'*32,team_id=uid(2),scope={'kind':'repository','id':'other'}),
        lambda *args:None,[REPO])
    with pytest.raises(ValueError,match='scope refused'):
        adapter.binding(uid(1),uid(3))


def test_concurrent_conflicting_reservations_have_one_winner(setup_draft):
    writer,fixture,origin,data=setup_draft
    def attempt(project):
        try:return fixture.reservations.reserve(uid(1),uid(3),uid(2),project,REPO)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,['prj_'+'a'*32,'prj_'+'b'*32]))
    assert sum(value is not None for value in results)==1


def test_reservation_blocks_conflicting_project_mapping(setup_draft):
    writer,fixture,origin,data=setup_draft
    fixture.reservations.reserve(uid(1),uid(3),uid(2),'prj_'+'f'*32,REPO)
    with pytest.raises(ValueError,match='planning binding unavailable'):
        writer.save(1234,object(),data)
    assert fixture.binding(uid(1),uid(3)) is None


def test_reservations_are_append_only_and_replayable(setup_draft):
    writer,fixture,origin,data=setup_draft;project='prj_'+'e'*32
    first=fixture.reservations.reserve(uid(1),uid(3),uid(2),project,REPO)
    assert first['inserted'] and not fixture.reservations.reserve(uid(1),uid(3),uid(2),project,REPO)['inserted']
    with fixture.projects.store.connection() as db:
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM onboarding_reservations')


def test_planning_over_actual_unix_transport_does_not_grant_designation(env):
    import os
    _,store,_=env
    projects=module('projects').Projects(store);projects.migrate(projects.migration_plan()['expected_sha256'])
    scopes=module('scopes').Scopes(store);scopes.migrate(scopes.migration_plan()['expected_sha256'])
    reporting=module('reporting').Reporting(store);reporting.migrate(reporting.migration_plan()['expected_sha256'])
    evidence=module('evidence').Evidence(store);evidence.migrate(evidence.migration_plan()['expected_sha256'])
    reservations=module('onboarding_reservations').Reservations(store);reservations.migrate(reservations.migration_plan()['expected_sha256'])
    peer=os.getuid();grants=dict(contract='engineering-history-access.v3',principals=[dict(uid=peer,
        private_read=['jarvis'],write=[],category_read=[],category_write=[],planning_agent='codex',
        planning_organization_id=uid(1),planning_teams=[uid(2)],planning_repositories=['jarvis'],planning_categories=[])])
    origin=dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),project_identifier='P-ENG-1',
        project_url='https://linear.app/fixture/project/example',scope=REPO,source_session=uid(4),source_actor=uid(5),agent='codex')
    value=dict(name='Fixture project',overview='An investigation',intended_outcome='Retained knowledge',in_scope='Engineering',
        out_of_scope='Unrelated work',markdown='# Architecture\n\n## PLAN-01\n\nInvestigate.\n',plan_ids=['PLAN-01'])
    with running(env,grants) as server:
        call=lambda message:rpc(server,message)
        adapter=history.HistoryAdapter(call,
            lambda org,project:call(dict(method='planning_binding',organization_id=org,linear_project_id=project)),
            lambda org,linear,team,project,scope:call(dict(method='planning_reserve',organization_id=org,linear_project_id=linear,team_id=team,project_id=project,scope=scope)),[REPO])
        writer=drafts.DraftWriter({peer:dict(agent='codex',organization_id=uid(1),team_id=uid(2),scopes=[REPO])},lambda evidence:origin,adapter)
        result=writer.save(peer,object(),value)
        assert result['designation']=='draft' and result['execution_authorized'] is False
        project=adapter.project(REPO,result['project_id'])
        assert project['governing_version'] is None
        from test_history_projects import envelope
        forged=envelope(result['project_id'],'architecture.designate',dict(version=1,markdown_sha256=result['markdown_sha256'],reason='forged'),project['head'])
        with pytest.raises(ValueError):call(dict(method='planning_project_submit',request=forged))
