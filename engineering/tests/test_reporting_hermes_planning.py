import importlib.util
from pathlib import Path

import pytest
from test_reporting_onboarding_drafts import uid, REPO

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/hermes_planning.py'
spec=importlib.util.spec_from_file_location('hermes_planning_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture():
    native=dict(organization_id=uid(1),session_id=uid(2),hermes_session_id='linear:'+uid(1)+':'+uid(2),run_id='run_'+'a'*32)
    origin=dict(organization_id=uid(1),team_id=uid(3),project_id=uid(4),project_identifier=uid(4),
        project_url='https://linear.app/example/project/test',scope=REPO,source_session=uid(2),source_actor=uid(5),agent='jarvis')
    proposal=dict(name='Fixture',overview='Overview',intended_outcome='Outcome',in_scope='Scope',out_of_scope='None',
        markdown='# Draft\nPLAN-01',plan_ids=['PLAN-01'])
    return native,origin,proposal


def test_jarvis_tool_binds_native_session_and_never_grants_execution():
    native,origin,proposal=fixture();calls=[]
    def call(operation,frame):
        calls.append((operation,frame))
        if operation=='resolve':return dict(dispatch_id=uid(9),origin=origin,execution_authorized=False)
        return dict(saved=True,execution_authorized=False)
    adapter=module.Adapter(call,actual=lambda:native)
    assert adapter.invoke('engineering_draft_project',{'proposal':proposal}) == dict(saved=True,execution_authorized=False)
    assert calls[1][1]['native']==native and calls[1][1]['message']['dispatch_id']==uid(9)
    assert calls[1][1]['message']['operation']=='draft.project'


def test_jarvis_tool_rejects_foreign_session_and_unconfirmed_result():
    native,origin,proposal=fixture()
    origin['source_session']=uid(8)
    adapter=module.Adapter(lambda *_:dict(dispatch_id=uid(9),origin=origin,execution_authorized=False),actual=lambda:native)
    with pytest.raises(ValueError,match='origin differs'):adapter.invoke('engineering_draft_project',{'proposal':proposal})
    origin['source_session']=native['session_id']
    def call(operation,_):
        return dict(dispatch_id=uid(9),origin=origin,execution_authorized=False) if operation=='resolve' else {'saved':True}
    with pytest.raises(ValueError,match='unconfirmed'):
        module.Adapter(call,actual=lambda:native).invoke('engineering_draft_project',{'proposal':proposal})


def test_tool_registration_only_exposes_configured_planning_operations():
    tools=[]
    class Context:
        def register_tool(self,**value):tools.append(value)
    module.register(Context(),lambda:None,allow_review=True)
    assert {item['name'] for item in tools} == {'engineering_draft_project','engineering_draft_work','engineering_prepare_review'}
    assert all(item['toolset']=='engineering_planning' for item in tools)


def test_jarvis_broker_reverifies_live_origin_for_each_operation():
    broker_module=module.local('hermes_planning_broker')
    native,origin,proposal=fixture();current=[origin];calls=[]
    grant={1234:dict(agent='jarvis',organization_id=origin['organization_id'],team_id=origin['team_id'],scopes=[REPO])}
    broker=broker_module.Broker(grant,lambda peer,run:calls.append((peer,run)) or current[0],lambda *_:None,object())
    resolved=broker.resolve(1234,dict(contract='hermes-planning-native.v1',native=native))
    assert resolved['execution_authorized'] is False and len(calls)==1
    message=dict(operation='draft.project',dispatch_id=resolved['dispatch_id'],proposal=proposal)
    current[0]=dict(origin,source_session=uid(99))
    with pytest.raises(ValueError,match='origin differs'):
        broker.submit(1234,dict(contract='hermes-planning-submit.v1',native=native,message=message))
    assert len(calls)==2
    with pytest.raises(ValueError):broker.resolve(9999,dict(contract='hermes-planning-native.v1',native=native))


def test_transport_uses_only_fixed_endpoint_and_rejects_unsafe_origin(monkeypatch):
    import json
    transport=module.local('hermes_planning_transport');calls=[]
    class Response:
        status=200
        def read(self,_):return json.dumps({'execution_authorized':False}).encode()
    class Connection:
        def __init__(self,host,port,timeout):assert host=='n8n' and port==5678
        def request(self,method,path,body,headers):calls.append((method,path,json.loads(body)))
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(transport.http.client,'HTTPConnection',Connection)
    client=transport.Transport('http://n8n:5678',b'x'*32)
    assert client('resolve',{'fixture':True})=={'execution_authorized':False}
    assert calls==[('POST','/webhook/rras-jarvis-planning-resolve',{'fixture':True})]
    with pytest.raises(ValueError):client('other',{})
    with pytest.raises(ValueError):transport.Transport('http://user:secret@n8n:5678',b'x'*32)


def test_private_bridge_requires_credential_and_does_not_grant_execution():
    import http.client,json,socket,threading
    bridge=module.local('hermes_planning_http')
    class Broker:
        def resolve(self,peer,frame):
            assert peer==1234 and frame=={'fixture':True}
            return {'execution_authorized':False}
        def submit(self,peer,frame):raise AssertionError('not requested')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    server=bridge.server(Broker(),1234,b'x'*32,('127.0.0.1',port))
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        def request(token):
            connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
            connection.request('POST','/webhook/rras-jarvis-planning-resolve',body=b'{"fixture":true}',
                headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            response=connection.getresponse();value=json.loads(response.read());connection.close();return response.status,value
        assert request('wrong')[0]==403
        assert request('x'*32)==(200,{'execution_authorized':False})
    finally:server.shutdown();thread.join(5);server.server_close()


def test_native_origin_requires_active_exact_jarvis_and_independent_scope():
    native,origin,_=fixture();origin_module=module.local('hermes_planning_origin')
    record=dict(contract='hermes-planning-origin.v1',native=native,app_user_id=uid(9),active=True,source_verified=True,origin=origin)
    resolver=origin_module.Resolver(1234,native['organization_id'],uid(9),lambda _:record,lambda _:REPO)
    assert resolver(1234,native)==origin
    record['active']=False
    with pytest.raises(ValueError,match='active'):resolver(1234,native)
    record['active']=True;record['source_verified']=False
    with pytest.raises(ValueError,match='active'):resolver(1234,native)
    record['source_verified']=True
    bad=origin_module.Resolver(1234,native['organization_id'],uid(9),lambda _:record,lambda _:{'kind':'repository','id':'other'})
    with pytest.raises(ValueError,match='scope'):bad(1234,native)


def test_native_reader_rejects_issue_reply_from_other_run(monkeypatch):
    native,origin,_=fixture();reader_module=module.local('hermes_planning_reader_http');app=uid(9)
    reader=reader_module.Reader('http://127.0.0.1:5678/webhook/rras-jarvis-planning-origin-'+app,
        'http://127.0.0.1:5678/webhook/rras-jarvis-planning-issue-'+app,app,b'x'*32)
    response=dict(contract='hermes-planning-issue.v1',native=native,origin=origin,issue={'id':uid(10)},permitted=True)
    monkeypatch.setattr(reader,'request',lambda *_:response)
    assert reader.issue(native,origin,uid(10))=={'id':uid(10)}
    response['native']=dict(native,run_id='run_'+'b'*32)
    with pytest.raises(ValueError,match='native issue'):reader.issue(native,origin,uid(10))
    with pytest.raises(ValueError):
        reader_module.Reader('http://example.com:5678/webhook/rras-jarvis-planning-origin-'+app,
            'http://127.0.0.1:5678/webhook/rras-jarvis-planning-issue-'+app,app,b'x'*32)


def test_service_assembles_jarvis_only_and_separate_credentials(monkeypatch):
    from types import SimpleNamespace
    service=module.local('hermes_planning_service');captured={}
    class Reader:
        def origin(self,_):return None
        def issue(self,*_):return None
    def server(broker,peer,token,address):
        captured.update(broker=broker,peer=peer,token=token,address=address);return 'inactive-server'
    original=service.local
    monkeypatch.setattr(service,'local',lambda name:SimpleNamespace(server=server) if name=='hermes_planning_http' else original(name))
    config=dict(organization_id=uid(1),app_user_id=uid(9),team_id=uid(3),peer_uid=1234,scopes=[REPO],
        history_socket='/run/fixture.sock',history_uid=1235,reader_origin_url='unused',reader_issue_url='unused',
        listen_address='127.0.0.1',listen_port=8768)
    assert service.assemble(config,b'r'*32,b'b'*32,lambda _:REPO,reader=Reader(),history_rpc=lambda _:None)=='inactive-server'
    assert captured['broker'].grants[1234]['agent']=='jarvis'
    with pytest.raises(ValueError,match='distinct reader'):
        service.assemble(config,b'r'*32,b'r'*32,lambda _:REPO,reader=Reader(),history_rpc=lambda _:None)
    with pytest.raises(ValueError,match='journal'):
        service.assemble(dict(config,issue_creator_url='unused'),b'r'*32,b'b'*32,lambda _:REPO,reader=Reader(),history_rpc=lambda _:None)


def test_project_scope_comes_only_from_protected_map(monkeypatch):
    from types import SimpleNamespace
    scope=module.local('hermes_planning_scope');original=scope.local
    data={'contract':'hermes-planning-project-scopes.v1','projects':{uid(4):REPO}}
    monkeypatch.setattr(scope,'local',lambda name:SimpleNamespace(decode=lambda *_,**__:data) if name=='protected_config' else original(name))
    resolve=scope.Resolver('/root/protected-scope.json')
    assert resolve(uid(4))==REPO
    with pytest.raises(ValueError,match='not configured'):resolve(uid(5))
