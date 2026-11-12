"""The broker obtains origin and issue identity from trusted callbacks."""
import importlib.util
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import pytest
from test_reporting_onboarding_work import setup_work,setup_draft,store,projects,uid

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_broker.py'
spec=importlib.util.spec_from_file_location('onboarding_broker_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_broker_uses_authenticated_dispatch_and_native_issue_read(setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    calls=[]
    def session(peer,dispatch):
        calls.append(('session',peer,dispatch))
        if (peer,dispatch)!=(1234,uid(8)):raise ValueError('not active')
        return origin
    def read(dispatch,verified,issue_id):
        assert dispatch==uid(8)
        calls.append(('read',verified['source_session'],issue_id))
        if issue_id!=issue['id']:raise ValueError('not found')
        return issue
    broker=module.Broker(writer.grants,session,read,writer.store)
    request=dict(operation='draft.work',dispatch_id=uid(8),issue_id=issue['id'],proposal=detail)
    result=broker.dispatch(1234,request)
    assert result['execution_authorized'] is False
    assert calls==[('session',1234,uid(8)),('read',origin['source_session'],issue['id'])]
    with pytest.raises(ValueError):broker.dispatch(999,request)
    with pytest.raises(ValueError):broker.dispatch(1234,dict(request,dispatch_id=uid(9)))
    with pytest.raises(ValueError):broker.dispatch(1234,dict(request,agent='jarvis'))
    with pytest.raises(ValueError):broker.dispatch(1234,dict(request,issue_id=uid(99)))


def test_broker_rejects_runtime_origin_outside_peer_grant(setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    forged=dict(origin,agent='jarvis')
    broker=module.Broker(writer.grants,lambda *_:forged,lambda *_:issue,writer.store)
    with pytest.raises(ValueError):
        broker.dispatch(1234,dict(operation='draft.work',dispatch_id=uid(8),issue_id=issue['id'],proposal=detail))


def test_optional_issue_creation_uses_the_bound_dispatch(tmp_path,setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    @contextmanager
    def connect():
        db=sqlite3.connect(tmp_path/'issue-journal.sqlite3')
        try:yield db
        finally:db.close()
    journal=module.local('onboarding_issue_journal').IssueJournal(connect)
    with connect() as db:journal.initialize(db)
    calls=[]
    def create(dispatch,selected,plan,proposal):
        calls.append((dispatch,selected,plan));return issue['id']
    broker=module.Broker(writer.grants,lambda *_:origin,lambda dispatch,selected,id:issue,writer.store,
        issue_journal=journal,issue_create=create)
    result=broker.dispatch(1234,dict(operation='draft.issue',dispatch_id=uid(8),proposal=detail))
    assert result['state']=='complete' and calls==[(uid(8),origin,'PLAN-01')]
