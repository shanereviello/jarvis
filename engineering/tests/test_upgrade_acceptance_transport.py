"""Actual namespace adapter with fake Docker responses; no Docker/root access."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_native'

@pytest.fixture
def fixture(tmp_path):
    spec=importlib.util.spec_from_file_location('acceptance_transport',ROOT/'upgrade_acceptance_transport.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    token='a'*32;prefix='rras-upgrade-test-'+token[:12]+'-';network=prefix+'net';calls=[];rows={}
    names={'hermes','hermes-candidate-workflow-123456789abc','hermes-rollback-workflow-123456789abc','hermes-failed-workflow-123456789abc'}
    def api(method,path,body=None):
        calls.append((method,path,copy.deepcopy(body)))
        if path.startswith('/containers/create?name='):
            cid=('b' if not rows else 'c')*64;name=path.split('name=')[1]
            config={k:copy.deepcopy(v) for k,v in body.items() if k not in ('HostConfig','NetworkingConfig')}
            row={'Id':cid,'Name':'/'+name,'Config':config,'HostConfig':copy.deepcopy(body['HostConfig']),
                'Image':body['Image'],'NetworkSettings':{'Networks':copy.deepcopy(body['NetworkingConfig']['EndpointsConfig'])},'State':{'Running':False}}
            rows[cid]=row;return {'Id':cid}
        ref=path.split('/')[2];row=next((r for r in rows.values() if r['Id']==ref or r['Name']=='/'+ref),None)
        if method=='GET':return copy.deepcopy(row)
        assert row
        if '/start' in path:row['State']['Running']=True
        elif '/stop' in path:row['State']['Running']=False
        elif '/rename?' in path:row['Name']='/'+path.split('name=')[1]
        else:raise AssertionError(path)
    t=m.Transport(api,tmp_path,token,'sha256:'+'d'*64,names,network)
    dirs={}
    for target in ('/opt/data','/workspace/git/jarvis','/workspace/git/robot_ws','/workspace/jarvis-artifacts','/workspace/shared','/opt/rras-workflow','/opt/rras-workflow-history'):
        path=tmp_path/str(len(dirs));path.mkdir();dirs[target]=path
    body={'Image':t.image,'User':'1000:1000','Entrypoint':['/opt/hermes/.venv/bin/python'],'Cmd':['-I','-B','/opt/hermes/gateway/run.py'],
        'Labels':{m.LABEL:token},'Env':[k+'='+v for k,v in m.ENV.items()],
        'HostConfig':{'NetworkMode':network,'Privileged':False,'ReadonlyRootfs':True,'AutoRemove':False,'IpcMode':'private',
            'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'Tmpfs':{'/tmp':'fixture'},
            'Mounts':[{'Type':'bind','Source':str(v),'Target':k,'ReadOnly':k not in ('/opt/data','/workspace/jarvis-artifacts','/workspace/shared')} for k,v in dirs.items()]},
        'NetworkingConfig':{'EndpointsConfig':{'jarvis-net':{'Aliases':['hermes','jarvis']}}}}
    return SimpleNamespace(m=m,t=t,body=body,calls=calls,rows=rows,root=tmp_path,dirs=dirs)


def test_real_adapter_maps_only_names_network_aliases_and_preserves_rest(fixture):
    f=fixture;reply=f.t.call('POST','/containers/create?name=hermes',f.body);cid=reply['Id']
    raw=f.rows[cid];assert raw['Name']=='/'+f.t.physical('hermes')
    row=f.t.call('GET','/containers/hermes/json')
    assert row['Name']=='/hermes' and set(row['NetworkSettings']['Networks'])=={'jarvis-net'}
    assert row['HostConfig']==raw['HostConfig'] and row['Config']==raw['Config'] and row['Id']==raw['Id']
    assert row['NetworkSettings']['Networks']['jarvis-net']['Aliases']==['hermes','jarvis']
    f.t.call('POST','/containers/'+cid+'/start');assert raw['State']['Running']
    f.t.call('POST','/containers/'+cid+'/rename?name=hermes-rollback-workflow-123456789abc')
    assert f.t.exec_ref(cid)==cid
    f.t.call('POST','/containers/'+cid+'/stop?t=60');assert not raw['State']['Running']
    assert not any(path=='/containers/hermes/json' for _,path,_ in f.calls)

@pytest.mark.parametrize('path',['/containers/'+'e'*64+'/start','/containers/unadmitted/json','/containers/hermes/delete',
    '/containers/hermes/stop?t=0','/containers/hermes/rename?name=production','/images/create','/networks/create'])
def test_unadmitted_resource_or_operation_never_reaches_docker(fixture,path):
    f=fixture
    with pytest.raises(ValueError):f.t.call('POST',path)
    assert not f.calls

@pytest.mark.parametrize('field',['label','image','root','entrypoint','cmd','env','duplicate_env','network','privileged','readonly','capadd','capdrop','security',
    'autorm','binds','volumesfrom','ports','pid','ipc','devices','tmpfs','groups','userns','mount_source','mount_symlink','mount_rw','mount_duplicate'])
def test_unsafe_create_never_reaches_docker(fixture,field):
    f=fixture;b=copy.deepcopy(f.body);h=b['HostConfig']
    if field=='label':b['Labels']={}
    elif field=='image':b['Image']='another-image'
    elif field=='root':b['User']='0:0'
    elif field=='entrypoint':b['Entrypoint']=['/bin/sh']
    elif field=='cmd':b['Cmd']=['-c','bad']
    elif field=='env':b['Env'].append('OPENAI_API_KEY=fixture-only-never-used')
    elif field=='duplicate_env':b['Env'].append(b['Env'][0])
    elif field=='network':h['NetworkMode']='host'
    elif field=='privileged':h['Privileged']=True
    elif field=='readonly':h['ReadonlyRootfs']=False
    elif field=='capadd':h['CapAdd']=['SYS_ADMIN']
    elif field=='capdrop':h['CapDrop']=[]
    elif field=='security':h['SecurityOpt']=[]
    elif field=='autorm':h['AutoRemove']=True
    elif field=='binds':h['Binds']=['/var/run/docker.sock:/var/run/docker.sock']
    elif field=='volumesfrom':h['VolumesFrom']=['hermes']
    elif field=='ports':h['PortBindings']={'80/tcp':[{'HostPort':'80'}]}
    elif field=='pid':h['PidMode']='host'
    elif field=='ipc':h['IpcMode']='host'
    elif field=='devices':h['Devices']=[{'PathOnHost':'/dev/sda'}]
    elif field=='tmpfs':h['Tmpfs']['/var/run']='rw'
    elif field=='groups':h['GroupAdd']=['docker']
    elif field=='userns':h['UsernsMode']='host'
    elif field=='mount_source':h['Mounts'][0]['Source']='/srv/hermes/data'
    elif field=='mount_symlink':
        p=f.root/'link';p.symlink_to(f.root/'0');h['Mounts'][0]['Source']=str(p)
    elif field=='mount_rw':h['Mounts'][-1]['ReadOnly']=False
    else:h['Mounts'][-1]=copy.deepcopy(h['Mounts'][0])
    with pytest.raises(ValueError):f.t.call('POST','/containers/create?name=hermes',b)
    assert not f.calls

@pytest.mark.parametrize('field',['label','name','network','environment','mount'])
def test_ownership_is_rechecked_before_every_mutation_and_exec(fixture,field):
    f=fixture;cid=f.t.call('POST','/containers/create?name=hermes',f.body)['Id'];row=f.rows[cid]
    if field=='label':row['Config']['Labels']={}
    elif field=='name':row['Name']='/hermes' # real production name is outside namespace
    elif field=='network':row['NetworkSettings']['Networks']={'jarvis-net':{}}
    elif field=='environment':row['Config']['Env'].append('PROVIDER_TOKEN=fixture')
    else:row['HostConfig']['Mounts'][0]['Source']='/srv/hermes/data'
    before=len([1 for m,_,_ in f.calls if m=='POST'])
    with pytest.raises(ValueError):f.t.call('POST','/containers/'+cid+'/start')
    with pytest.raises(ValueError):f.t.exec_ref(cid)
    assert len([1 for m,_,_ in f.calls if m=='POST'])==before


def test_lost_create_response_can_only_be_adopted_via_owned_name(fixture):
    f=fixture;actual=f.t.raw
    def lost(method,path,body=None):
        answer=actual(method,path,body)
        if method=='POST':raise OSError('lost response')
        return answer
    f.t.raw=lost
    with pytest.raises(OSError):f.t.call('POST','/containers/create?name=hermes',f.body)
    assert not f.t.ids
    row=f.t.call('GET','/containers/hermes/json');assert row['Id'] in f.t.ids
    assert sum(m=='POST' for m,_,_ in f.calls)==1


def test_docker_omits_false_readonly_defaults_in_inspected_host_mounts(fixture):
    f=fixture;cid=f.t.call('POST','/containers/create?name=hermes',f.body)['Id']
    for mount in f.rows[cid]['HostConfig']['Mounts']:
        if mount['ReadOnly'] is False:del mount['ReadOnly']
    # The daemon representation is equivalent to the explicit false request;
    # only known writable targets allow this default, never protected code.
    assert f.t.call('GET','/containers/hermes/json')['Id']==cid
    f.t.call('POST','/containers/'+cid+'/start')
    protected=f.rows[cid]['HostConfig']['Mounts'][-1];assert protected['ReadOnly'] is True
    del protected['ReadOnly']
    with pytest.raises(ValueError,match='unsafe source mount'):f.t.call('POST','/containers/'+cid+'/stop?t=60')
