"""Curated routes deny private/writer/control methods; real same-UID socket tests."""
from contextlib import contextmanager
import copy
import os
from pathlib import Path
import tempfile
import threading
import pytest
from test_engineering_history_local import module
from test_history_curated_preview import preview_inputs
from test_history_managed_link import setup,exporter,j,fixtures

c=module('contract');catalog=module('curated_publication');reader=module('curated_read_access');unix=module('curated_read_unix')


@pytest.fixture
def env(preview_inputs):
    with tempfile.TemporaryDirectory(prefix='rras-curated-',dir='/tmp') as name:
        root=Path(name);root.chmod(0o700);preview=module('curated_preview').build(*preview_inputs);repo=preview['entries'][0]['repository_id']
        store=root/'catalog';catalog.initialize(store,[repo]);receipt=catalog.publish(store,preview,c.digest(c.encoded(preview)),None,'publish',approve_publication=True)
        policy={'contract':'engineering-curated-read-access.v1','principals':[{'uid':os.getuid(),'repositories':[repo]}]}
        yield root,store,preview,repo,receipt,policy


def search(repo,generation=None):return {'method':'search','repository_id':repo,'query':'','generation_sha256':generation,'offset':0,'limit':20}


@contextmanager
def running(env,policy=None):
    root,store,_,_,_,default=env;stop=threading.Event();errors=[]
    with unix.Server(root/'reader.sock',store,default if policy is None else policy) as server:
        def serve():
            try:
                while not stop.is_set():server.serve_once()
            except BaseException as error:errors.append(error)
        worker=threading.Thread(target=serve);worker.start()
        try:yield server
        finally:
            stop.set();worker.join(7);assert not worker.is_alive() and not errors


def test_real_peer_search_read_and_endpoint_cleanup(env):
    root,_,preview,repo,receipt,_=env
    with running(env) as server:
        result=unix.call(server.path,os.getuid(),search(repo))
        assert result['entries']==preview['entries'] and result['authority_granted'] is False
        answer=unix.call(server.path,os.getuid(),{'method':'read','repository_id':repo,'entry_id':preview['entries'][0]['entry_id'],'generation_sha256':receipt['generation_sha256']})
        assert answer['entry']==preview['entries'][0] and answer['human_authenticated'] is False
    assert not (root/'reader.sock').exists()


@pytest.mark.parametrize('method',['history','document','submit','publish','withdraw','approve','launch','merge','deploy'])
def test_private_writer_and_action_routes_refused_over_socket(env,method):
    _,_,_,repo,_,_=env
    with running(env) as server:
        with pytest.raises(ValueError,match='service refused'):unix.call(server.path,os.getuid(),{'method':method,'repository_id':repo})
        assert unix.call(server.path,os.getuid(),search(repo))['entries']


def test_unknown_worker_root_and_cross_repository_refused_before_catalog(env,monkeypatch):
    _,store,_,repo,_,policy=env;access=reader.Access(store,policy)
    real=reader.local
    monkeypatch.setattr(reader,'local',lambda name:pytest.fail('must refuse before data access') if name=='curated_publication' else real(name))
    for uid in (0,996,997,os.getuid()+10000):
        with pytest.raises(ValueError):access.dispatch(uid,search(repo))
    with pytest.raises(ValueError):access.dispatch(os.getuid(),search('other_repo'))


@pytest.mark.parametrize('change',['root','worker','write','duplicate','unknown_repo'])
def test_invalid_read_policy_refused(env,change):
    _,store,_,_,_,policy=env;policy=copy.deepcopy(policy)
    if change=='root':policy['principals'][0]['uid']=0
    elif change=='worker':policy['principals'][0]['uid']=996
    elif change=='write':policy['principals'][0]['write']=True
    elif change=='duplicate':policy['principals']*=2
    else:policy['principals'][0]['repositories']=['other_repo']
    with pytest.raises(ValueError):reader.Access(store,policy)


def test_withdrawal_and_restart_do_not_reveal_old_entry(env):
    _,store,preview,repo,receipt,_=env;entry=preview['entries'][0]['entry_id'];old=receipt['generation_sha256']
    with running(env) as server:
        assert unix.call(server.path,os.getuid(),search(repo))['entries']
        catalog.withdraw(store,[entry],old,'withdraw',approve_withdrawal=True)
        assert unix.call(server.path,os.getuid(),search(repo))['entries']==[]
        with pytest.raises(ValueError):unix.call(server.path,os.getuid(),{'method':'read','repository_id':repo,'entry_id':entry,'generation_sha256':old})
    with running(env) as server:assert unix.call(server.path,os.getuid(),search(repo))['entries']==[]


def test_json_principal_cannot_override_peer_or_repository(env):
    _,store,_,repo,_,policy=env;access=reader.Access(store,policy);message=search(repo);message['peer_uid']=os.getuid()
    with pytest.raises(ValueError):access.dispatch(os.getuid(),message)


def test_wrong_connected_service_identity_refused(env):
    _,_,_,repo,_,_=env
    with running(env) as server:
        with pytest.raises(ValueError):unix.call(server.path,os.getuid()+10000,search(repo))
