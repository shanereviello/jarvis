"""Historical custody consistency and transfer ordering; root is a test adapter."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from test_engineering_history_local import module,DOC
from test_history_managed_review import inputs
import test_history_document_approval as adapter

export=module('review_document_export');c=module('contract')


@pytest.fixture
def packet(inputs):
    return module('review_document_link').build({'work_request':inputs[2],'package':module('managed_review').build(*inputs,DOC)})


@pytest.fixture
def custody():
    x=adapter.DocumentApprovalTests();x.setUp();x.prepare_document()
    try:yield x
    finally:x.doCleanups()


def test_historical_export_survives_live_revocation_without_approval(custody,monkeypatch):
    x=custody;before={p.name:p.read_bytes() for p in x.state.iterdir() if p.is_file()}
    x.config['hermes_project']='revoked';x.save_config()
    with pytest.raises(ValueError):x.d.load(x.state,x.rid)
    monkeypatch.setattr(export,'administrator',lambda:None)
    monkeypatch.setattr(export,'source_module',lambda *_:x.d)
    packet=export.snapshot(x.state,x.rid,x.root,'a'*64,approve_private_export=True)
    assert packet['authority_granted'] is False and packet['source_provenance']=='imported'
    assert {p.name:p.read_bytes() for p in x.state.iterdir() if p.is_file()}==before
    assert not list(x.state.glob('*.approval.json'))


def test_export_requires_explicit_private_export_approval(custody,monkeypatch):
    monkeypatch.setattr(export,'administrator',lambda:None)
    monkeypatch.setattr(export,'source_module',lambda *_:pytest.fail('no protected input read before approval'))
    with pytest.raises(ValueError,match='explicit private'):export.snapshot(custody.state,custody.rid,custody.root,'a'*64)


@pytest.mark.parametrize('change',['markdown','capture','version'])
def test_changed_historical_custody_or_source_refused(custody,monkeypatch,change):
    x=custody;monkeypatch.setattr(export,'administrator',lambda:None);monkeypatch.setattr(export,'source_module',lambda *_:x.d)
    if change=='markdown':(x.state/(x.rid+'.review.md')).write_text('changed')
    elif change=='capture':(x.state/(x.rid+'.review.json')).write_text('{}')
    else:
        real=adapter.m.control_hashes;monkeypatch.setattr(adapter.m,'control_hashes',lambda:dict(real(),changed='f'*64))
    with pytest.raises(ValueError):export.snapshot(x.state,x.rid,x.root,'a'*64,approve_private_export=True)


def test_handoff_populates_then_transfers_directory_last(packet,tmp_path,monkeypatch):
    monkeypatch.setattr(export,'administrator',lambda:None);calls=[]
    def parent(path,mode):path=Path(path);path.mkdir(mode=mode);return path
    monkeypatch.setattr(export,'parent',parent)
    def chown(path,uid,gid,**kwargs):
        path=Path(path);calls.append(path.name)
        assert uid==gid==1000 and kwargs=={'follow_symlinks':False}
        if path.is_dir():assert sorted(p.name for p in path.iterdir())==['handoff.json','packet.json']
        else:assert path.stat().st_mode&0o777==0o600
    monkeypatch.setattr(export.os,'chown',chown)
    done=export.handoff('8'*32,packet,approve_private_export=True,journal_parent=tmp_path/'journals',handoff_parent=tmp_path/'handoffs')
    assert calls==['packet.json','handoff.json','document-'+'8'*32]
    assert Path(done['journal'],'packet.json').read_bytes()==Path(done['handoff'],'packet.json').read_bytes()
    assert done['history_records_written'] is False


def test_root_producer_cannot_run_as_normal_client(monkeypatch):
    monkeypatch.setattr(export.os,'getuid',lambda:1000)
    with pytest.raises(ValueError,match='root private'):export.snapshot('/x','a'*64,'/x','b'*64,approve_private_export=True)


def test_manifest_bytes_checked_before_source_module_import(tmp_path,monkeypatch):
    root=tmp_path/'release';root.mkdir();(root/'release-manifest.json').write_text('{}')
    monkeypatch.setattr(export,'protected',lambda p:Path(p))
    with pytest.raises(ValueError,match='manifest changed'):export.source_module(root,'a'*64)


def test_source_payload_tamper_refuses_before_import(tmp_path,monkeypatch):
    root=tmp_path/'release';path=root/'engineering/tools/rras_native/document_approval.py';path.parent.mkdir(parents=True)
    path.write_text("raise AssertionError('unverified source executed')")
    raw=c.encoded({'files':{'engineering/tools/rras_native/document_approval.py':'f'*64}});(root/'release-manifest.json').write_bytes(raw)
    monkeypatch.setattr(export,'protected',lambda p:Path(p))
    with pytest.raises(ValueError,match='payload changed'):export.source_module(root,hashlib.sha256(raw).hexdigest())
