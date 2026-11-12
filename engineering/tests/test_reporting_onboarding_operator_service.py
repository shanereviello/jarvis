import asyncio
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sqlite3
import httpx
import pytest
from test_history_web import key,access,headers,token,ORIGIN
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO,module
from test_reporting_onboarding_work import setup_work
from test_reporting_human_attestation_store import STATEMENT

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_operator_service.py'
spec=importlib.util.spec_from_file_location('operator_service_fixture',path)
service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)


def test_scoped_review_to_signed_operator_decision(tmp_path,setup_work,key):
    writer,history,origin,issue,detail,draft,planning_access=setup_work
    connection=lambda:sqlite3.connect(tmp_path/'operator.sqlite3')
    with connection() as db:service.initialize_empty(db)
    grants=dict(contract='engineering-history-access.v3',principals=[dict(uid=999,private_read=['jarvis'],write=['jarvis'],
        category_read=[],category_write=[],planning_agent=None,planning_organization_id=None,planning_teams=[],planning_repositories=[],planning_categories=[])])
    operator_access=module('access').Access(history.projects.store,grants)
    class Planning:
        def origin(self,dispatch,issue_id):
            assert dispatch==uid(10) and issue_id==issue['id'];return origin
        def issue(self,dispatch,selected,issue_id):
            assert dispatch==uid(10) and selected==origin and issue_id==issue['id'];return issue
    response={'data':{'viewer':{'id':uid(9),'organization':{'id':uid(1)}},'comment':{
        'id':uid(8),'body':f"I approve architecture version 1 sha256 {draft['markdown_sha256']}",
        'createdAt':'2026-11-12T12:00:00Z','editedAt':None,'archivedAt':None,'botActor':None,'externalUser':None,'onBehalfOf':None,
        'user':{'id':uid(5),'app':False},'issue':{'id':issue['id'],'team':{'id':uid(2)},'project':{'id':uid(3)}}}}}
    config=dict(organization_id=uid(1),app_user_id=uid(9),team_id=uid(2),human_ids=[uid(5)],planning_peer_uid=1234,scopes=[REPO])
    selected=service.assemble(config,connection,access(key),Planning(),lambda _:response,lambda value:operator_access.dispatch(999,value))
    prepared=selected['review_broker'].dispatch(1234,dict(operation='review.prepare',dispatch_id=uid(10),issue_id=issue['id'],version=1))
    assert not prepared['execution_authorized'] and history.project(REPO,draft['project_id'])['governing_version'] is None
    with pytest.raises(ValueError):selected['review_broker'].dispatch(1234,dict(operation='decision.approve',dispatch_id=uid(10),issue_id=issue['id'],version=1))
    signed={k.decode():v.decode() for k,v in headers(token(key))};signed['origin']=ORIGIN
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=selected['app']),base_url=ORIGIN) as client:
            begin=await client.post('/api/attestation/begin',headers=signed,json={'review_id':prepared['review_id'],'comment_id':uid(8)})
            assert begin.status_code==200
            result=await client.post('/api/attestation/confirm',headers=signed,json={'challenge':begin.json()['challenge'],'statement':STATEMENT})
            assert result.status_code==200 and result.json()['decision_recorded'] and not result.json()['execution_authorized']
            return result.json()
    approved=asyncio.run(run())
    assert history.project(REPO,draft['project_id'])['governing_version']==1
    assert selected['reviews'].decision_review(approved['decision_receipt_sha256'])==prepared['review_id']
    assert not selected['production_active']
