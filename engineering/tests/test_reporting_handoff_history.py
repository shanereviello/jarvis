"""Native handoff transitions survive outage/replay and preserve original pins."""
import copy
import importlib.util
from pathlib import Path
import pytest
from test_reporting_capture_intake import store,projects,evidence,reporting,sender,events
from test_reporting_runtime_reporting import setup,m
from test_reporting_codex_runtime import uid


def selected(tmp_path,projects):
    runtime_policy,config,spool,_,request=setup(tmp_path,projects);pin=runtime_policy['issues'][uid(3)]
    policy=dict(contract='native-agent-handoff-policy.v1',organization_id=uid(1),agents=dict(codex=uid(2),jarvis=uid(20)),issues={uid(3):pin})
    return spool,dict(contract='native-handoff-history-source.v1',policy=policy,scope=config['scope'],
        contexts={uid(3):[dict(binding=pin,context=config['contexts'][uid(3)])]})


def transitions(value):
    pin=value['policy']['issues'][uid(3)];native=m.local('native_handoff')
    intent=native.prepare(value['policy'],'jarvis',dict(session_id=uid(5),issue_id=uid(3),binding=pin,parent_handoff_id=None,depth=0),
        dict(key='fixture-handoff',summary='A selected failed attempt needs investigation.',requested_action='Investigate the failure and report validation.',
            references=[dict(namespace='validation',id='fixture-failure',sha256='a'*64)],limitations=[]))
    rows=[]
    for sequence,state in enumerate(('requested','acknowledged','completed'),1):
        snapshot={key:intent[key] for key in ('id','organization_id','sender','recipient','source_session_id','issue_id','comment_id','parent_handoff_id','depth')}
        snapshot.update(body=intent,state=state,target_session_id=None if sequence==1 else uid(60),
            result=None if sequence==1 else 'Native runtime observation; work acceptance is separate.',
            source_quiescence=None if sequence==1 else dict(source='hermes_runtime',run_id='fixture-hermes-run',state='completed'),
            recipient_observation=None if sequence==1 else dict(source='codex_runtime',dispatch_id=uid(61),state='running' if sequence==2 else 'completed'))
        rows.append(dict(sequence=sequence,id=intent['id'],organization_id=uid(1),state=state,snapshot=snapshot,observed_at='2026-11-08T20:00:00.000000Z'))
    return rows


def test_all_states_stage_during_history_outage_and_replay_exactly(tmp_path,projects,evidence,reporting):
    spool,value=selected(tmp_path,projects);rows=transitions(value);source=m.local('handoff_history')
    query=lambda after:dict(contract='native-handoff-event-page.v1',events=[x for x in rows if x['sequence']>after])
    assert source.poll(spool,value,query)['events_staged']==3
    assert spool.flush(lambda _:(_ for _ in ()).throw(OSError('fixture outage')))['pending']==3
    assert source.poll(spool,value,query)['events_staged']==0
    assert spool.flush(sender(reporting))['pending']==0
    saved=[r for r,_ in events(reporting)];assert [r['body']['state'] for r in saved]==['requested','acknowledged','completed']
    assert all(r['context']==value['contexts'][uid(3)][0]['context'] and r['source']['kind']=='imported' for r in saved)
    assert saved[-1]['body']['target_session']['id']==uid(60)
    assert any(r['namespace']=='runtime_dispatch' and r['id']==uid(61) for r in saved[-1]['body']['references'])
    assert not any(r['operation'] in ('decision.observe','outcome.record') for r in saved)


def test_changed_native_event_and_missing_initial_transition_are_refused(tmp_path,projects,reporting):
    spool,value=selected(tmp_path,projects);rows=transitions(value);source=m.local('handoff_history')
    with pytest.raises(ValueError,match='ordered'):source.stage(spool,value,rows[1])
    assert source.stage(spool,value,rows[0])
    changed=copy.deepcopy(rows[0]);changed['snapshot']['body']['requested_action']='Changed under same event ID'
    with pytest.raises(ValueError,match='event changed'):source.stage(spool,value,changed)
    wrong=copy.deepcopy(rows[1]);wrong['snapshot']['body']['recipient_app_user_id']=uid(99)
    with pytest.raises(ValueError):source.stage(spool,value,wrong)
    assert source.cursor(spool,value)==1


def test_retained_context_versions_do_not_substitute_latest_architecture(tmp_path,projects,reporting):
    spool,value=selected(tmp_path,projects);rows=transitions(value);source=m.local('handoff_history')
    old=copy.deepcopy(value['contexts'][uid(3)][0]);new=copy.deepcopy(old)
    new['binding']['architecture_version']+=1;new['context']['architecture']['version']+=1
    new['binding']['architecture_sha256']='9'*64;new['context']['architecture']['markdown_sha256']='9'*64
    value['policy']['issues'][uid(3)]=new['binding'];value['contexts'][uid(3)].append(new)
    source.configuration(value);source.stage(spool,value,rows[0])
    with spool.connection() as db:saved=spool.c.decode(db.execute('SELECT request FROM items').fetchone()[0])
    assert saved['context']==old['context'] and saved['context']!=new['context']


def test_invalid_remote_page_records_gap_but_still_delivers_pending_history(tmp_path,projects,evidence,reporting):
    spool,value=selected(tmp_path,projects);rows=transitions(value);source=m.local('handoff_history');source.stage(spool,value,rows[0])
    job=dict(spool=str(spool.root),selected=value,reader_url='http://unused/webhook/rras-native-handoff-events-prj_'+'1'*32,
        service_socket=str(tmp_path/'unused.sock'),service_uid=995)
    result=m.local('handoff_history_http').run_once(job,b'synthetic-not-used',query=lambda _:dict(contract='wrong',events=[]),send=sender(reporting))
    assert result['collection']['gap'] and result['delivery']['pending']==0
    assert source.cursor(spool,value)==1
