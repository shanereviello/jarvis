from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import socket
import sqlite3
from test_reporting_onboarding_drafts import setup_draft,store,projects,uid,REPO,module

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_service.py'
spec=importlib.util.spec_from_file_location('planning_service_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_composed_service_dispatches_and_records_a_draft(tmp_path,setup_draft):
    initial,fixture,origin,proposal=setup_draft;peer=os.getuid()
    access=module('access').Access(fixture.projects.store,dict(contract='engineering-history-access.v3',principals=[
        dict(uid=peer,private_read=['jarvis'],write=[],category_read=[],category_write=[],planning_agent='codex',
             planning_organization_id=uid(1),planning_teams=[uid(2)],planning_repositories=['jarvis'],planning_categories=[])]))
    @contextmanager
    def connect():
        db=sqlite3.connect(tmp_path/'planning.sqlite3')
        try:yield db
        finally:db.close()
    with connect() as db:m.initialize_empty(db)
    class Reader:
        def origin(self,dispatch,issue_id,**kwargs):
            assert dispatch==uid(8) and issue_id==uid(7)
            return origin
        def issue(self,*args):raise ValueError('no issue in fixture')
    class Client:
        def call(self,method,arguments):
            if method=='thread/start':return {'thread':{'id':'thread','cwd':str(tmp_path)}}
            if method=='mcpServerStatus/list':return {'data':[{'name':'engineering_planning','tools':{
                'engineering_draft_project':{},'engineering_draft_work':{}}}]}
            if method=='turn/start':return {'turn':{'id':'turn'}}
            raise ValueError('unexpected native operation')
        def close(self):pass
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    config=dict(runtime_policy=dict(organization_id=uid(1),app_user_id=uid(9),peer_uid=peer,cwd=str(tmp_path),
        planning_authorized=True,authority_reference='fixture only'),team_id=uid(2),scopes=[REPO],
        history_socket='/tmp/unused-history.sock',history_uid=peer,broker_socket='/tmp/unused-planning.sock',
        native_socket='/tmp/unused-native.sock',native_peer_uid=0,mcp_python='/usr/bin/python3',lock_path=str(tmp_path/'planning.lock'),
        reader_origin_url='unused',reader_issue_url='unused',listen_address='127.0.0.1',listen_port=port)
    service=m.assemble(config,connect,b'not-used',b'fixture-private-token-with-at-least-32-bytes',
        reader=Reader(),history_rpc=lambda request:access.dispatch(peer,request),client_factory=Client,clock=lambda:100)
    try:
        event=dict(dispatch_id=uid(8),session_id=uid(4),issue_id=uid(7),organization_id=uid(1),app_user_id=uid(9),message='Plan')
        assert service.runtime.dispatch(event)['state']=='running'
        result=service.broker.dispatch(peer,dict(operation='draft.project',dispatch_id=uid(8),proposal=proposal))
        assert result['designation']=='draft' and result['execution_authorized'] is False
        service.runtime.complete(uid(8),'thread','turn','completed')
    finally:service.close()
