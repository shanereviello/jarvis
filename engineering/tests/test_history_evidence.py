"""Actual private chunks, reviewed migration, exact manifests and scoped RPC."""
import base64
import copy
import hashlib
import os
import sqlite3
import uuid
import pytest
from test_engineering_history_local import module,store,request as work_request
from test_history_projects import projects, P1, REPO
from test_history_reporting import reporting, request
from test_engineering_history_unix import env, running, rpc
from test_history_reporting import ready

em=module('evidence');c=module('contract')


@pytest.fixture
def evidence(reporting):
    value=em.Evidence(reporting.store);value.migrate(value.migration_plan()['expected_sha256']);return value


def upload(raw=b'private fixture evidence',scope=None,key=None):
    return dict(contract='engineering-evidence-chunk.v1',client_event_key=key or uuid.uuid4().hex,
        scope=scope or REPO,sha256=hashlib.sha256(raw).hexdigest(),byte_length=len(raw),
        data_base64=base64.b64encode(raw).decode())


def manifest(projects,raw,*,context=True):
    value=request(projects,'artifact.record');body=value['body']
    if not context:value['context']=None
    body.update(content_sha256=hashlib.sha256(raw).hexdigest(),byte_length=len(raw),
        chunks=[dict(index=i,sha256=hashlib.sha256(raw[n:n+em.CHUNK_BYTES]).hexdigest(),
            byte_length=len(raw[n:n+em.CHUNK_BYTES])) for i,n in enumerate(range(0,len(raw),em.CHUNK_BYTES))])
    return value


def view(projects):
    return projects.read(REPO,dict(view='project',project_id=P1))


def query(projects,value,index=None,snapshot=None):
    q=dict(artifact_id=value['body']['artifact_id'],version=value['body']['version'],
        snapshot=snapshot or view(projects)['snapshot'])
    if index is not None:q['index']=index
    return q


def test_explicit_upgrade_binds_current_reporting_and_preserves_prior_views(reporting,projects):
    old=view(projects);value=em.Evidence(reporting.store);plan=value.migration_plan()
    with reporting.store.connection() as db:
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        before={name:db.execute('SELECT * FROM '+name).fetchall() for name in tables}
        ddl=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL"))
    with pytest.raises(ValueError):value.migrate('0'*64)
    reporting.submit(request(projects,'checkpoint.report'))
    with pytest.raises(ValueError):value.migrate(plan['expected_sha256'])
    plan=value.migration_plan()
    # Take the comparison after the intentionally retained checkpoint.
    with reporting.store.connection() as db:
        before={name:db.execute('SELECT * FROM '+name).fetchall() for name in tables}
    value.migrate(plan['expected_sha256'])
    with reporting.store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==5
        assert {name:db.execute('SELECT * FROM '+name).fetchall() for name in tables}==before
        after=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL"))
        assert all(after[name]==sql for name,sql in ddl.items())
    assert projects.read(REPO,dict(view='project',project_id=old['project']['project_id'],snapshot=old['snapshot']))==old
    assert not list(value.chunks.iterdir())
    with pytest.raises(ValueError):value.migrate(plan['expected_sha256'])


def test_upload_exact_replay_and_changed_key_conflict(evidence):
    value=upload();first=evidence.upload(value)
    assert evidence.upload(value)==dict(inserted=False,receipt=first['receipt'])
    assert evidence.read_blob(value['sha256'],value['byte_length'])==base64.b64decode(value['data_base64'])
    changed=upload(b'changed',key=value['client_event_key'])
    with pytest.raises(ValueError,match='idempotency'):evidence.upload(changed)
    assert len(list(evidence.chunks.iterdir()))==1
    assert first['receipt']['visibility']=='operator_private' and first['receipt']['authority_granted'] is False


@pytest.mark.parametrize('change',['digest','size','boolean','base64','path','extra','too_large'])
def test_malformed_chunks_never_enter_custody(evidence,change):
    value=upload()
    if change=='digest':value['sha256']='0'*64
    elif change=='size':value['byte_length']+=1
    elif change=='boolean':value['byte_length']=True
    elif change=='base64':value['data_base64']+='\n'
    elif change=='path':value['sha256']='../outside'
    elif change=='extra':value['source_path']='/private/other/session'
    elif change=='too_large':value=upload(b'x'*(em.CHUNK_BYTES+1))
    with pytest.raises(ValueError):evidence.upload(value)
    assert not list(evidence.chunks.iterdir())


def test_manifest_requires_scoped_uploaded_bytes_and_total_digest(evidence,reporting,projects):
    raw=b'A'*em.CHUNK_BYTES+b'B';value=manifest(projects,raw)
    with pytest.raises(ValueError,match='retained scoped chunk'):reporting.submit(value)
    evidence.upload(upload(raw[:em.CHUNK_BYTES]));evidence.upload(upload(raw[em.CHUNK_BYTES:]))
    wrong=copy.deepcopy(value);wrong['body']['content_sha256']='0'*64
    with pytest.raises(ValueError,match='content digest'):reporting.submit(wrong)
    old=view(projects)['snapshot'];saved=reporting.submit(value)
    assert reporting.submit(value)==dict(inserted=False,receipt=saved['receipt'])
    with pytest.raises(ValueError,match='boundary'):evidence.read(REPO,query(projects,value,snapshot=old))
    got=evidence.read(REPO,query(projects,value,1))
    assert base64.b64decode(got['chunk']['data_base64'])==b'B'
    assert got['manifest_sha256']==saved['receipt']['request_sha256']
    other=manifest(projects,raw,context=False);other['scope']=dict(kind='repository',id='other')
    other['body']['artifact_id']='cap_'+'9'*32
    with pytest.raises(ValueError,match='scoped chunk'):reporting.submit(other)


def test_empty_artifact_and_immutable_manifest_versions(evidence,reporting,projects):
    value=manifest(projects,b'');first=reporting.submit(value);old=view(projects)['snapshot']
    assert evidence.read(REPO,query(projects,value))['manifest']['byte_length']==0
    with pytest.raises(ValueError):evidence.read(REPO,query(projects,value,0))
    evidence.upload(upload(b'new bytes'));new=manifest(projects,b'new bytes')
    new['body'].update(version=2,previous_sha256=first['receipt']['request_sha256'])
    new['expected_head']=first['receipt']['request_sha256'];reporting.submit(new)
    assert evidence.read(REPO,query(projects,value,snapshot=old))['manifest']['byte_length']==0
    with pytest.raises(ValueError,match='boundary'):evidence.read(REPO,query(projects,new,snapshot=old))


def test_association_correction_is_append_only_and_exact(evidence,reporting,projects):
    value=manifest(projects,b'',context=False);saved=reporting.submit(value)
    assoc=request(projects,'artifact.associate');assoc['body']['manifest_sha256']=saved['receipt']['request_sha256']
    first=reporting.submit(assoc);old=view(projects)['snapshot']
    changed=copy.deepcopy(assoc);changed['client_event_key']=uuid.uuid4().hex
    with pytest.raises(ValueError,match='previous artifact association'):reporting.submit(changed)
    changed['body'].update(previous_association_sha256=first['receipt']['request_sha256'],reason='Explicit corrected association explanation')
    changed['expected_head']=first['receipt']['request_sha256'];reporting.submit(changed)
    before=projects.read(REPO,dict(view='reporting',snapshot=old))
    assert sum(r['submission']['operation']=='artifact.associate' for r in before['items'])==1
    evidence.upload(upload(b'immutability sentinel'))
    with reporting.store.connection() as db:
        for table in ('evidence_uploads','evidence_chunks'):
            with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM '+table)


def test_quota_retains_prior_evidence_and_replay_survives_lost_ack(evidence,monkeypatch):
    value=upload(b'keep');first=evidence.upload(value)
    monkeypatch.setattr(em,'SCOPE_BYTES',4)
    with pytest.raises(ValueError,match='capacity'):evidence.upload(upload(b'extra'))
    assert evidence.upload(value)['receipt']==first['receipt']
    assert evidence.read_blob(value['sha256'],4)==b'keep'
    monkeypatch.setattr(em,'SCOPE_BYTES',100)
    later=upload(b'lost acknowledgment');sync=evidence.store.sync
    monkeypatch.setattr(evidence.store,'sync',lambda:(_ for _ in ()).throw(OSError('fixture lost acknowledgment')))
    with pytest.raises(OSError):evidence.upload(later)
    monkeypatch.setattr(evidence.store,'sync',sync)
    assert evidence.upload(later)['inserted'] is False


def test_orphan_after_failed_commit_is_verified_on_replay(evidence,monkeypatch):
    value=upload(b'orphan')
    with monkeypatch.context() as m:
        m.setattr(em.uuid,'uuid4',lambda:(_ for _ in ()).throw(OSError('fixture interrupted before commit')))
        with pytest.raises(OSError):evidence.upload(value)
    assert len(list(evidence.chunks.iterdir()))==1
    assert evidence.upload(value)['inserted'] is True
    assert len(list(evidence.chunks.iterdir()))==1


@pytest.mark.parametrize('change',['symlink','hardlink','permissions','content'])
def test_unsafe_or_corrupt_chunks_are_not_served(evidence,reporting,projects,tmp_path,change):
    raw=b'protected';value=upload(raw);evidence.upload(value)
    meta=manifest(projects,raw);reporting.submit(meta);p=evidence.chunks/value['sha256']
    if change=='symlink':
        outside=tmp_path/'outside';outside.write_bytes(raw);p.unlink();p.symlink_to(outside)
    elif change=='hardlink':os.link(p,tmp_path/'linked')
    elif change=='permissions':p.chmod(0o644)
    else:p.write_bytes(b'corrupted')
    with pytest.raises((ValueError,OSError)):evidence.read(REPO,query(projects,meta,0))


def test_reader_scope_and_actual_unix_chunk_round_trip(env):
    root,store,_=env;work=work_request();work['body']['repository_id']='jarvis';store.submit(work);pm=module('projects').Projects(store)
    pm.migrate(pm.migration_plan()['expected_sha256']);ready(pm)
    reporting=module('reporting').Reporting(store);reporting.migrate(reporting.migration_plan()['expected_sha256'])
    evidence=em.Evidence(store);evidence.migrate(evidence.migration_plan()['expected_sha256'])
    grants=dict(contract='engineering-history-access.v1',principals=[
        dict(uid=os.getuid(),private_read=['jarvis'],write=['jarvis']),
        dict(uid=2002,private_read=['other'],write=['other']),dict(uid=2003,private_read=['jarvis'],write=[])])
    access=module('access').Access(store,grants);value=upload(b'RPC bytes')
    with pytest.raises(ValueError):access.dispatch(2003,dict(method='evidence_upload',request=value))
    with pytest.raises(ValueError):access.dispatch(2002,dict(method='evidence_read',scope=REPO,query={}))
    with running(env,grants) as server:
        saved=rpc(server,dict(method='evidence_upload',request=value))
        assert saved['receipt']['peer_uid']==os.getuid()
        meta=manifest(pm,b'RPC bytes');rpc(server,dict(method='reporting_submit',request=meta))
        fetched=rpc(server,dict(method='evidence_read',scope=REPO,query=query(pm,meta,0)))
        assert base64.b64decode(fetched['chunk']['data_base64'])==b'RPC bytes'
