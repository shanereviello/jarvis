"""Explicit offline v1-to-v2 runtime journal migration; never starts a model.

The journal owner must stop the runtime first. A migration keeps prior rows and
marks existing sessions as legacy so they cannot silently resume in a new cwd.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3


def local(name):
    spec=importlib.util.spec_from_file_location('policy_migration_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@contextmanager
def locked(root):
    runtime=local('codex_runtime');root=runtime.private(root,True)
    path=root/'runtime.lock';fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        runtime.private(path)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise ValueError('stop the runtime before migration') from exc
        journal=runtime.private(root/'runtime.sqlite3')
        db=sqlite3.connect(journal,timeout=3);db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()
    finally:os.close(fd)


def snapshot(db, next_policy):
    runtime=local('codex_runtime');current=db.execute('SELECT body FROM policy').fetchall()
    if len(current)!=1:raise ValueError('one existing policy required')
    old=runtime.policy(json.loads(current[0][0]));new=runtime.policy(next_policy)
    if old['contract']!='codex-runtime-policy.v1' or new['contract']!='codex-runtime-policy.v2':
        raise ValueError('explicit v1 to v2 migration required')
    for key in ('organization_id','app_user_id','binary','cwd','issues'):
        if old[key]!=new[key]:raise ValueError('migration cannot change existing identity or work pins')
    if db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('legacy_sessions','policy_migrations')").fetchone():
        raise ValueError('prior migration state already exists')
    if db.execute("SELECT 1 FROM turns WHERE state NOT IN ('completed','failed','interrupted') OR state IS NULL LIMIT 1").fetchone():
        raise ValueError('active or uncertain turns require reconciliation before migration')
    fingerprints={}
    for table,order in [('policy','body'),('sessions','session'),('turns','dispatch'),('events','sequence')]:
        h=hashlib.sha256();count=0
        for row in db.execute('SELECT * FROM '+table+' ORDER BY '+order):
            item=[{'bytes':bytes(value).hex()} if isinstance(value,(bytes,bytearray,memoryview)) else value for value in row]
            h.update(runtime.encoded(item));count+=1
        fingerprints[table]=dict(count=count,sha256=h.hexdigest())
    evidence=dict(contract='codex-policy-migration-plan.v1',old_policy_sha256=hashlib.sha256(runtime.encoded(old)).hexdigest(),
        new_policy_sha256=hashlib.sha256(runtime.encoded(new)).hexdigest(),tables=fingerprints,
        legacy_sessions=fingerprints['sessions']['count'],models_started=0)
    return evidence,old,new


def plan(root,next_policy):
    with locked(root) as db:
        value,_,_=snapshot(db,next_policy)
        value['expected_sha256']=hashlib.sha256(local('codex_runtime').encoded(value)).hexdigest()
        return value


def migrate(root,next_policy,expected_sha256):
    runtime=local('codex_runtime')
    with locked(root) as db:
        value,old,new=snapshot(db,next_policy)
        digest=hashlib.sha256(runtime.encoded(value)).hexdigest()
        if digest!=expected_sha256:raise ValueError('migration plan differs; inspect journal before retry')
        db.execute('CREATE TABLE legacy_sessions(session TEXT PRIMARY KEY REFERENCES sessions(session),original_cwd TEXT NOT NULL)')
        db.execute('INSERT INTO legacy_sessions(session,original_cwd) SELECT session,? FROM sessions',(old['cwd'],))
        db.execute('CREATE TABLE policy_migrations(old_body BLOB NOT NULL,new_body BLOB NOT NULL,plan_sha256 TEXT NOT NULL)')
        db.execute('INSERT INTO policy_migrations VALUES(?,?,?)',(runtime.encoded(old),runtime.encoded(new),digest))
        db.execute('UPDATE policy SET body=?',(runtime.encoded(new),))
        return dict(migrated=True,plan_sha256=digest,legacy_sessions=value['legacy_sessions'],models_started=0)
