"""Actual durable private spool, redaction, service replay and explicit context."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import pytest
from test_engineering_history_local import module,store
from test_history_projects import projects,REPO
from test_history_reporting import reporting
from test_history_evidence import evidence,manifest,view

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('capture_intake_test',ROOT/'tools/rras_reporting/capture_intake.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


@pytest.fixture
def spool(tmp_path):return m.Spool(tmp_path/'capture-spool',create=True)


def stage(spool,projects,text=b'Synthetic prompt\nSynthetic failed approach\nSynthetic resolution',*,native=b'first-native-prefix',context=True):
    return spool.stage(text,scope=REPO,context=manifest(projects,b'')['context'] if context else None,
        session=dict(namespace='synthetic_codex',id='synthetic-session'),collector='specstory',collector_version='2.17.0',
        source_sha256=hashlib.sha256(native).hexdigest(),source_range=dict(start='line:1',end='line:3'),
        source_created_at='2026-11-07T12:00:00Z',source_updated_at='2026-11-07T12:00:02Z')


def sender(reporting):
    access=module('access').Access(reporting.store,dict(contract='engineering-history-access.v1',
        principals=[dict(uid=2001,private_read=['jarvis'],write=['jarvis'])]))
    def send(message):
        assert message['method'] in ('evidence_upload','reporting_submit')
        return access.dispatch(2001,message)
    return send


def events(reporting):
    with reporting.store.connection() as db:return reporting.events(db,REPO)


def test_pattern_redaction_precedes_any_spool_write(spool,projects,evidence,reporting):
    secrets=[b'sk-abcdefghijklmnopqrstuvwxyz012345',b'ghp_abcdefghijklmnopqrstuvwxyz012345',
        b'real-looking-password',b'private-body-marker',b'opaque-header-token']
    raw=(b'# Visible engineering\napi_key="'+secrets[0]+b'"\npassword='+secrets[2]+
        b'\nAuthorization: Bearer '+secrets[4]+b'\n-----BEGIN PRIVATE KEY-----\n'+secrets[3]+
        b'\n-----END PRIVATE KEY-----\n'+secrets[1]+b'\nUseful failure and result.')
    result=stage(spool,projects,raw)
    assert result['raw_bytes_retained'] is False and result['redactions']
    for p in spool.root.rglob('*'):
        if p.is_file():assert all(secret not in p.read_bytes() for secret in secrets)
    assert spool.flush(sender(reporting))['pending']==0
    saved=[r for r,_ in events(reporting) if r['operation']=='artifact.record'][0]
    got=evidence.read(REPO,dict(artifact_id=result['artifact_id'],version=1,snapshot=view(projects)['snapshot']))
    assert saved['body']['captured_at']!=saved['body']['source_updated_at']
    assert got['manifest']['redaction_profile']==m.PROFILE and got['manifest']['completeness']=='partial'
    assert not any(r['operation'] in ('attempt.record','handoff.record') for r,_ in events(reporting))


def test_repeated_source_and_content_return_existing_frozen_item(spool,projects,evidence,reporting):
    first=stage(spool,projects);again=stage(spool,projects)
    assert first['sequence']==again['sequence'] and again['staged'] is False
    result=spool.flush(sender(reporting));assert result['pending']==0 and result['work_launched'] is False
    before=events(reporting);assert spool.flush(sender(reporting))['delivered']==0
    assert events(reporting)==before


def test_outage_restarts_and_lost_artifact_ack_never_duplicate_import(spool,projects,evidence,reporting):
    stage(spool,projects)
    def offline(message):raise OSError('synthetic unavailable')
    assert spool.flush(offline)['pending']>0
    assert spool.flush(offline)['pending']>0
    reopened=m.Spool(spool.root);send=sender(reporting);lost=[False]
    def lose(message):
        result=send(message)
        if message['method']=='reporting_submit' and message['request']['operation']=='artifact.record' and not lost[0]:
            lost[0]=True;raise OSError('synthetic lost acknowledgment after commit')
        return result
    assert reopened.flush(lose)['pending']>0
    assert m.Spool(spool.root).flush(send)['pending']==0
    rows=events(reporting)
    assert sum(r['operation']=='artifact.record' for r,_ in rows)==1
    statuses=[r['body']['status'] for r,_ in rows if r['operation']=='source.observe']
    assert statuses[-1]=='current' and 'failed' in statuses


def test_queued_versions_preserve_exact_predecessor_and_original_bytes(spool,projects,evidence,reporting):
    first=stage(spool,projects,b'first export');stage(spool,projects,b'second export',native=b'next-native-prefix')
    result=spool.flush(sender(reporting));assert result['pending']==0
    records=[(r,receipt) for r,receipt in events(reporting) if r['operation']=='artifact.record']
    assert [r['body']['version'] for r,_ in records]==[1,2]
    assert records[1][0]['expected_head']==records[0][1]['request_sha256']
    for version,text in [(1,b'first export'),(2,b'second export')]:
        answer=evidence.read(REPO,dict(artifact_id=first['artifact_id'],version=version,index=0,snapshot=view(projects)['snapshot']))
        assert answer['chunk']['sha256']==hashlib.sha256(text).hexdigest()


def test_unknown_association_stays_unmapped(spool,projects,evidence,reporting):
    stage(spool,projects,context=False);assert spool.flush(sender(reporting))['pending']==0
    rows=events(reporting)
    assert all(r['context'] is None for r,_ in rows)
    assert rows[-1][0]['body']['status']=='unmapped'
    assert view(projects)['project']['reporting']['record_count']==0


def test_wrong_receipt_retains_frozen_request_for_reconciliation(spool,projects,evidence,reporting):
    stage(spool,projects);send=sender(reporting)
    def corrupt(message):
        result=send(message)
        if message['method']=='reporting_submit' and message['request']['operation']=='artifact.record':
            result=copy.deepcopy(result);result['receipt']['request_sha256']='0'*64
        return result
    assert spool.flush(corrupt)['failed']>0
    with spool.connection() as db:
        row=db.execute("SELECT * FROM items WHERE kind='artifact'").fetchone()
        assert row['receipt'] is None
        frozen=row['request']
    assert spool.flush(send)['pending']==0
    with spool.connection() as db:assert db.execute("SELECT request FROM items WHERE kind='artifact'").fetchone()[0]==frozen
    assert sum(r['operation']=='artifact.record' for r,_ in events(reporting))==1


def test_reserved_status_capacity_and_export_corruption(spool,projects,evidence,reporting,monkeypatch):
    monkeypatch.setattr(m,'MAX_ITEMS',4);first=stage(spool,projects)
    with pytest.raises(ValueError,match='capacity'):stage(spool,projects,b'next',native=b'next')
    assert spool.flush(sender(reporting))['pending']==0
    assert len(events(reporting))==3
    with spool.connection() as db:row=db.execute("SELECT * FROM items WHERE kind='artifact'").fetchone()
    assert (spool.exports/row['export_sha256']).read_bytes().startswith(b'Synthetic prompt')


@pytest.mark.parametrize('limit',[0,True,1001,None])
def test_delivery_batch_is_bounded(spool,limit):
    with pytest.raises(ValueError):spool.flush(lambda x:None,maximum=limit)


def test_source_state_changes_are_deduplicated_and_recovery_is_retained(spool,projects,evidence,reporting):
    args=dict(scope=REPO,context=None,session=dict(namespace='codex',id='fixture'),cursor='byte:42',
        source_observed_at='2026-11-07T12:00:00Z')
    assert spool.source_status(**args,status='failed',detail='Selected source unavailable')['staged']
    assert not spool.source_status(**args,status='failed',detail='Selected source unavailable')['staged']
    assert spool.source_status(**args,status='current',detail='Selected source available')['staged']
    assert spool.source_status(**args,status='failed',detail='Selected source unavailable')['staged']
    assert spool.flush(sender(reporting))['pending']==0
    assert [r['body']['status'] for r,_ in events(reporting)]==['failed','current','failed']


def test_corrupt_pending_export_is_retained_but_never_finalized(spool,projects,evidence,reporting):
    stage(spool,projects)
    with spool.connection() as db:row=db.execute("SELECT * FROM items WHERE kind='artifact'").fetchone()
    path=spool.exports/row['export_sha256'];path.write_bytes(b'CORRUPTED')
    result=spool.flush(sender(reporting))
    assert result['failed'] and result['pending'] and path.exists()
    assert not any(r['operation']=='artifact.record' for r,_ in events(reporting))
