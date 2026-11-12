"""A lost create response must not trigger a duplicate Linear issue."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_issue_journal.py'
spec=importlib.util.spec_from_file_location('issue_journal_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


@pytest.fixture
def journal(tmp_path):
    path=tmp_path/'journal.sqlite3'
    @contextmanager
    def connect():
        db=sqlite3.connect(path,timeout=5)
        try:yield db
        finally:db.close()
    with connect() as db:module.IssueJournal.initialize(db)
    return module.IssueJournal(connect)


ORG='00000000-0000-4000-8000-000000000001'
PROJECT='00000000-0000-4000-8000-000000000002'
ISSUE='00000000-0000-4000-8000-000000000003'
TEAM='00000000-0000-4000-8000-000000000005'
ORIGIN=dict(organization_id=ORG,project_id=PROJECT,team_id=TEAM)
PROPOSAL=dict(title='Investigate',description='Draft work')


def test_complete_replays_without_creating_again(journal):
    calls=[]
    def create(value):calls.append(value);return ISSUE
    verify=lambda value:dict(id=value,organization_id=ORG,project_id=PROJECT,team_id=TEAM)
    assert journal.create_once(ORIGIN,'PLAN-01',PROPOSAL,create,verify)['created']
    assert journal.create_once(ORIGIN,'PLAN-01',PROPOSAL,create,verify)==dict(state='complete',issue_id=ISSUE,created=False)
    assert len(calls)==1
    with pytest.raises(ValueError):journal.create_once(ORIGIN,'PLAN-01',dict(title='different'),create,verify)


def test_lost_response_is_uncertain_and_never_retried(journal):
    calls=[]
    def create(value):calls.append(value);raise TimeoutError()
    for _ in range(2):
        assert journal.create_once(ORIGIN,'PLAN-01',PROPOSAL,create,lambda _:None)['state']=='uncertain'
    assert len(calls)==1


def test_concurrent_attempts_call_create_only_once(journal):
    calls=[]
    def create(value):calls.append(value);return ISSUE
    verify=lambda value:dict(id=value,organization_id=ORG,project_id=PROJECT,team_id=TEAM)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:journal.create_once(ORIGIN,'PLAN-01',PROPOSAL,create,verify),range(2)))
    assert len(calls)==1
    assert set(x['state'] for x in results)<={'complete','uncertain'}


def test_uncertain_result_requires_exact_verified_reconciliation(journal):
    def lost(_):raise TimeoutError()
    journal.create_once(ORIGIN,'PLAN-01',PROPOSAL,lost,lambda _:None)
    with pytest.raises(ValueError):journal.reconcile(ORIGIN,'PLAN-01',PROPOSAL,ISSUE,lambda *args:False)
    checked=[]
    def verify(issue,plan,sha):checked.append((issue,plan,sha));return True
    result=journal.reconcile(ORIGIN,'PLAN-01',PROPOSAL,ISSUE,verify)
    assert result==dict(state='complete',issue_id=ISSUE,reconciled=True)
    assert checked[0][0:2]==(ISSUE,'PLAN-01')
    assert not journal.reconcile(ORIGIN,'PLAN-01',PROPOSAL,ISSUE,verify)['reconciled']
    with pytest.raises(ValueError):
        journal.reconcile(ORIGIN,'PLAN-01',PROPOSAL,'00000000-0000-4000-8000-000000000004',verify)
