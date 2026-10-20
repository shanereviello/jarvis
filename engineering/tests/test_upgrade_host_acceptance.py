"""Run the harness with real Git payload/SQLite/files and fake root/Docker/native.

The separate sudo host run is still required for actual native/Docker evidence.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from test_workflow_production_package import committed_source

HERE=Path(__file__).resolve().parents[1]/'tools/rras_native'

def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.fixture
def harness(committed_source,tmp_path,monkeypatch):
    builder,repo,commit,_=committed_source;release=tmp_path/'protected-code';release.mkdir()
    builder.build(repo,commit,release/'payload')
    (release/'intake').mkdir();(release/'fixtures').mkdir()
    example=HERE.parents[1]/'contracts/examples/jarvis-interactive.json'
    (release/'fixtures/jarvis-interactive.json').write_bytes(example.read_bytes())
    (release/'acceptance-manifest.json').write_text(json.dumps({'source_commit':commit}))
    s,a,t,r=[module(n) for n in ('stage_workflow_upgrade','activate_workflow_upgrade','upgrade_acceptance_transport','run_upgrade_host_acceptance')]
    modules={'stage_workflow_upgrade':s,'activate_workflow_upgrade':a,'upgrade_acceptance_transport':t}
    monkeypatch.setattr(r,'local',lambda name:modules[name]);monkeypatch.setattr(r,'ROOT',tmp_path/'state')
    monkeypatch.setattr(r,'__file__',str(release/'engineering/tools/rras_native/run_upgrade_host_acceptance.py'))
    monkeypatch.setattr(s,'administrator',lambda:None);monkeypatch.setattr(s,'protected',lambda p:Path(p));monkeypatch.setattr(s,'role',lambda *a:None)
    monkeypatch.setattr(s,'source_ancestor',lambda v:None);monkeypatch.setattr(s,'idle',lambda:None)
    regular=s.regular
    monkeypatch.setattr(s,'regular',lambda path,limit=4*1024*1024,user=False:regular(path,limit,user=False))
    def os_proxy(**overrides):
        return SimpleNamespace(**{k:overrides.get(k,getattr(os,k)) for k in dir(os)})
    monkeypatch.setattr(r,'os',os_proxy(getuid=lambda:0,geteuid=lambda:0,chown=lambda *args:None))
    monkeypatch.setattr(a,'os',os_proxy(getuid=lambda:0,geteuid=lambda:0))
    rows={};states={};calls=[];fail={'discovery':False};net={}
    def raw(method,path,body=None):
        calls.append((method,path))
        if path.startswith('/containers/create?name='):
            cid=('b' if not rows else 'c')*64;name=path.split('name=')[1]
            config={k:copy.deepcopy(v) for k,v in body.items() if k not in ('HostConfig','NetworkingConfig')}
            rows[cid]={'Id':cid,'Name':'/'+name,'Config':config,'HostConfig':copy.deepcopy(body['HostConfig']),'Image':body['Image'],
                'NetworkSettings':{'Networks':copy.deepcopy(body['NetworkingConfig']['EndpointsConfig'])},
                'Mounts':[{'Destination':v['Target'],'Source':v['Source'],'RW':not v['ReadOnly'],'Type':v['Type']} for v in body['HostConfig']['Mounts']],
                'State':{'Running':False,'StartedAt':'fixture-start'},'RestartCount':0}
            states[cid]='running';return {'Id':cid}
        ref=path.split('/')[2];row=next((r for r in rows.values() if r['Id']==ref or r['Name']=='/'+ref),None)
        if method=='GET':return copy.deepcopy(row)
        assert row
        if '/start' in path:row['State']['Running']=True;states[ref]='running'
        elif '/stop' in path:row['State']['Running']=False
        elif '/rename?' in path:row['Name']='/'+path.split('name=')[1]
        else:raise AssertionError(path)
    monkeypatch.setattr(a,'api',raw)
    def subprocess_run(argv,**kwargs):
        if argv[:3]==['/usr/bin/docker','image','inspect']:return subprocess.CompletedProcess(argv,0,b'',b'')
        if argv[:3]==['/usr/bin/docker','network','create']:
            net.update(Name=argv[-1],Internal=True,Driver='bridge',Labels={t.LABEL:argv[-2].split('=',1)[1]})
            return subprocess.CompletedProcess(argv,0,b'fixture-network',b'')
        if argv[:3]==['/usr/bin/docker','network','inspect']:return subprocess.CompletedProcess(argv,0,s.encoded([net]),b'')
        raise AssertionError('unadmitted host subprocess '+repr(argv))
    monkeypatch.setattr(r,'subprocess',SimpleNamespace(run=subprocess_run,DEVNULL=subprocess.DEVNULL,PIPE=subprocess.PIPE,SubprocessError=subprocess.SubprocessError,CompletedProcess=subprocess.CompletedProcess))
    def command(argv,**kwargs):
        if argv[:2]==['/usr/bin/docker','exec']:
            index=5 if argv[2]=='-i' else 4;ref=argv[index];script=argv[index+5]
            row=next(r for r in rows.values() if r['Id']==ref or r['Name']=='/'+ref);ref=row['Id']
            if script==a.STATUS:answer={'fresh':True,'live':True,'state':states[ref],'active_agents':0,'pid':25,'start_time':'constant'}
            elif script==a.DRAIN:
                raw=s.encoded({'principal':argv[-1],'epoch':'fixture'});s.write(s.HERMES_CONFIG.parent/'.drain_request.json',raw)
                states[ref]='draining';answer={'sha256':s.sha(raw),'epoch':'fixture'}
            elif script==a.DISCOVERY:
                if fail['discovery']:raise ValueError('fixture discovery failure')
                answer={'verified':True}
            else:
                assert 'existing_history_entry_verified' in script
                return subprocess.CompletedProcess(argv,0,b'existing_history_entry_verified\n',b'')
            return subprocess.CompletedProcess(argv,0,s.encoded(answer),b'')
        raise AssertionError('unadmitted command '+repr(argv))
    monkeypatch.setattr(s,'command',command)
    return SimpleNamespace(r=r,s=s,a=a,t=t,rows=rows,calls=calls,fail=fail,root=r.ROOT)


def test_actual_harness_orchestration_with_explicit_fake_boundaries(harness):
    h=harness;answer=h.r.run()
    assert answer['phase']=='isolated_upgrade_lifecycle_verified'
    assert answer['fixture_containers_stopped'] is True and answer['api_calls']==0
    assert len(answer['cases'])==9
    assert len(h.rows)==2 and not any(r['State']['Running'] for r in h.rows.values())
    assert (h.root/'complete.json').exists() and (h.root/'docker-operations.json').exists()
    # All host operations went to isolated names or positively adopted IDs.
    assert all('/containers/hermes/' not in path for _,path in h.calls)
    assert sum(m=='POST' and '/create?' in path for m,path in h.calls)==2
    assert not any('delete' in path for _,path in h.calls)
    with pytest.raises(ValueError,match='exists'):h.r.run()


def test_interrupted_harness_stops_only_its_fixture_and_retains_evidence(harness,monkeypatch):
    h=harness;actual=h.a.Upgrade.activate
    def fail(engine,approved=False):raise ValueError('fixture interrupted before activation')
    monkeypatch.setattr(h.a.Upgrade,'activate',fail)
    with pytest.raises(ValueError,match='interrupted'):h.r.run()
    assert not any(r['State']['Running'] for r in h.rows.values())
    assert (h.root/'acceptance-error.txt').exists() and not (h.root/'complete.json').exists()


def test_cleanup_stop_failure_prevents_success_receipt(harness,monkeypatch):
    h=harness;actual=h.a.api;stops=0
    def raw(method,path,body=None):
        nonlocal stops
        if method=='POST' and '/stop?' in path:
            stops+=1
            if stops>=3:raise OSError('fixture cleanup stop failed')
        return actual(method,path,body)
    monkeypatch.setattr(h.a,'api',raw)
    with pytest.raises(ValueError,match='stop uncertain'):h.r.run()
    assert not (h.root/'complete.json').exists()
    assert list(h.root.glob('stop-error-*'))
