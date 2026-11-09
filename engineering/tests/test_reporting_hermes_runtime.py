"""Native Jarvis tool staging, source attribution and outage-safe delivery."""
import copy
import importlib.util
import json
from pathlib import Path
import threading
import pytest
from test_reporting_runtime_reporting import setup,m,projects,reporting,store
from test_reporting_codex_runtime import uid


hermes=m.local('hermes_runtime')


def installed(tmp_path,projects):
    codex,config,_,_,_=setup(tmp_path,projects)
    queue=m.local('runtime_handoff').Queue(tmp_path/'native-queue',create=True)
    policy=dict(contract='native-agent-handoff-policy.v1',organization_id=uid(1),agents=dict(codex=uid(2),jarvis=uid(20)),issues=codex['issues'])
    native=dict(organization_id=uid(1),session_id=uid(5),hermes_session_id='linear:'+uid(1)+':'+uid(5),run_id='run_'+'a'*32)
    context=dict(session_id=uid(5),issue_id=uid(3),binding=policy['issues'][uid(3)],parent_handoff_id=None,depth=0,delivery_id=uid(8))
    configuration=dict(contract='hermes-native-reporting.v1',policy=policy,scope=config['scope'],contexts=config['contexts'],queue=str(queue.path),
        origin='http://127.0.0.1:5678',token_file='/not-read-in-fixture')
    return configuration,native,context,queue


def args(operation):
    if operation=='checkpoint':return dict(key='finding-1',observations=['Observed the selected problem; api_key=sk-fixture-DO-NOT-RETAIN-123456789'],next_step='Validate the correction.')
    return dict(key='engineering-investigation',summary='Investigate the selected failure.',requested_action='Review code under the agreed architecture.',references=[],limitations=['No new execution authority is granted.'])


@pytest.mark.parametrize('operation',['checkpoint','handoff'])
def test_tool_stages_actual_native_source_then_delivers_same_work(tmp_path,projects,reporting,operation):
    config,native,context,queue=installed(tmp_path,projects);calls=[]
    def call(kind,value):
        calls.append((kind,value))
        if kind=='context':return dict(context=context,execution_started=False)
        return dict(staged=True,request_id=value['id'],execution_started=False)
    adapter=hermes.Adapter(config,actual=lambda:native,call=call)
    first=adapter.record(operation,args(operation));assert first['staged'] and not first['authority_granted'] and not calls
    assert adapter.record(operation,args(operation))['replayed']
    with queue.connection() as db:assert b'sk-fixture-DO-NOT-RETAIN' not in db.execute('SELECT intent FROM handoffs').fetchone()[0]
    assert adapter.flush()==dict(delivered=1,pending=0,models_started=0)
    assert calls[0][1]==dict(contract='jarvis-native-context.v1',**native)
    delivered=calls[-1][1]
    if operation=='handoff':
        assert delivered['sender']=='jarvis' and delivered['recipient']=='codex' and delivered['binding']==context['binding']
        assert delivered['source_session_id']==native['session_id']
    else:
        report=delivered['report'];assert report['context']==config['contexts'][uid(3)]
        assert report['source']==dict(kind='agent_reported',namespace='hermes_runtime_adapter',id=native['run_id'])
        assert report['body']['attempt_id'].startswith('att_')
    assert adapter.flush()['delivered']==0


def test_native_report_survives_transport_outage_without_worker_rerun(tmp_path,projects,reporting):
    config,native,context,queue=installed(tmp_path,projects)
    adapter=hermes.Adapter(config,actual=lambda:native,call=lambda *_:(_ for _ in ()).throw(OSError('synthetic outage')))
    adapter.record('handoff',args('handoff'));assert adapter.flush()['pending']==1
    seen=[]
    def recover(kind,value):
        seen.append((kind,value))
        return dict(context=context,execution_started=False) if kind=='context' else dict(staged=True,request_id=value['id'],execution_started=False)
    restarted=hermes.Adapter(config,actual=lambda:(_ for _ in ()).throw(AssertionError('passive delivery must not ask for an active run')),call=recover)
    assert restarted.flush()['pending']==0 and [kind for kind,_ in seen]==['context','handoff']


def test_wrong_retained_binding_and_caller_identity_fields_are_refused(tmp_path,projects,reporting):
    from jsonschema import ValidationError
    config,native,context,queue=installed(tmp_path,projects);seen=[]
    bad=copy.deepcopy(context);bad['binding']['architecture_sha256']='9'*64
    def call(kind,value):seen.append(kind);return dict(context=bad,execution_started=False)
    adapter=hermes.Adapter(config,actual=lambda:native,call=call)
    for field in ('work_item_id','session_id','approved','app_user_id'):
        with pytest.raises(ValidationError):adapter.record('checkpoint',dict(args('checkpoint'),**{field:'spoof'}))
    adapter.record('checkpoint',args('checkpoint'));assert adapter.flush()['pending']==1 and seen==['context']


def test_exhausted_handoff_does_not_block_independent_checkpoint_delivery(tmp_path,projects,reporting):
    config,native,context,queue=installed(tmp_path,projects);context.update(parent_handoff_id=uid(80),depth=4);posted=[]
    def call(kind,value):
        if kind=='context':return dict(context=context,execution_started=False)
        posted.append(kind);return dict(staged=True,request_id=value['id'],execution_started=False)
    adapter=hermes.Adapter(config,actual=lambda:native,call=call)
    adapter.record('handoff',args('handoff'));adapter.record('checkpoint',args('checkpoint'))
    assert adapter.flush()==dict(delivered=1,pending=1,models_started=0) and posted==['checkpoint']


def test_concurrent_recovery_sends_one_frozen_request(tmp_path,projects,reporting):
    config,native,context,queue=installed(tmp_path,projects)
    entered=threading.Event();release=threading.Event();posted=[]
    def call(kind,value):
        if kind=='context':return dict(context=context,execution_started=False)
        posted.append(value['id']);entered.set();assert release.wait(5)
        return dict(staged=True,request_id=value['id'],execution_started=False)
    adapter=hermes.Adapter(config,actual=lambda:native,call=call)
    adapter.record('handoff',args('handoff'))
    results=[]
    first=threading.Thread(target=lambda:results.append(adapter.flush()))
    second=threading.Thread(target=lambda:results.append(adapter.flush()))
    first.start();assert entered.wait(5);second.start();release.set()
    first.join(5);second.join(5)
    assert not first.is_alive() and not second.is_alive()
    assert len(posted)==1 and sum(r['delivered'] for r in results)==1


def test_passive_worker_recovers_without_native_run(tmp_path,projects,reporting,monkeypatch):
    config,native,context,queue=installed(tmp_path,projects)
    down=hermes.Adapter(config,actual=lambda:native,call=lambda *_:(_ for _ in ()).throw(OSError('offline')))
    down.record('handoff',args('handoff'));assert down.flush()['pending']==1
    delivered=threading.Event()
    def call(kind,value):
        if kind=='context':return dict(context=context,execution_started=False)
        delivered.set();return dict(staged=True,request_id=value['id'],execution_started=False)
    recovered=hermes.Adapter(config,actual=lambda:(_ for _ in ()).throw(AssertionError('no run should start')),call=call)
    original=hermes.local
    class Protected:
        @staticmethod
        def decode(*_args,**_kwargs):return config
    monkeypatch.setattr(hermes,'local',lambda name:Protected if name=='protected_config' else original(name))
    monkeypatch.setattr(hermes,'Adapter',lambda _config:recovered)
    stop,thread=hermes.start_delivery_worker('/fixture',interval=1)
    try:assert delivered.wait(5)
    finally:stop.set();thread.join(5)
    assert not thread.is_alive() and recovered.flush()['pending']==0


def test_plugin_registers_cleanup_for_passive_worker(monkeypatch):
    wrapper_path=Path(__file__).resolve().parents[1]/'hermes_plugins/engineering-reporting/__init__.py'
    spec=importlib.util.spec_from_file_location('test_engineering_plugin',wrapper_path)
    wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
    stop=threading.Event();calls=[]
    class Protected:
        @staticmethod
        def decode(path,**kwargs):calls.append(('decode',str(path)));return {'fixture':True}
    class Runtime:
        @staticmethod
        def local(name):assert name=='protected_config';return Protected
        @staticmethod
        def Adapter(config):assert config=={'fixture':True}
        @staticmethod
        def register(ctx,path):calls.append(('register',str(path)))
        @staticmethod
        def start_delivery_worker(path):return stop,None
    class Loader:
        def exec_module(self,module):pass
    class Spec:loader=Loader()
    class Context:
        def on_unload(self,callback):self.cleanup=callback
    monkeypatch.setattr(wrapper.importlib.util,'spec_from_file_location',lambda *_:Spec())
    monkeypatch.setattr(wrapper.importlib.util,'module_from_spec',lambda _:Runtime)
    ctx=Context();wrapper.register(ctx)
    assert [item[0] for item in calls]==['decode','register']
    ctx.cleanup();assert stop.is_set()
