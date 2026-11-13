import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_reporting_hermes_planning import fixture
from test_reporting_n8n_codex import uid


path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/hermes_planning_review_broker.py'
spec=importlib.util.spec_from_file_location('hermes_review_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_review_requires_correct_peer_and_verified_origin(monkeypatch):
    native,origin,_=fixture();issue=uid(8);calls=[]
    class Store:
        def __init__(self,connection,history,read,scopes):self.read_issue=read
        def prepare(self,actual,issue_id,version):
            assert actual==origin and self.read_issue(issue_id)['id']==issue
            calls.append(version);return uid(9)
        def read(self,review_id):return dict(project_id='project',issue_id=issue,version=1,markdown_sha256='a'*64)
    original=module.local
    monkeypatch.setattr(module,'local',lambda name:SimpleNamespace(ReviewStore=Store) if name=='onboarding_review_store' else original(name))
    selected={key:origin[key] for key in ('organization_id','team_id','project_id')};selected['id']=issue
    broker=module.Broker(1234,lambda peer,n:origin,lambda n,o,i:selected,lambda:None,None,[origin['scope']],origin['team_id'])
    msg=dict(operation='review.prepare',native=native,issue_id=issue,version=1)
    with pytest.raises(ValueError):broker.dispatch(1235,msg)
    result=broker.dispatch(1234,msg)
    assert result['execution_authorized'] is False and result['human_approval_inferred'] is False and calls==[1]
    broker.team_id=uid(100)
    with pytest.raises(ValueError):broker.dispatch(1234,msg)
