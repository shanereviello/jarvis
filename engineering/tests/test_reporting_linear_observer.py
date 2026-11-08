"""Passive paginated imports, exact ownership and outage/replay semantics."""
import copy
import importlib.util
from pathlib import Path
from test_reporting_capture_intake import store,projects,evidence,reporting,spool,sender,events
from test_history_reporting import request

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
spec=importlib.util.spec_from_file_location('observer_test',ROOT/'linear_observer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
P='00000000-0000-4000-8000-000000000001';T='00000000-0000-4000-8000-000000000002'
A='00000000-0000-4000-8000-000000000003';O='00000000-0000-4000-8000-000000000004'
I='00000000-0000-4000-8000-000000000005';J='00000000-0000-4000-8000-000000000006'
C='00000000-0000-4000-8000-000000000007';D='00000000-0000-4000-8000-000000000008'


def selected(projects):
    ctx=request(projects,'checkpoint.report')['context'];project=copy.deepcopy(ctx);project['work']=None
    return dict(organization_id=O,team_id=T,actor_id=A,project_id=P,scope=dict(kind='repository',id='jarvis'),context=project,issues={I:ctx})


def native(kind,**kw):return dict(id=kind,updatedAt='2026-11-07T12:00:00Z',**kw)
def connection(nodes,more=False,cursor=None):return dict(nodes=nodes,pageInfo=dict(hasNextPage=more,endCursor=cursor))


def transport(fault=None):
    calls=[]
    def query(value):
        calls.append(value);kind=value['operation'];after=value['variables'].get('after')
        assert 'mutation' not in value['query'] and value['variables']['id']==P
        root=dict(id=P)
        if kind=='project':root=native(P,name='Synthetic project',description='Context')
        if kind=='issues':
            if after is None:
                root['issues']=connection([native(I,title='Mapped',team=dict(id=T),project=dict(id=P))],True,'next')
            else:root['issues']=connection([native(J,title='Unmapped',team=dict(id=T),project=dict(id=P))])
        if kind=='comments':
            issue=I if I in value['query'] else J
            comments=connection([native(C,body='Useful failure\nAuthorization: Bearer SYNTHETIC-SECRET')]) if issue==I else connection([])
            root['issues']=dict(nodes=[dict(id=issue,team=dict(id=T),project=dict(id=P),comments=comments)])
        if kind=='documents':root['documents']=connection([native(D,title='Reading copy',content='Architecture reading copy')])
        answer=dict(data=dict(viewer=dict(id=A,organization=dict(id=O)),project=root))
        if fault=='actor':answer['data']['viewer']['id']=J
        if fault=='errors':answer['errors']=[dict(message='synthetic denied')]
        if fault=='scope' and kind=='issues':root['issues']['nodes'][0]['project']['id']=J
        if fault=='cursor' and kind=='issues':root['issues']=connection(root['issues']['nodes'],True,'same')
        if fault=='offline' and kind=='documents':raise OSError('sensitive native error not retained')
        return answer
    return query,calls


def test_all_pages_exact_mappings_unknowns_redaction_and_unchanged_replay(spool,projects,evidence,reporting):
    config=selected(projects);query,calls=transport()
    result=m.poll(spool,config,query)
    assert result==dict(observed=5,complete_pass=True,work_launched=False)
    assert [x['variables'].get('after') for x in calls if x['operation']=='issues']==[None,'next']
    assert spool.flush(sender(reporting))['pending']==0
    rows=[r for r,_ in events(reporting) if r['operation']=='linear.observe']
    assert len(rows)==5
    assert next(r for r in rows if r['body']['object_id']==J)['context'] is None
    assert next(r for r in rows if r['body']['object_id']==I)['context']['work'] is not None
    assert next(r for r in rows if r['body']['object_kind']=='comment')['context']['work'] is not None
    for path in spool.root.rglob('*'):
        if path.is_file():assert b'SYNTHETIC-SECRET' not in path.read_bytes()
    assert m.poll(spool,config,query)['observed']==0
    assert spool.flush(sender(reporting))['delivered']==0


def test_poll_failure_keeps_partial_observations_and_recovery_resumes_without_duplicates(spool,projects,evidence,reporting):
    config=selected(projects);query,_=transport('offline')
    assert not m.poll(spool,config,query)['complete_pass']
    assert spool.flush(sender(reporting))['pending']==0
    query,_=transport();assert m.poll(spool,config,query)['complete_pass']
    assert spool.flush(sender(reporting))['pending']==0
    rows=events(reporting)
    assert sum(r['operation']=='linear.observe' for r,_ in rows)==5
    assert [r['body']['status'] for r,_ in rows if r['operation']=='source.observe']==['gap','current']


def test_bad_identity_cross_scope_and_nonadvancing_pages_refuse_without_launching(spool,projects,evidence,reporting):
    config=selected(projects)
    for fault in ('actor','errors','scope','cursor'):
        query,calls=transport(fault);result=m.poll(spool,config,query)
        assert not result['complete_pass'] and not result['work_launched']
        assert len(calls)<10
    assert spool.flush(sender(reporting))['pending']==0
    assert not any(r['operation'] in ('attempt.record','decision.observe','handoff.record') for r,_ in events(reporting))
