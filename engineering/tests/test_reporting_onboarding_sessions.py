from contextlib import contextmanager
import copy
import importlib.util
from pathlib import Path
import sqlite3
import pytest
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_sessions.py'
spec=importlib.util.spec_from_file_location('planning_sessions_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_session_is_bound_to_peer_native_identity_and_expiry(tmp_path,setup_draft):
    writer,fixture,origin,value=setup_draft
    path=tmp_path/'sessions.sqlite3'
    @contextmanager
    def connect():
        db=sqlite3.connect(path)
        try:yield db
        finally:db.close()
    with connect() as db:module.Sessions.initialize(db)
    now=[100];native=[copy.deepcopy(origin)]
    active=[True]
    sessions=module.Sessions(connect,writer.grants,lambda _:native[0],lambda *_:active[0],clock=lambda:now[0])
    assert sessions.register(1234,uid(8),200)['registered']
    assert not sessions.register(1234,uid(8),200)['registered']
    assert sessions.lookup(1234,uid(8))==origin
    with pytest.raises(ValueError):sessions.lookup(4321,uid(8))
    active[0]=False
    with pytest.raises(ValueError):sessions.lookup(1234,uid(8))
    active[0]=True
    native[0]=dict(origin,source_actor=uid(99))
    with pytest.raises(ValueError):sessions.lookup(1234,uid(8))
    native[0]=origin;now[0]=200
    with pytest.raises(ValueError):sessions.lookup(1234,uid(8))


def test_registration_limits_lifetime_and_revocation(tmp_path,setup_draft):
    writer,fixture,origin,value=setup_draft
    @contextmanager
    def connect():
        db=sqlite3.connect(tmp_path/'sessions.sqlite3')
        try:yield db
        finally:db.close()
    with connect() as db:module.Sessions.initialize(db)
    sessions=module.Sessions(connect,writer.grants,lambda _:origin,lambda *_:True,clock=lambda:100)
    with pytest.raises(ValueError):sessions.register(1234,uid(8),3701)
    sessions.register(1234,uid(8),200)
    sessions.revoke(uid(8))
    with pytest.raises(ValueError):sessions.lookup(1234,uid(8))
    with pytest.raises(ValueError):sessions.register(1234,uid(8),200)
