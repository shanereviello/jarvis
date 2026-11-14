import asyncio
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
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
    work=writer.save(1234,object(),object(),detail)
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
    async def run(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as client:
            begin=await client.post('/api/attestation/begin',headers=signed,json={'review_id':prepared['review_id'],'comment_id':uid(8)})
            assert begin.status_code==200
            result=await client.post('/api/attestation/confirm',headers=signed,json={'challenge':begin.json()['challenge'],'statement':STATEMENT})
            assert result.status_code==200 and result.json()['decision_recorded'] and not result.json()['execution_authorized']
            return result.json()
    bridge=service.local('onboarding_operator_browser_unix');transport=service.local('onboarding_broker_unix')
    with tempfile.TemporaryDirectory(prefix='rras-operator-flow-',dir='/tmp') as raw:
        socket=Path(raw)/'browser.sock';stop=threading.Event()
        with transport.server(socket,bridge.Broker(os.getuid(),selected['browser'])) as server:
            def serve():
                while not stop.is_set():server.serve_once()
            worker=threading.Thread(target=serve);worker.start()
            try:
                app=service.local('onboarding_attestation_web').create_app(bridge.Client(socket,os.getuid()),access(key))
                approved=asyncio.run(run(app))
            finally:stop.set();worker.join(5)
    assert history.project(REPO,draft['project_id'])['governing_version']==1
    assert selected['reviews'].decision_review(approved['decision_receipt_sha256'])==prepared['review_id']
    assert not selected['production_active']
    retained=writer.store.work(REPO,work['work_id'])
    request=dict(organization_id=origin['organization_id'],team_id=origin['team_id'],linear_project_id=origin['project_id'],
        issue_id=issue['id'],scope=REPO,project_id=draft['project_id'],work_id=work['work_id'],plan_id=detail['plan_id'],
        work_revision_sha256=retained['work_revision_sha256'],assignment_sha256=retained['assignment']['assignment_sha256'],
        architecture_version=1,architecture_sha256=draft['markdown_sha256'],decision_receipt_sha256=approved['decision_receipt_sha256'],
        workspace='/fixture/workspace',native_socket='/fixture/socket',baseline_commit='e'*40)
    native={key:request[key] for key in ('organization_id','team_id','linear_project_id','issue_id')}
    admission=service.local('onboarding_admission_service').assemble_history(selected,
        lambda value:operator_access.dispatch(999,value),lambda _:native)
    message=dict(operation='admission.verify',request=request)
    assert admission.dispatch(0,message)=={'history_issue_human_verified':True}
    response['data']['comment']['editedAt']='2026-11-12T12:01:00Z'
    with pytest.raises(ValueError):admission.dispatch(0,message)
