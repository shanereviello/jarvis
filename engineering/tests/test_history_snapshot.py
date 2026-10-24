"""Consistent real SQLite snapshots; no encryption/readiness claims."""
import os
import sqlite3
import pytest
from test_engineering_history_local import module,request,document

s=module('snapshot');store_module=module('store')


def test_snapshot_preserves_receipts_documents_outbox_and_replay(tmp_path):
    tmp_path.chmod(0o700);root=tmp_path/'store';root.mkdir(mode=0o700)
    live=store_module.Store(root,create=True)
    req=request();receipt=live.submit(req)['receipt']
    live.submit(document(receipt['work_revision_sha256']))
    before=live.path.read_bytes()
    result=s.capture(live.path,tmp_path/'snapshot')
    restored=store_module.Store(tmp_path/'snapshot')
    assert restored.history()==live.history()
    assert restored.pending()==live.pending()
    assert restored.submit(req)['receipt']==receipt
    assert live.path.read_bytes()==before
    assert result['encrypted'] is False and result['production_backup_ready'] is False
    with pytest.raises(FileExistsError):s.capture(live.path,tmp_path/'snapshot')


def test_snapshot_refuses_public_input_and_symlink(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'db';path.write_bytes(b'x');path.chmod(0o644)
    with pytest.raises(ValueError,match='private'):s.capture(path,tmp_path/'snapshot')
    path.chmod(0o600);link=tmp_path/'link';link.symlink_to(path)
    with pytest.raises(ValueError,match='private'):s.capture(link,tmp_path/'snapshot')


def test_snapshot_refuses_unknown_schema_and_retains_failure(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'db'
    with sqlite3.connect(path) as db:db.execute('PRAGMA user_version=99')
    path.chmod(0o600)
    with pytest.raises(ValueError,match='schema'):s.capture(path,tmp_path/'snapshot')
    assert (tmp_path/'snapshot/history.sqlite3').exists()
    assert not (tmp_path/'snapshot/snapshot-manifest.json').exists()
