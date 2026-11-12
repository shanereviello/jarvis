import copy
import importlib.util
from pathlib import Path
import sqlite3
import pytest
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO
from test_reporting_onboarding_review_store import reviews

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_review_broker.py'
spec=importlib.util.spec_from_file_location('review_broker_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_active_planning_peer_prepares_only_a_review_reference(tmp_path,setup_draft):
    writer,history,origin,data=setup_draft;draft=writer.save(1234,object(),data)
    connection=lambda:sqlite3.connect(tmp_path/'reviews.sqlite3')
    with connection() as db:reviews.ReviewStore.initialize(db)
    class History:
        def project(self,scope,pid):return history.project(scope,pid)
        def architecture(self,scope,pid,version):return history.projects.read(scope,dict(view='architecture',project_id=pid,version=version))['document']
    grants={1234:dict(agent='codex',organization_id=uid(1),team_id=uid(2),scopes=[REPO])}
    issue=dict(organization_id=uid(1),team_id=uid(2),project_id=uid(3),id=uid(7),identifier='REV-7',url='https://linear.app/fixture')
    broker=module.Broker(grants,lambda peer,dispatch,selected:origin,lambda dispatch,selected,issue_id:issue,connection,History(),[REPO])
    request=dict(operation='review.prepare',dispatch_id=uid(10),issue_id=uid(7),version=1)
    result=broker.dispatch(1234,request)
    assert result['markdown_sha256']==draft['markdown_sha256'] and not result['human_approval_inferred'] and not result['execution_authorized']
    assert broker.dispatch(1234,request)==result
    with pytest.raises(ValueError):broker.dispatch(1235,request)
    with pytest.raises(ValueError):broker.dispatch(1234,dict(request,operation='decision.approve'))
    with pytest.raises(ValueError):broker.dispatch(1234,dict(request,extra=True))
    other=copy.deepcopy(issue);other['project_id']=uid(99);broker.read_issue=lambda *_:other
    with pytest.raises(ValueError):broker.dispatch(1234,request)
    assert history.project(REPO,draft['project_id'])['governing_version'] is None
