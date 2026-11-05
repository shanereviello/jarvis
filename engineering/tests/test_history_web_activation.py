"""Additive read-only policy plan and exact activation binding; no root actions."""
import copy
import hashlib
from pathlib import Path
import subprocess
import pytest
from test_history_web import web,TOOLS


def activation():
    prefix=(TOOLS/'production_package.py').read_text().split('\ndef build(',1)[0]
    suffix=(TOOLS/'activation.py').read_text();namespace={'__name__':'fixture_activation'}
    exec(compile(prefix+'\n'+suffix,'fixture_activation','exec'),namespace);return namespace


def policy():return {'contract':'engineering-history-access.v1','principals':[
    {'uid':1000,'private_read':['jarvis','robot_ws'],'write':['jarvis','robot_ws']},
    {'uid':1001,'private_read':['other_repository'],'write':[]}]}


def test_adds_only_new_jarvis_reader_preserving_all_old_principals():
    module=activation();original=policy();saved=copy.deepcopy(original);candidate=module['proposed_policy'](original)
    assert original==saved and candidate['principals'][:-1]==saved['principals']
    assert candidate['principals'][-1]=={'uid':993,'private_read':['jarvis'],'write':[]}
    candidate['principals'][0]['private_read'].append('new')
    assert original==saved


@pytest.mark.parametrize('entry',[
    {'uid':993,'private_read':['jarvis'],'write':[]},
    {'uid':996,'private_read':['jarvis'],'write':[]},
    {'uid':997,'private_read':['jarvis'],'write':[]},
    {'uid':True,'private_read':['jarvis'],'write':[]},
    {'uid':0,'private_read':['jarvis'],'write':[]},
    {'uid':1000,'private_read':['jarvis'],'write':[]},
    {'uid':1002,'private_read':['jarvis'],'write':['other']},
    {'uid':1002,'private_read':['jarvis','jarvis'],'write':[]},
    {'uid':1002,'private_read':['../bad'],'write':[]},
])
def test_existing_role_or_invalid_policy_refused_without_mutating_input(entry):
    module=activation();value=policy();value['principals'].append(entry);saved=copy.deepcopy(value)
    with pytest.raises(ValueError):module['proposed_policy'](value)
    assert value==saved


def test_no_slot_for_reader_refused():
    value=policy();value['principals']=[{'uid':2000+i,'private_read':[],'write':[]} for i in range(128)]
    with pytest.raises(ValueError):activation()['proposed_policy'](value)


def test_exact_binding_and_stale_baselines_refused():
    module=activation();review={'policy_before_sha256':'a'*64,'policy_after_sha256':'b'*64,'history_pid':'123'}
    module['bind_review'](review,'a'*64,'b'*64,'123')
    for args in ((None,None,None),('c'*64,'b'*64,'123'),('a'*64,'c'*64,'123'),('a'*64,'b'*64,'124')):
        with pytest.raises(ValueError):module['bind_review'](review,*args)


def test_actual_entrypoints_refuse_unprivileged_invocation():
    module=activation()
    with pytest.raises(ValueError,match='administrator'):module['preflight']('/not-read','a'*64,'b'*64)
    with pytest.raises(ValueError,match='administrator'):module['activate']('/not-read','a'*64,'b'*64,'c'*64,'d'*64,'1')


def test_stale_review_stops_before_any_mutation(monkeypatch,tmp_path):
    module=activation();review={'policy_before_sha256':'a'*64,'policy_after_sha256':'b'*64,'history_pid':'123'}
    monkeypatch.setitem(module,'preflight',lambda *args:(review,b'',b'',tmp_path/'not-created',tmp_path/'not-written',{}))
    def mutation(*args):raise AssertionError('unexpected mutation')
    monkeypatch.setattr(module['os'],'umask',mutation)
    with pytest.raises(ValueError,match='baseline changed'):module['activate']('/release','a'*64,'b'*64,'a'*64,'b'*64,'999')
    assert not list(tmp_path.iterdir())


def test_emitter_uses_only_exact_committed_activation(tmp_path):
    source=tmp_path/'repo';folder=source/'engineering/tools/rras_history_web';folder.mkdir(parents=True)
    for name in ('production_package.py','activation.py'):(folder/name).write_bytes((TOOLS/name).read_bytes())
    env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],env=env,stderr=subprocess.PIPE).decode().strip()
    git('init');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-m','Fixture')
    original=(folder/'activation.py').read_bytes();(folder/'activation.py').write_bytes(b'raise RuntimeError("uncommitted")')
    path=tmp_path/'helper.py';result=web('activation_package').emit(source,git('rev-parse','HEAD'),path)
    assert original in path.read_bytes() and hashlib.sha256(path.read_bytes()).hexdigest()==result['helper_sha256']
    compile(path.read_bytes(),str(path),'exec')
