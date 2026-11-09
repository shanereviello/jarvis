"""Model-free runtime protocol, actual journal restart, cancellation and HTTP tests."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location('runtime_test_'+name, ROOT/'tools/rras_reporting'/(name+'.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value
m = module('codex_runtime')
def uid(n): return str(uuid.UUID(int=n))


def test_sigterm_removes_owned_checkpoint_socket_and_closes_runtime(tmp_path):
    script = r'''
import importlib.util,sys,time
from pathlib import Path
root=Path(sys.argv[1]);folder=Path(sys.argv[2]);entry=root/'tools/rras_reporting/codex_runtime_http.py'
s=importlib.util.spec_from_file_location('http_entry',entry);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
u=importlib.util.spec_from_file_location('unix_entry',root/'tools/rras_history/unix.py');unix=importlib.util.module_from_spec(u);u.loader.exec_module(unix)
broker=unix.Server.__new__(unix.Server);broker.path=folder/'checkpoint.sock';broker.listener=None;broker.identity=None;broker.on_bound=None
class Http:
 def serve_forever(self):
  (folder/'ready').write_text('ready')
  while True:time.sleep(.1)
 def server_close(self):(folder/'http-closed').write_text('closed')
class Runtime:
 def close(self):(folder/'runtime-closed').write_text('closed')
m.serve(Http(),broker,Runtime())
'''
    child=subprocess.Popen([sys.executable,'-I','-c',script,str(ROOT),str(tmp_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+10
        while not (tmp_path/'ready').exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.05)
        assert (tmp_path/'ready').exists(),child.stderr.read().decode() if child.poll() is not None else 'child did not become ready'
        assert (tmp_path/'checkpoint.sock').exists()
        os.kill(child.pid,signal.SIGTERM)
        _,error=child.communicate(timeout=10)
        assert child.returncode==0,error.decode()
        assert not (tmp_path/'checkpoint.sock').exists()
        assert (tmp_path/'runtime-closed').exists() and (tmp_path/'http-closed').exists()
    finally:
        if child.poll() is None:child.kill();child.communicate()


class Client:
    def __init__(self, *args): self.calls=[]; self.waiting=[]; self.closed=False; self.fail=None; self.complete=False
    def call(self, method, params):
        self.calls.append((method,params))
        if self.fail == method: raise ValueError('synthetic lost response')
        if method.startswith('thread/'):
            return dict(thread=dict(id='thread-1',sessionId='root-lineage-1'))
        if method == 'turn/start':
            if self.complete: self.finish('completed')
            return dict(turn=dict(id='turn-'+str(sum(k=='turn/start' for k,_ in self.calls))))
        if method == 'turn/interrupt':
            self.finish('interrupted'); return {}
        raise AssertionError(method)
    def finish(self, status):
        turn='turn-'+str(sum(k=='turn/start' for k,_ in self.calls))
        self.waiting.extend([
            dict(method='item/completed',params=dict(threadId='thread-1',turnId=turn,item=dict(type='agentMessage',text='Synthetic engineering result.'))),
            dict(method='turn/completed',params=dict(threadId='thread-1',turn=dict(id=turn,status=status)))])
    def events(self): result,self.waiting=self.waiting,[]; return result
    def close(self): self.closed=True


@pytest.fixture
def policy(tmp_path):
    return dict(contract='codex-runtime-policy.v1',organization_id=uid(1),app_user_id=uid(2),
        execution_authorized=True,execution_authority_reference='synthetic fixture only; no provider calls',
        binary=str(tmp_path/'synthetic-codex'),cwd=str(tmp_path),sandbox='read-only',issues={uid(3):dict(
            project_id='prj_'+'1'*32,work_id='wrk_'+'2'*32,plan_id='SHRR-03',work_revision_sha256='3'*64,
            architecture_version=4,architecture_sha256='4'*64)})


@pytest.fixture
def runtime(tmp_path, policy):
    client=Client(); runtime=m.Runtime(tmp_path/'state',policy,create=True,client_factory=lambda *args:client)
    yield runtime,client
    runtime.close()


def request(policy, number=4, session=5):
    return dict(contract='codex-dispatch.v1',dispatch_id=uid(number),organization_id=policy['organization_id'],
        app_user_id=policy['app_user_id'],session_id=uid(session),issue_id=uid(3),message='Synthetic direct operator request.',
        binding=copy.deepcopy(policy['issues'][uid(3)]))


def test_dispatch_ack_and_exact_replay_never_start_second_turn(runtime,policy):
    value,client=runtime; req=request(policy)
    first=value.dispatch(req)
    assert first['state']=='running' and first['thread']=='thread-1'
    assert value.dispatch(req)==first
    assert len([k for k,_ in client.calls if k=='turn/start'])==1
    req['message']='changed'
    with pytest.raises(ValueError,match='identity changed'): value.dispatch(req)
    client.finish('completed'); assert value.status(uid(4))['result']=='Synthetic engineering result.'
    value.dispatch(request(policy,6))
    assert client.calls[-2][0]=='thread/resume'
    assert client.calls[-2][1]['sandbox']=='read-only'
    assert client.calls[-2][1]['cwd']==policy['cwd']
    assert 'Pinned engineering context' in client.calls[-1][1]['input'][0]['text']


@pytest.mark.parametrize('field',['organization_id','app_user_id','issue_id','binding','command','message'])
def test_wrong_context_and_worker_selected_commands_never_dispatch(runtime,policy,field):
    value,client=runtime; req=request(policy)
    if field=='binding': req[field]['architecture_sha256']='9'*64
    elif field=='command': req[field]='arbitrary command'
    elif field=='message': req[field]='x'*(m.MAX_MESSAGE+1)
    else: req[field]=uid(99)
    with pytest.raises(ValueError):value.dispatch(req)
    assert client.calls==[]


def test_execution_authority_cannot_come_from_webhook(tmp_path,policy):
    policy['execution_authorized']=False; client=Client()
    value=m.Runtime(tmp_path/'disabled',policy,create=True,client_factory=lambda *a:client)
    with pytest.raises(ValueError,match='not authorized'):value.dispatch(request(policy))
    assert client.calls==[]
    value.close()


def test_http_distinguishes_pre_dispatch_refusal_from_uncertain_execution(tmp_path,policy):
    policy['execution_authorized']=False;client=Client()
    value=m.Runtime(tmp_path/'disarmed-http',policy,create=True,client_factory=lambda *a:client)
    http=module('codex_runtime_http').server(value,b'synthetic-bridge-credential-32-bytes',('127.0.0.1',0))
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:
        req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+'/v1/dispatch',
            data=m.encoded(request(policy)),headers={'Content-Type':'application/json',
                'Authorization':'Bearer synthetic-bridge-credential-32-bytes'})
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(req,timeout=3)
        assert error.value.code==403
        assert json.load(error.value)==dict(contract='codex-admission-refusal.v1',dispatch=uid(4),state='failed',reason='execution_not_authorized')
        assert client.calls==[]
        with value.connection() as db:assert db.execute('SELECT count(*) FROM turns').fetchone()[0]==0
    finally:http.shutdown();http.server_close();thread.join(3);value.close()


def test_runtime_journal_excludes_reasoning_deltas_and_nested_private_fields(runtime,policy):
    value,client=runtime;value.dispatch(request(policy))
    client.waiting=[dict(method='item/reasoning/textDelta',params=dict(delta='EXCLUDED-REASONING')),
        dict(method='item/completed',params=dict(threadId='thread-1',turnId='turn-1',item=dict(type='reasoning',text='EXCLUDED-REASONING'))),
        dict(method='item/completed',params=dict(threadId='thread-1',turnId='turn-1',item=dict(type='agentMessage',phase='analysis',text='EXCLUDED-REASONING'))),
        dict(method='item/completed',params=dict(threadId='thread-1',turnId='turn-1',item=dict(type='agentMessage',text='Visible final',reasoning='EXCLUDED-REASONING'))),
        dict(method='turn/completed',params=dict(threadId='thread-1',turn=dict(id='turn-1',status='completed',
            items=[dict(type='reasoning',text='EXCLUDED-REASONING')])))]
    assert value.status(uid(4))['result']=='Visible final'
    with value.connection() as db:
        saved=[x[0] for x in db.execute('SELECT body FROM events')]
        lifecycle=[x for x in saved if b'adapter/threadMetadata' not in x]
        assert len(lifecycle)==2 and all(b'EXCLUDED-REASONING' not in x for x in saved)


def test_one_issue_executor_across_sessions_and_real_turn_interrupt(runtime,policy):
    value,client=runtime; value.dispatch(request(policy))
    with pytest.raises(ValueError,match='active or uncertain'): value.dispatch(request(policy,6,7))
    assert value.interrupt(uid(4))['state']=='interrupted'
    assert client.calls[-1]==('turn/interrupt',dict(threadId='thread-1',turnId='turn-1'))
    assert value.interrupt(uid(4))['state']=='interrupted'


def test_lost_dispatch_response_survives_restart_and_prevents_rerun(runtime,policy):
    value,client=runtime; client.fail='turn/start'
    with pytest.raises(ValueError,match='uncertain'):value.dispatch(request(policy))
    assert value.status(uid(4))['state']=='uncertain'
    assert value.dispatch(request(policy))['state']=='uncertain'
    value.close()
    other=Client(); restarted=m.Runtime(value.root,policy,client_factory=lambda *a:other)
    assert restarted.dispatch(request(policy))['state']=='uncertain'
    assert not other.calls
    with pytest.raises(ValueError,match='active or uncertain'):restarted.dispatch(request(policy,6))
    with pytest.raises(ValueError):restarted.interrupt(uid(4))
    restarted.close()


def test_completion_arriving_before_rpc_response_is_retained(runtime,policy):
    value,client=runtime; client.complete=True
    assert value.dispatch(request(policy))['state']=='completed'


def test_restart_does_not_claim_a_running_turn_finished(runtime,policy):
    value,client=runtime;value.dispatch(request(policy));value.close()
    restarted=m.Runtime(value.root,policy,client_factory=Client)
    assert restarted.status(uid(4))['state']=='uncertain'
    assert restarted.client.calls==[('thread/read',dict(threadId='thread-1',includeTurns=True))]
    restarted.close()


def test_journal_policy_and_privacy_cannot_be_changed(runtime,policy):
    value,_=runtime
    changed=copy.deepcopy(policy);changed['app_user_id']=uid(88)
    with pytest.raises(ValueError,match='policy differs'):m.Runtime(value.root,changed)
    value.path.chmod(0o644)
    with pytest.raises(ValueError,match='private'):m.Runtime(value.root,policy)
    value.path.chmod(0o600)


def test_private_http_auth_context_and_interrupt(runtime,policy):
    value,client=runtime; http=module('codex_runtime_http')
    server=http.server(value,b'synthetic-bridge-credential-32-bytes',('127.0.0.1',0))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    def send(path,body=None,auth=True):
        headers={'Content-Type':'application/json'}
        if auth:headers['Authorization']='Bearer synthetic-bridge-credential-32-bytes'
        req=urllib.request.Request(base+path,data=None if body is None else m.encoded(body),headers=headers)
        return urllib.request.urlopen(req,timeout=3)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:send('/v1/dispatch',request(policy),False)
        assert e.value.code==403 and not client.calls
        response=send('/v1/dispatch',request(policy));assert response.status==202
        assert json.load(send('/v1/runs/'+uid(4)))['state']=='running'
        assert json.load(send('/v1/interrupt',dict(dispatch_id=uid(4))))['state']=='interrupted'
        with pytest.raises(urllib.error.HTTPError):send('/v1/dispatch?untrusted=1',request(policy,6))
    finally:server.shutdown();server.server_close();thread.join(3)


def test_real_stdio_rpc_with_model_free_executable(tmp_path):
    executable=tmp_path/'fake-codex'
    executable.write_text('''#!/usr/bin/env python3
import json,sys
for line in sys.stdin:
 v=json.loads(line)
 if 'id' not in v: continue
 if v['method']=='initialize': result={'userAgent':'synthetic'}
 else:
  print(json.dumps({'method':'item/reasoning/textDelta','params':{'delta':'excluded synthetic reasoning'}}),flush=True)
  print(json.dumps({'method':'turn/completed','params':{'threadId':'synthetic-thread','turn':{'id':'synthetic-turn','status':'completed','items':[{'type':'reasoning','text':'excluded synthetic reasoning'}]}}}),flush=True)
  result={'thread':{'id':'synthetic-thread'}}
 print(json.dumps({'id':v['id'],'result':result}),flush=True)
''')
    executable.chmod(0o700)
    client=m.AppServer(str(executable),str(tmp_path),timeout=3)
    try:
        assert client.call('thread/start',{})['thread']['id']=='synthetic-thread'
        events=client.events()
        assert len(events)==1 and events[0]['method']=='turn/completed'
        assert 'excluded synthetic reasoning' not in json.dumps(events)
    finally:client.close()


def test_second_process_cannot_own_same_journal(runtime,policy):
    value,_=runtime
    with pytest.raises(ValueError,match='another adapter'):m.Runtime(value.root,policy)


def test_different_issues_cannot_edit_same_fixed_worktree(tmp_path,policy):
    policy['issues'][uid(30)]=dict(policy['issues'][uid(3)],work_id='wrk_'+'9'*32,plan_id='SHRR-04')
    client=Client();value=m.Runtime(tmp_path/'workspace',policy,create=True,client_factory=lambda *a:client)
    try:
        value.dispatch(request(policy))
        other=request(policy,6,7);other['issue_id']=uid(30);other['binding']=policy['issues'][uid(30)]
        with pytest.raises(ValueError,match='workspace has an active'):value.dispatch(other)
        assert len([m for m,_ in client.calls if m=='turn/start'])==1
    finally:value.close()


@pytest.mark.parametrize('terminal',['completed','failed','interrupted'])
def test_restart_recovers_only_the_exact_saved_terminal_turn(tmp_path,policy,terminal):
    first=Client();value=m.Runtime(tmp_path/'recover',policy,create=True,client_factory=lambda *a:first)
    value.dispatch(request(policy));value.close()
    class Reader(Client):
        def call(self,method,params):
            self.calls.append((method,params))
            assert method=='thread/read'
            return dict(thread=dict(id='thread-1',cwd=policy['cwd'],turns=[
                dict(id='turn-1',status=terminal,items=[dict(type='agentMessage',text='Recovered exact result.')]),
                dict(id='later-unrelated-turn',status='completed',items=[dict(type='agentMessage',text='Do not substitute.')])]))
    reader=Reader();restarted=m.Runtime(value.root,policy,client_factory=lambda *a:reader)
    try:
        result=restarted.status(uid(4))
        assert result['state']==terminal and result['result']=='Recovered exact result.'
        assert reader.calls==[('thread/read',dict(threadId='thread-1',includeTurns=True))]
        assert restarted.dispatch(request(policy))['state']==terminal
        assert len(reader.calls)==1
    finally:restarted.close()


@pytest.mark.parametrize('change',['wrong_thread','wrong_cwd','missing_turn','active','duplicate_turn','malformed_items'])
def test_restart_reconciliation_never_guesses_a_result(tmp_path,policy,change):
    first=Client();value=m.Runtime(tmp_path/'unresolved',policy,create=True,client_factory=lambda *a:first)
    value.dispatch(request(policy));value.close()
    class Reader(Client):
        def call(self,method,params):
            self.calls.append((method,params));assert method=='thread/read'
            turn=dict(id='turn-1',status='completed',items=[])
            thread=dict(id='thread-1',cwd=policy['cwd'],turns=[turn])
            if change=='wrong_thread':thread['id']='other-thread'
            elif change=='wrong_cwd':thread['cwd']='/'
            elif change=='missing_turn':turn['id']='later-turn'
            elif change=='active':turn['status']='inProgress'
            elif change=='duplicate_turn':thread['turns'].append(dict(turn))
            elif change=='malformed_items':turn['items']=[None]
            return dict(thread=thread)
    reader=Reader();restarted=m.Runtime(value.root,policy,client_factory=lambda *a:reader)
    try:
        assert restarted.status(uid(4))['state']=='uncertain'
        with pytest.raises(ValueError,match='active or uncertain'):restarted.dispatch(request(policy,6,7))
        assert all(method=='thread/read' for method,_ in reader.calls)
    finally:restarted.close()
