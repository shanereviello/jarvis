"""Real disposable custody/wrapper files; explicit fake root, Docker and gateway.

No production services, network, credentials or privileged subprocesses are used.
"""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from test_workflow_upgrade_staging import fixture, stage

@pytest.fixture
def engine(fixture,monkeypatch):
    f=fixture;s=f.m
    f.container.update(Config={'Hostname':'original','Image':'pinned-tag','Env':['FIXTURE=private'],'Labels':{}},
        HostConfig={'AutoRemove':False,'Binds':None,'VolumesFrom':None,'OomKillDisable':False,'Mounts':[
            {'Source':v[0],'Target':k,'Type':'bind','ReadOnly':not v[1]} for k,v in s.mounts(f.plan['installed_release']).items()]},
        NetworkSettings={'Networks':{'jarvis-net':{'Aliases':['hermes','jarvis',f.container['Id'][:12]]}}})
    stage(f)
    spec=importlib.util.spec_from_file_location('activation',Path(s.__file__).with_name('activate_workflow_upgrade.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m.os,'getuid',lambda:0);monkeypatch.setattr(m.os,'geteuid',lambda:0)
    rows={f.container['Id']:f.container};calls=[];states={f.container['Id']:'running'};fail={'after':None,'before':None}
    def api(method,path,body=None):
        calls.append((method,path))
        if fail['before'] and fail['before'] in path:raise OSError('fixture before mutation')
        part=path.removeprefix('/containers/');ref=part.split('/')[0]
        row=next((r for r in rows.values() if r['Id']==ref or r['Name']=='/'+ref),None)
        if method=='GET':return copy.deepcopy(row)
        if part.startswith('create?'):
            cid='c'*64;config={k:copy.deepcopy(v) for k,v in body.items() if k not in ('HostConfig','NetworkingConfig')};config['Hostname']=cid[:12]
            rows[cid]={'Id':cid,'Name':'/'+part.split('name=')[1],'Image':body['Image'],'Config':config,'HostConfig':copy.deepcopy(body['HostConfig']),
                'State':{'Running':False},'Mounts':[{'Source':v['Source'],'Destination':v['Target'],'RW':not v['ReadOnly'],'Type':v['Type']} for v in body['HostConfig']['Mounts']],
                'NetworkSettings':{'Networks':copy.deepcopy(body['NetworkingConfig']['EndpointsConfig'])}}
            states[cid]='running';result={'Id':cid}
        else:
            assert row is not None
            if '/stop?' in part:row['State']['Running']=False
            elif '/start' in part:row['State']['Running']=True;states[ref]='running'
            elif '/rename?' in part:
                name='/'+part.split('name=')[1];assert not any(r['Name']==name for r in rows.values());row['Name']=name
            else:raise AssertionError(path)
            result=None
        if fail['after'] and fail['after'] in path:raise OSError('fixture response lost')
        return result
    monkeypatch.setattr(m,'api',api)
    e=m.Upgrade(f.journal,f.digest,stage=s)
    def rpc(ref,script,*args):
        if script==m.STATUS:return {'live':True,'fresh':True,'state':states[ref],'active_agents':0,'pid':23,'start_time':'fixed'}
        if script==m.DRAIN:
            raw=s.encoded({'principal':args[0],'epoch':'fixture-epoch'});s.write(e.marker,raw)
            states[ref]='draining';return {'sha256':s.sha(raw),'epoch':'fixture-epoch'}
        assert script==m.DISCOVERY;return {'verified':True}
    monkeypatch.setattr(e,'rpc',rpc)
    # Drain marker role is independently asserted in production; fixture uid may
    # differ. Only the metadata adapter translates this one disposable marker.
    actual=m.metadata
    def metadata(path):
        value=actual(path)
        if Path(path)==e.marker:value['uid']=1000
        return value
    monkeypatch.setattr(m,'metadata',metadata)
    return SimpleNamespace(e=e,f=f,m=m,rows=rows,calls=calls,states=states,fail=fail)


def test_roundtrip_preserves_later_journal_and_history(engine):
    x=engine;e=x.e;f=x.f
    assert e.preflight()['service_mutations'] is False
    assert not e.directory.exists()
    assert e.activate(True)['phase']=='complete'
    assert x.rows['c'*64]['Name']=='/hermes'
    assert not x.rows[f.container['Id']]['State']['Running']
    for name,entry in f.m.WRAPPERS.items():assert (f.m.SBIN/name).read_bytes()==f.m.wrapper(f.release,entry)
    f.m.JOURNAL_DB.write_bytes(b'legitimate new journal data');(f.m.HISTORY/'index.json').write_bytes(b'{"new":true}')
    assert e.rollback(True)['phase']=='rolled_back'
    assert len(x.rows)==2 and x.rows[f.container['Id']]['Name']=='/hermes'
    assert x.rows[f.container['Id']]['State']['Running'] and not x.rows['c'*64]['State']['Running']
    assert f.m.JOURNAL_DB.read_bytes()==b'legitimate new journal data'
    assert (f.m.HISTORY/'index.json').read_bytes()==b'{"new":true}'
    for name,entry in f.m.WRAPPERS.items():assert (f.m.SBIN/name).read_bytes()==f.m.wrapper(f.plan['installed_release'],entry)
    with pytest.raises(ValueError,match='fenced'):e.activate(True)
    assert not any('/delete' in p for _,p in x.calls)

@pytest.mark.parametrize('action',['activate','rollback'])
def test_separate_approval_required(engine,action):
    with pytest.raises(ValueError,match='approval'):getattr(engine.e,action)()
    assert not engine.calls

@pytest.mark.parametrize('point',['/stop?','/rename?','create?','/start'])
def test_lost_response_retains_intent_and_explicit_rollback(engine,point):
    x=engine;x.fail['after']=point
    with pytest.raises(OSError):x.e.activate(True)
    assert x.e.state_path.exists() and list(x.e.directory.glob('activation-error-*'))
    assert sum('create?' in p for m,p in x.calls if m=='POST')<=1
    x.fail['after']=None
    assert x.e.rollback(True)['phase']=='rolled_back'
    assert sum('create?' in p for m,p in x.calls if m=='POST')<=1


def test_failed_create_is_uncertain_and_never_retried(engine):
    x=engine;x.fail['before']='create?'
    with pytest.raises(OSError):x.e.activate(True)
    x.fail['before']=None
    with pytest.raises(ValueError,match='unresolved'):x.e.rollback(True)
    with pytest.raises(ValueError,match='fenced'):x.e.activate(True)
    assert sum('create?' in p for m,p in x.calls if m=='POST')==1


def test_partial_wrapper_switch_restored(engine,monkeypatch):
    x=engine;actual=x.e.switch_wrapper;count=0
    def switch(name,direction):
        nonlocal count
        count+=1
        if count==2:raise OSError('interrupted wrapper sequence')
        return actual(name,direction)
    monkeypatch.setattr(x.e,'switch_wrapper',switch)
    with pytest.raises(OSError):x.e.activate(True)
    monkeypatch.setattr(x.e,'switch_wrapper',actual)
    assert x.e.rollback(True)['phase']=='rolled_back'


def test_broken_new_code_does_not_block_rollback(engine):
    x=engine;x.e.activate(True);(x.f.release/'entrypoints/operator.py').write_bytes(b'broken')
    # Fresh process loads protected originals without depending on new code.
    other=x.m.Upgrade(x.f.journal,x.f.digest,stage=x.f.m);other.rpc=x.e.rpc
    assert other.rollback(True)['phase']=='rolled_back'

@pytest.mark.parametrize('drift',['marker','wrapper','config','unknown_live','both_running','candidate_config'])
def test_drift_refuses_rollback_mutation(engine,drift):
    x=engine;x.e.activate(True)
    if drift=='marker':x.e.marker.write_bytes(b'foreign drain')
    elif drift=='wrapper':(x.f.m.SBIN/'rras-workflow').write_bytes(b'foreign wrapper')
    elif drift=='config':x.f.m.CONFIG.write_bytes(b'foreign config')
    elif drift=='unknown_live':
        x.rows['c'*64]['Name']='/'+x.e.candidate_name
        x.rows['d'*64]={'Id':'d'*64,'Name':'/hermes'}
    elif drift=='both_running':x.rows[x.f.container['Id']]['State']['Running']=True
    else:x.rows['c'*64]['Config']['Env']=['foreign']
    before=sum(m=='POST' for m,_ in x.calls)
    with pytest.raises(ValueError):x.e.rollback(True)
    assert sum(m=='POST' for m,_ in x.calls)==before


def test_interrupted_owned_drain_can_be_completed_for_rollback(engine,monkeypatch):
    x=engine;actual=x.e.checkpoint
    def checkpoint(phase):
        actual(phase)
        if phase=='drain_owned':raise OSError('interrupted after durable receipt')
    monkeypatch.setattr(x.e,'checkpoint',checkpoint)
    with pytest.raises(OSError):x.e.activate(True)
    monkeypatch.setattr(x.e,'checkpoint',actual)
    assert x.e.rollback(True)['phase']=='rolled_back'
    assert x.states[x.f.container['Id']]=='running' and not x.e.marker.exists()


def test_drain_identity_change_prevents_stop(engine,monkeypatch):
    x=engine;actual=x.e.status;count=0
    def status(ref):
        nonlocal count
        count+=1;result=actual(ref)
        if count>=3:result['start_time']='new process'
        return result
    monkeypatch.setattr(x.e,'status',status)
    with pytest.raises(ValueError,match='identity'):x.e.activate(True)
    assert not any(m=='POST' for m,_ in x.calls)
    assert x.e.marker.exists()


def test_global_lock_excludes_second_mutator(engine):
    with engine.e.lock():
        with pytest.raises(BlockingIOError):
            with engine.e.lock():pass


def test_drain_becomes_busy_immediately_before_stop(engine,monkeypatch):
    x=engine;actual=x.e.status;count=0
    def status(ref):
        nonlocal count
        count+=1;result=actual(ref)
        if count>=4:result['active_agents']=1
        return result
    monkeypatch.setattr(x.e,'status',status)
    with pytest.raises(ValueError,match='changed before stop'):x.e.activate(True)
    assert not any(m=='POST' for m,_ in x.calls)


def test_unrecorded_drain_response_is_preserved(engine,monkeypatch):
    x=engine;actual=x.e.rpc
    def rpc(ref,script,*args):
        result=actual(ref,script,*args)
        if script==x.m.DRAIN:raise OSError('lost drain response before receipt')
        return result
    monkeypatch.setattr(x.e,'rpc',rpc)
    with pytest.raises(OSError):x.e.activate(True)
    assert x.e.marker.exists()
    with pytest.raises(ValueError,match='unowned'):x.e.rollback(True)
    assert not any(m=='POST' for m,_ in x.calls)


def test_wrapper_replace_response_loss_uses_durable_inode_receipt(engine,monkeypatch):
    x=engine;actual=x.e.checkpoint
    def checkpoint(phase):
        if phase=='wrapper_upgrade_complete':raise OSError('lost after atomic replacement')
        return actual(phase)
    monkeypatch.setattr(x.e,'checkpoint',checkpoint)
    with pytest.raises(OSError):x.e.activate(True)
    monkeypatch.setattr(x.e,'checkpoint',actual)
    assert x.e.rollback(True)['phase']=='rolled_back'


def test_candidate_network_alias_drift_refused(engine):
    x=engine;x.e.activate(True)
    x.rows['c'*64]['NetworkSettings']['Networks']['jarvis-net']['Aliases'].append('unreviewed-alias')
    before=sum(m=='POST' for m,_ in x.calls)
    with pytest.raises(ValueError,match='aliases'):x.e.rollback(True)
    assert sum(m=='POST' for m,_ in x.calls)==before


def test_stale_preflight_does_not_create_activation_state(engine,monkeypatch):
    x=engine;actual=x.e.status
    def stale(ref):return dict(actual(ref),fresh=False)
    monkeypatch.setattr(x.e,'status',stale)
    with pytest.raises(ValueError,match='unavailable'):x.e.activate(True)
    assert not x.e.directory.exists()
    assert not any(m=='POST' for m,_ in x.calls)
