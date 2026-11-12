from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sqlite3
from test_reporting_onboarding_work import setup_work,setup_draft,store,projects

root=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
def load(name):
    spec=importlib.util.spec_from_file_location('issue_create_test_'+name,root/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_create_and_link_replays_without_duplicate(tmp_path,setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    @contextmanager
    def connect():
        db=sqlite3.connect(tmp_path/'issues.sqlite3')
        try:yield db
        finally:db.close()
    journal=load('onboarding_issue_journal').IssueJournal(connect)
    with connect() as db:journal.initialize(db)
    calls=[]
    def create(selected,plan,proposal):calls.append((selected,plan,proposal));return issue['id']
    creator=load('onboarding_issue_create').Creator(writer.grants,lambda _:origin,lambda selected,id:issue,
        writer.store,journal,create)
    result=creator.create(1234,None,detail)
    assert result['state']=='complete' and not result['execution_authorized']
    assert creator.create(1234,None,detail)==result and len(calls)==1
    assert '<!-- rras-draft-work:' in calls[0][2]['description']


def test_uncertain_creation_does_not_repeat(tmp_path,setup_work):
    writer,fixture,origin,issue,detail,draft,access=setup_work
    @contextmanager
    def connect():
        db=sqlite3.connect(tmp_path/'issues.sqlite3')
        try:yield db
        finally:db.close()
    journal=load('onboarding_issue_journal').IssueJournal(connect)
    with connect() as db:journal.initialize(db)
    calls=[]
    def lost(*args):calls.append(1);raise TimeoutError()
    creator=load('onboarding_issue_create').Creator(writer.grants,lambda _:origin,lambda *_:issue,writer.store,journal,lost)
    assert creator.create(1234,None,detail)['state']=='uncertain'
    assert creator.create(1234,None,detail)['state']=='uncertain' and calls==[1]
