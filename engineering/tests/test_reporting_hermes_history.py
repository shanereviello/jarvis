"""Owned intake of native Jarvis start, lifecycle and checkpoint, without work launch."""
import copy
import json
import pytest
from test_reporting_handoff_history import selected as handoff_selected
from test_reporting_capture_intake import store,projects,evidence,reporting,sender,events
from test_reporting_runtime_reporting import m
from test_reporting_codex_runtime import uid

source=m.local('hermes_history')


def selected(tmp_path,projects):
    spool,value=handoff_selected(tmp_path,projects);value['contract']='hermes-runtime-history-source.v1'
    return spool,value


def lifecycle(value):
    pin=value['policy']['issues'][uid(3)];when='2026-11-08T20:00:00.000000Z'
    admission=dict(sequence=1,delivery_id=uid(8),organization_id=uid(1),session_id=uid(5),issue_id=uid(3),binding=pin,handoff_id=None,observed_at=when)
    run=dict(sequence=1,delivery_id=uid(8),organization_id=uid(1),session_id=uid(5),issue_id=uid(3),binding=pin,handoff_id=None,
        run_id='run_'+'a'*32,hermes_session_id='linear:'+uid(1)+':'+uid(5),status='running',recorded_at=when,admitted_at=when,completed_at=None)
    return admission,run


def checkpoint(tmp_path,value,run):
    native=m.local('hermes_runtime');queue=m.local('runtime_handoff').Queue(tmp_path/'native-tool-queue',create=True);posted=[]
    context=dict(session_id=uid(5),issue_id=uid(3),binding=run['binding'],parent_handoff_id=None,depth=0,delivery_id=uid(8))
    def call(kind,body):
        if kind=='context':return dict(context=context,execution_started=False)
        posted.append(body);return dict(staged=True,request_id=body['id'],execution_started=False)
    adapter=native.Adapter(dict(contract='hermes-native-reporting.v1',policy=value['policy'],scope=value['scope'],
        contexts={uid(3):value['contexts'][uid(3)][0]['context']},queue=str(queue.path),origin='http://fixture.invalid',token_file='/unused'),
        call=call,actual=lambda:{k:run[k] for k in ('organization_id','session_id','hermes_session_id','run_id')})
    adapter.record('checkpoint',dict(key='investigation',observations=['Selected native finding.'],next_step='Validate the proposed correction.'))
    assert adapter.flush()['pending']==0
    request=posted[0];raw=json.dumps(request['report'],separators=(',',':'),ensure_ascii=False)
    return dict(sequence=1,id=request['id'],run_id=run['run_id'],organization_id=uid(1),issue_id=uid(3),report_json=raw,
        report_sha256=queue.i.local('contract').digest(raw.encode()),observed_at='2026-11-08T20:00:01.000000Z')


def page(admission,run,report=None):
    def query(cursor):
        admissions=[admission] if cursor['after_admission']==0 else []
        checkpoints=[report] if report and cursor['after_checkpoint']==0 else []
        return dict(contract='hermes-runtime-history-page.v1',admissions=admissions,runs=[run],checkpoints=checkpoints,
            next_admission_after=1,next_run_after=0,next_checkpoint_after=1 if report else 0)
    return query


def test_native_start_and_checkpoint_reach_owned_history_after_outage(tmp_path,projects,evidence,reporting):
    spool,value=selected(tmp_path,projects);admission,run=lifecycle(value);report=checkpoint(tmp_path,value,run);query=page(admission,run,report)
    source.poll(spool,value,query)
    assert spool.flush(lambda _:(_ for _ in ()).throw(OSError('synthetic history outage')))['pending']>0
    source.poll(spool,value,query)
    assert spool.flush(sender(reporting))['pending']==0
    saved=[r for r,_ in events(reporting)];attempts=[r['body'] for r in saved if r['operation']=='attempt.record']
    assert [body['phase'] for body in attempts]==['started','progress']
    assert all(body['actor']==dict(role='jarvis',runtime='hermes_api',source_actor_id=uid(20)) for body in attempts)
    record=next(r for r in saved if r['operation']=='checkpoint.report')
    assert record['source']['kind']=='agent_reported' and record['body']['attempt_id']==attempts[0]['attempt_id']
    assert record['context']==value['contexts'][uid(3)][0]['context']
    run['status']='completed';run['completed_at']='2026-11-08T20:00:02.000000Z';source.poll(spool,value,query)
    assert spool.flush(sender(reporting))['pending']==0
    attempts=[r['body'] for r,_ in events(reporting) if r['operation']=='attempt.record']
    assert [body['phase'] for body in attempts]==['started','progress','completed']
    assert not any(r['operation'] in ('decision.observe','outcome.record') for r,_ in events(reporting))
    assert source.poll(spool,value,query)['models_started']==0 and spool.flush(sender(reporting))['delivered']==0


def test_terminal_contradiction_preserves_gap_without_reopening_attempt(tmp_path,projects,evidence,reporting):
    spool,value=selected(tmp_path,projects);admission,run=lifecycle(value);query=page(admission,run)
    run.update(status='completed',completed_at='2026-11-08T20:00:02.000000Z');source.poll(spool,value,query)
    run.update(status='running',completed_at=None);source.poll(spool,value,query)
    assert spool.flush(sender(reporting))['pending']==0
    saved=[r for r,_ in events(reporting)]
    assert [r['body']['phase'] for r in saved if r['operation']=='attempt.record']==['started','completed']
    assert any(r['operation']=='source.observe' and r['body']['status']=='gap' and 'terminal' in str(r['body']['gaps']) for r in saved)


def test_old_pins_remain_exact_and_bad_native_report_is_not_imported(tmp_path,projects,reporting):
    spool,value=selected(tmp_path,projects);admission,run=lifecycle(value);old=copy.deepcopy(value['contexts'][uid(3)][0]);new=copy.deepcopy(old)
    new['binding'].update(architecture_version=old['binding']['architecture_version']+1,architecture_sha256='9'*64)
    new['context']['architecture'].update(version=new['binding']['architecture_version'],markdown_sha256='9'*64)
    value['policy']['issues'][uid(3)]=new['binding'];value['contexts'][uid(3)].append(new)
    source.poll(spool,value,page(admission,run))
    with spool.connection() as db:
        assert all(spool.c.decode(r[0])['context']==old['context'] for r in db.execute('SELECT request FROM items'))
    report=dict(sequence=1,id=uid(70),run_id=run['run_id'],organization_id=uid(1),issue_id=uid(3),report_json='{}',report_sha256='0'*64,observed_at=None)
    with pytest.raises(ValueError,match='digest'):source.stage_checkpoint(spool,value,report,{run['run_id']:run})


def test_interrupted_cursor_is_retained_and_refuses_collection(tmp_path,projects,reporting):
    spool,value=selected(tmp_path,projects);pending=spool.root/'hermes-cursor.pending';pending.write_text('interrupted');pending.chmod(0o600)
    with pytest.raises(ValueError,match='interrupted'):source.poll(spool,value,lambda _:(_ for _ in ()).throw(AssertionError('must not query')))
    assert pending.read_text()=='interrupted'
