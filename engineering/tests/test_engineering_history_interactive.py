"""Explicit client context and spool using real local databases, never a daemon."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch
import pytest
from jsonschema import ValidationError
from test_engineering_history_local import request, module, c, WORK, TOOLS

m=module('interactive');store_module=module('store')

@pytest.fixture
def environment(tmp_path):
    backend=tmp_path/'history';backend.mkdir(mode=0o700);store=store_module.Store(backend,create=True)
    state=tmp_path/'client';state.mkdir(mode=0o700);client=m.Client(state,store=backend,create=True)
    return client,store


def note():return dict(summary='Implementation inspected; review still needed',decisions=[],next_action='Review evidence',references=[])

def start(client,session=None):
    client.enqueue('start','start-1',request(),session_id=session)
    return c.digest(c.encoded(request()['body']))


def test_explicit_start_checkpoint_handoff_pause_finish_and_receipts(environment):
    client,store=environment;head=start(client)
    assert store.history()['records']==[]
    assert not client.status()['context_recorded'] and len(client.status()['pending'])==2
    result=client.flush();assert result['delivered_now']==2 and result['status']['context_recorded']
    assert result['status']['context']['work_revision_sha256']==head
    assert result['status']['context']['session_id'] is None
    for kind in ('checkpoint','handoff','pause'):
        body=note()
        if kind=='checkpoint':body['checkpoint_type']='progress'
        client.enqueue(kind,kind+'-1',body);client.flush()
    client.enqueue('finish','finish-1',dict(outcome='completed_claim',summary='Reported completion; human acceptance remains separate',references=[]));client.flush()
    rows=store.history()['records'];assert len(rows)==6
    assert rows[-1]['submission']['body']['outcome']=='completed_claim'
    assert all(not row['receipt']['authority_granted'] for row in rows)
    assert client.status()['recording_state']=='recorded'
    assert client.status()['context_freshness']=='not_polled'


def test_offline_queue_survives_restart_and_replays_in_order_without_duplicates(environment,tmp_path):
    client,store=environment;offline=tmp_path/'offline';store.root.rename(offline)
    start(client);client.enqueue('handoff','handoff',note())
    result=client.flush();assert result['delivered_now']==0
    assert result['status']['recording_state']=='pending'
    assert result['status']['pending'][0]['error']=='store_unavailable'
    assert not result['status']['context_recorded']
    offline.rename(store.root);reopened=m.Client(client.root)
    assert reopened.flush()['delivered_now']==3
    assert reopened.flush()['delivered_now']==0
    rows=store.history()['records'];assert [r['submission']['operation'] for r in rows]==['work.create','session.attach','checkpoint.append']
    assert len(store.pending()['pending'])==3


def test_backend_commit_before_lost_client_ack_is_recovered_idempotently(environment):
    client,store=environment;start(client)
    with patch.object(client,'acknowledge',side_effect=OSError('synthetic lost reply')):
        with pytest.raises(OSError):client.flush()
    assert len(store.history()['records'])==1 and len(client.status()['pending'])==2
    assert m.Client(client.root).flush()['delivered_now']==2
    assert len(store.history()['records'])==2 and len(store.pending()['pending'])==2


def test_multi_request_action_and_context_commit_atomically(environment):
    client,store=environment
    with client.connection() as db:
        db.execute("CREATE TRIGGER fixture_fail BEFORE INSERT ON queue WHEN (SELECT COUNT(*) FROM queue)>=1 BEGIN SELECT RAISE(ABORT,'fixture transaction failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):start(client)
    assert client.status()['pending']==[] and client.status()['context'] is None
    with client.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM actions').fetchone()[0]==0
    assert store.history()['records']==[]


def test_client_local_commit_response_loss_retries_same_key_without_requeue(environment):
    client,store=environment
    with patch.object(client,'sync',side_effect=OSError('lost response')):
        with pytest.raises(OSError):start(client)
    assert not m.Client(client.root).enqueue('start','start-1',request())['queued_new_action']
    assert len(client.status()['pending'])==2
    assert client.flush()['delivered_now']==2


def test_same_action_key_different_content_refused(environment):
    client,store=environment;start(client)
    changed=request();changed['body']['objective']='Changed request'
    with pytest.raises(ValueError,match='key conflict'):client.enqueue('start','start-1',changed)
    assert len(client.status()['pending'])==2


def test_multiple_sessions_attach_same_work_without_new_work_or_inferred_session(environment,tmp_path):
    client,store=environment;head=start(client,'explicit-session-A');client.flush()
    state=tmp_path/'second';state.mkdir(mode=0o700);second=m.Client(state,store=store.root,create=True)
    second.enqueue('attach','resume',dict(work_item_id=WORK,work_revision_sha256=head),session_id='explicit-session-B')
    second.flush()
    assert len(store.history()['records'])==3
    assert second.status()['context']['session_id']=='explicit-session-B'
    assert client.status()['context']['session_id']=='explicit-session-A'


def test_stale_context_refuses_then_explicit_abandon_and_reattach_preserves_history(environment):
    client,store=environment;head=start(client);client.flush()
    revision=request('work.revise','new-scope',head);revision['body']['revision']=2
    new=store.submit(revision)['receipt']['work_revision_sha256']
    client.enqueue('handoff','stale',note());result=client.flush()
    assert result['status']['pending'][0]['error']=='store_refused'
    assert len(store.history()['records'])==3
    status=client.abandon('stale','Stale scope; explicitly reattach to revised intent')
    assert status['recording_state']=='incomplete' and len(status['abandoned'])==1
    client.enqueue('attach','reattach',dict(work_item_id=WORK,work_revision_sha256=new));client.flush()
    assert client.status()['context_recorded'] and client.status()['context']['work_revision_sha256']==new
    assert len(client.status()['abandoned'])==1
    with client.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM queue').fetchone()[0]==4


def test_abandon_does_not_claim_remote_commit_reversal(environment):
    client,store=environment;start(client)
    with patch.object(client,'acknowledge',side_effect=OSError('lost acknowledgment')):
        with pytest.raises(OSError):client.flush()
    assert len(store.history()['records'])==1
    status=client.abandon('start-1','Delivery stopped after uncertain acknowledgment')
    assert all(x['state']=='delivery_abandoned_remote_outcome_not_inferred' for x in status['abandoned'])
    assert client.flush()['delivered_now']==0 and len(store.history()['records'])==1
    assert not client.status()['context_recorded']
    assert client.abandon('start-1','Delivery stopped after uncertain acknowledgment')['abandoned']==status['abandoned']
    with pytest.raises(ValueError,match='reason conflict'):client.abandon('start-1','Changed explanation')


@pytest.mark.parametrize('bad',['no_context','override_context','authority','observed','wrong_operation'])
def test_no_implicit_context_or_authority_promotion(environment,bad):
    client,store=environment
    if bad=='no_context':
        with pytest.raises(ValueError,match='explicit work'):client.enqueue('handoff','note',note())
        return
    start(client);before=len(client.status()['pending'])
    if bad=='override_context':
        body=note();body['work_item_id']=WORK
        with pytest.raises(ValueError):client.enqueue('handoff','bad',body)
    elif bad=='authority':
        body=note();body['execution_authorized']=True
        with pytest.raises(ValidationError):client.enqueue('handoff','bad',body)
    elif bad=='observed':
        body=request();body['source']['kind']='observed'
        with pytest.raises(ValidationError):client.enqueue('start','bad',body)
    else:
        with pytest.raises(ValueError):client.enqueue('merge','bad',note())
    assert len(client.status()['pending'])==before


def test_old_duplicate_action_does_not_reset_active_context(environment):
    client,store=environment;head=start(client,'S1');client.flush()
    client.enqueue('attach','new-session',dict(work_item_id=WORK,work_revision_sha256=head),session_id='S2')
    assert not client.enqueue('start','start-1',request(),session_id='S1')['queued_new_action']
    assert client.status()['context']['session_id']=='S2'


@pytest.mark.parametrize('capacity',['pending','actions'])
def test_queue_and_action_bounds_preserve_existing_context(environment,capacity):
    client,store=environment;start(client)
    with patch.object(m,'MAX_PENDING' if capacity=='pending' else 'MAX_ACTIONS',2 if capacity=='pending' else 1):
        with pytest.raises(ValueError):client.enqueue('handoff','extra',note())
    assert len(client.status()['pending'])==2


def test_client_metadata_modes_symlink_and_fixed_transport(environment,tmp_path):
    client,store=environment
    assert client.path.stat().st_mode&0o777==0o600
    with pytest.raises(FileExistsError):m.Client(client.root,store=store.root,create=True)
    with pytest.raises(ValueError):m.Client(client.root,store=tmp_path)
    link=tmp_path/'link';link.symlink_to(client.root,target_is_directory=True)
    with pytest.raises(ValueError):m.Client(link)
    client.root.chmod(0o755)
    with pytest.raises(ValueError):client.status()


def test_queued_request_and_delivered_receipt_cannot_be_overwritten(environment):
    client,store=environment;start(client)
    with client.connection() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute("UPDATE queue SET request='different'")
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM queue')
    client.flush()
    with client.connection() as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute('UPDATE queue SET receipt=NULL')


def test_receipt_mismatch_preserves_pending_request_and_does_not_mint_confirmation(environment):
    client,store=environment;start(client)
    original=client.acknowledge
    def changed(db,seq,req,receipt):
        receipt={**receipt,'work_revision_sha256':'f'*64}
        return original(db,seq,req,receipt)
    with patch.object(client,'acknowledge',side_effect=changed):
        with pytest.raises(ValueError,match='receipt differs'):client.flush()
    assert len(client.status()['pending'])==2 and not client.status()['context_recorded']
    assert client.flush()['delivered_now']==2


def test_cli_start_outage_queue_only_and_explicit_flush(tmp_path):
    state=tmp_path/'client';state.mkdir(mode=0o700);backend=tmp_path/'history'
    script=TOOLS/'interactive_cli.py'
    def cli(*args):return subprocess.run([sys.executable,str(script),*args,'--state',str(state)],capture_output=True,check=True,timeout=15)
    assert json.loads(cli('init','--history-store',str(backend)).stdout)['recording_state']=='empty'
    example=Path(__file__).resolve().parents[1]/'contracts/examples/history-local-work.json'
    result=json.loads(cli('start','--key','start','--request',str(example)).stdout)
    assert result['status']['recording_state']=='pending'
    payload=tmp_path/'note.json';payload.write_text(json.dumps(note()))
    result=json.loads(cli('handoff','--key','handoff','--note',str(payload),'--queue-only').stdout)
    assert len(result['status']['pending'])==3
    backend.mkdir(mode=0o700);store_module.Store(backend,create=True)
    assert json.loads(cli('flush').stdout)['delivered_now']==3
    assert json.loads(cli('status').stdout)['recording_state']=='recorded'


def test_concurrent_same_client_action_has_one_spool_entry_group(environment):
    from concurrent.futures import ThreadPoolExecutor
    client,store=environment
    def invoke(_):return m.Client(client.root).enqueue('start','one-request',request())['queued_new_action']
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(invoke,[1,2]))
    assert sorted(results)==[False,True] and len(client.status()['pending'])==2


def test_session_changes_cannot_be_hidden_in_note_or_noninitial_start(environment):
    client,store=environment;start(client)
    with pytest.raises(ValueError,match='explicit attachment'):client.enqueue('handoff','note',note(),session_id='other-session')
    changed=request();changed['body']['revision']=2
    with pytest.raises(ValueError,match='fresh'):client.enqueue('start','bad-revision',changed)
    assert len(client.status()['pending'])==2


def test_root_client_refuses_before_opening_state(tmp_path):
    with patch.object(m.os,'getuid',return_value=0),patch.object(m.os,'geteuid',return_value=0):
        with pytest.raises(ValueError,match='unprivileged'):m.Client(tmp_path,store=tmp_path,create=True)


def test_abandon_delivered_action_cannot_erase_receipt(environment):
    client,store=environment;start(client);client.flush()
    with pytest.raises(ValueError,match='no unresolved'):client.abandon('start-1','Erase previous history')
    assert client.status()['recording_state']=='recorded'
