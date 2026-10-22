"""Real Linux sockets/same-UID fixtures; cross-UID installation remains separate."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import pytest
from test_engineering_history_local import module, request, note, document

u = module('unix'); s = module('store'); interactive = module('interactive'); c = module('contract')
TOOLS = Path(__file__).resolve().parents[1] / 'tools/rras_history'


def policy():
    return dict(contract='engineering-history-access.v1', principals=[
        dict(uid=os.getuid(), private_read=['example'], write=['example'])])


@pytest.fixture
def env():
    # Keep sun_path below Linux's 108-byte limit even for long checkout paths.
    with tempfile.TemporaryDirectory(prefix='rras-history-', dir='/tmp') as raw:
        root = Path(raw); root.chmod(0o700)
        store_root = root / 'private'; store_root.mkdir(mode=0o700)
        state = root / 'client'; state.mkdir(mode=0o700)
        yield root, s.Store(store_root, create=True), state


@contextmanager
def running(env, grants=None):
    root, store, _ = env; errors = []; stop = threading.Event()
    with u.Server(root / 'service.sock', store, policy() if grants is None else grants) as server:
        def serve():
            try:
                while not stop.is_set(): server.serve_once()
            except BaseException as exc: errors.append(exc)
        worker = threading.Thread(target=serve); worker.start()
        try: yield server
        finally:
            stop.set(); worker.join(7)
            assert not worker.is_alive(), 'fixture server did not stop'
            assert not errors, errors


def rpc(server, message): return u.call(server.path, os.getuid(), message)

def submit(server, value=None): return rpc(server, {'method':'submit', 'request':value or request()})


def test_real_peer_credentials_and_immutable_document(env):
    with running(env) as server:
        head = submit(server)['receipt']['work_revision_sha256']
        r = document(head); result = submit(server, r)
        receipt = result['receipt']
        assert receipt['peer_uid'] == os.getuid() == receipt['writer_uid']
        assert receipt['transport'] == 'authenticated_local_service'
        fetched = rpc(server, dict(method='document', document_id=r['body']['document_id'], version=None))
        assert c.digest(fetched['markdown'].encode()) == receipt['document_manifest']['markdown_sha256']
        assert fetched['manifest'] == receipt['document_manifest']
        history = rpc(server, dict(method='history', repository_id='example', offset=0, limit=1))
        assert len(history['records']) == 1 and history['has_more']
        assert stat.S_IMODE(server.path.stat().st_mode) == 0o660
    assert not (env[0]/'service.sock').exists()


def test_service_restart_replays_exact_receipt(env):
    with running(env) as server: original = submit(server)['receipt']
    with running(env) as server:
        assert submit(server) == {'inserted':False, 'receipt':original}
        assert len(env[1].history()['records']) == 1


def test_client_outage_reopen_then_real_socket_flush(env):
    root, store, state = env
    client = interactive.Client(state, service_socket=root/'service.sock', service_uid=os.getuid(), create=True)
    client.enqueue('start', 'start', request(), session_id='explicit-session')
    client.enqueue('handoff', 'handoff', dict(summary='Pending offline', decisions=[], next_action=None, references=[]))
    assert client.flush()['status']['recording_state'] == 'pending'
    assert client.status()['pending'][0]['error'] == 'store_unavailable'
    with running(env):
        reopened = interactive.Client(state)
        result = reopened.flush()
        assert result['delivered_now'] == 3 and result['status']['context_recorded']
        assert result['status']['transport'] == 'authenticated_local_service'
        assert reopened.flush()['delivered_now'] == 0
    assert len(store.history()['records']) == 3


def test_lost_response_after_backend_commit_retries_without_duplicate(env):
    root, store, state = env
    client = interactive.Client(state, service_socket=root/'service.sock', service_uid=os.getuid(), create=True)
    client.enqueue('start', 'start', request())
    original = u.send; lose = [True]
    def send(connection, value, maximum, deadline):
        if value.get('ok') is True and lose[0]:
            lose[0] = False
            raise OSError('synthetic lost response after commit')
        return original(connection, value, maximum, deadline)
    with running(env):
        with patch.object(u, 'send', side_effect=send):
            result = client.flush()
        assert result['delivered_now'] == 0 and not result['status']['context_recorded']
        first = store.history()['records'][0]['receipt']
        assert interactive.Client(state).flush()['delivered_now'] == 2
    rows = store.history()['records']
    assert len(rows) == 2 and rows[0]['receipt'] == first


@pytest.mark.parametrize('field,value', [('writer_uid',2009),('peer_uid',2009),('contract','engineering-history-receipt.v1'),
                                       ('transport','local_caller_store'),('authority_granted',True)])
def test_client_rejects_wrong_service_receipt_preserving_queue(env, field, value):
    root, store, state = env
    client = interactive.Client(state, service_socket=root/'service.sock', service_uid=os.getuid(), create=True)
    client.enqueue('start','start',request())
    with running(env) as server:
        original = server.access.dispatch
        def changed(*args):
            result = original(*args); result['receipt'][field] = value; return result
        with patch.object(server.access, 'dispatch', side_effect=changed):
            with pytest.raises(ValueError, match='receipt differs'): client.flush()
        assert len(client.status()['pending']) == 2
        assert client.flush()['delivered_now'] == 2
    assert len(store.history()['records']) == 2


@pytest.mark.parametrize('message', [
    {'method':'execute'}, {'method':'outbox'}, {'method':'submit','request':{},'peer_uid':1000},
    {'method':'history','repository_id':'forbidden','offset':0,'limit':100},
    {'method':'document','document_id':'doc_'+'f'*32,'version':None},
])
def test_refusals_contain_no_private_diagnostics(env, message):
    with running(env) as server:
        with pytest.raises(ValueError, match='^history service refused request$'): rpc(server,message)
    assert env[1].history()['records'] == []


def test_real_ungranted_peer_denied(env):
    with running(env, {'contract':'engineering-history-access.v1','principals':[]}) as server:
        with pytest.raises((ValueError, OSError)): submit(server)
    assert env[1].history()['records'] == []


@pytest.mark.parametrize('raw', [b'{"method":"execute","method":"history"}', b'\xff', b'null', b'{' + b' '*300])
def test_invalid_json_frames_refused_without_mutation(env, raw):
    with running(env) as server:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.connect(str(server.path)); connection.sendall(struct.pack('!I',len(raw))+raw); connection.shutdown(socket.SHUT_WR)
            response = u.receive(connection,u.RESPONSE_LIMIT,time.monotonic()+2)
            assert response == dict(contract=u.CONTRACT,ok=False,error='refused')
    assert env[1].history()['records'] == []


@pytest.mark.parametrize('packet', [struct.pack('!I',0), struct.pack('!I',u.REQUEST_LIMIT+1),
                                    struct.pack('!I',100)+b'{}', struct.pack('!I',2)+b'{}trailing'])
def test_frame_bounds_truncation_and_pipelining(env, packet):
    with running(env) as server:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.connect(str(server.path)); connection.sendall(packet); connection.shutdown(socket.SHUT_WR)
            try: response = u.receive(connection,u.RESPONSE_LIMIT,time.monotonic()+2)
            except ConnectionResetError: pass  # Unread pipelined bytes may reset the stream.
            else: assert not response['ok']
    assert env[1].history()['records'] == []


def test_stalled_connection_has_total_deadline_then_server_recovers(env):
    with patch.object(u,'DEADLINE_SECONDS',0.15), running(env) as server:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.connect(str(server.path)); connection.sendall(b'\0')
            connection.settimeout(2)
            assert connection.recv(1) == b''
        assert submit(server)['inserted']


@pytest.mark.parametrize('kind', ['file','symlink','socket'])
def test_existing_endpoint_never_removed_or_adopted(env, kind):
    path = env[0]/'service.sock'; handle = None
    if kind == 'file': path.write_text('preserve')
    elif kind == 'symlink': path.symlink_to(env[0]/'absent')
    else:
        handle = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); handle.bind(str(path))
    before = path.lstat()
    try:
        with pytest.raises((OSError,ValueError)):
            with u.Server(path,env[1],policy()): pass
        after = path.lstat()
        assert (before.st_dev,before.st_ino,before.st_mode) == (after.st_dev,after.st_ino,after.st_mode)
    finally:
        if handle is not None: handle.close()


def test_cleanup_preserves_replaced_path(env):
    path = env[0]/'service.sock'
    with u.Server(path,env[1],policy()):
        path.unlink(); path.write_text('replacement evidence')
    assert path.read_text() == 'replacement evidence'


@pytest.mark.parametrize('mode', [0o777,0o770])
def test_writable_runtime_refused(env, mode):
    env[0].chmod(mode)
    try:
        with pytest.raises(ValueError):
            with u.Server(env[0]/'service.sock',env[1],policy()): pass
    finally: env[0].chmod(0o700)


def test_client_checks_socket_mode_and_expected_identity_before_private_send(env):
    with running(env) as server:
        server.path.chmod(0o666)
        with pytest.raises(ValueError,match='trusted history socket'): submit(server)
        server.path.chmod(0o660)
        with pytest.raises(ValueError): u.call(server.path,os.getuid()+100,{'method':'submit','request':request()})
        assert env[1].history()['records'] == []


@pytest.mark.parametrize('change', ['symlink','hardlink','mode','directory','oversize'])
def test_policy_file_safety(env, change):
    path = env[0]/'policy.json'; path.write_bytes(c.encoded(policy())); path.chmod(0o600)
    assert u.load_policy(path) == policy()
    if change == 'symlink':
        other = env[0]/'linked'; other.symlink_to(path); path = other
    if change == 'hardlink': os.link(path,env[0]/'linked')
    if change == 'mode': path.chmod(0o666)
    if change == 'directory': path.unlink(); path.mkdir()
    if change == 'oversize': path.write_bytes(b' '* (c.MAX_REQUEST+1))
    with pytest.raises((ValueError,OSError)): u.load_policy(path)


def test_response_bound_retains_store_and_does_not_emit_partial_history(env):
    with running(env) as server:
        submit(server)
        with patch.object(u,'RESPONSE_LIMIT',128):
            with pytest.raises(ValueError,match='refused'):
                rpc(server,dict(method='history',repository_id='example',offset=0,limit=100))
    assert len(env[1].history()['records']) == 1


def test_cli_service_and_client_real_subprocesses(env):
    root, store, state = env; path = root/'service.sock'
    config = root/'policy.json'; config.write_bytes(c.encoded(policy())); config.chmod(0o600)
    process = subprocess.Popen([sys.executable,str(TOOLS/'service_cli.py'),'--socket',str(path),
                                '--store',str(store.root),'--policy',str(config)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic()+5
        while not path.exists() and process.poll() is None and time.monotonic()<deadline: time.sleep(0.02)
        assert path.exists()
        cli = [sys.executable,str(TOOLS/'interactive_cli.py')]
        init = subprocess.run(cli+['init','--state',str(state),'--service-socket',str(path),'--service-uid',str(os.getuid())],capture_output=True,check=True)
        assert json.loads(init.stdout)['transport'] == 'authenticated_local_service'
        r = root/'request.json'; r.write_bytes(c.encoded(request()))
        run = subprocess.run(cli+['start','--state',str(state),'--key','start','--request',str(r)],capture_output=True,check=True)
        assert json.loads(run.stdout)['status']['context_recorded']
    finally:
        process.terminate(); out, err = process.communicate(timeout=7)
    assert process.returncode == 0 and not out and not err and not path.exists()


@pytest.mark.parametrize('kwargs', [dict(service_uid=0), dict(service_uid=996), dict(service_uid=997),
                                     dict(service_uid=True), dict(service_uid=None)])
def test_invalid_service_identity_cannot_initialize_client(env, kwargs):
    with pytest.raises(ValueError): interactive.Client(env[2],service_socket=env[0]/'service.sock',create=True,**kwargs)
    assert not (env[2]/'client.sqlite3').exists()


def test_client_peer_mismatch_precedes_private_send(env):
    # Fault-inject only the peer result; real different-UID proof is a host gate.
    path = env[0]/'service.sock'; captured = []; errors = []
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
        listener.bind(str(path)); path.chmod(0o660); listener.listen(1); listener.settimeout(2)
        def receive():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(2); captured.append(connection.recv(4096))
            except BaseException as exc: errors.append(exc)
        thread = threading.Thread(target=receive); thread.start()
        try:
            with patch.object(u,'peer',return_value=os.getuid()+100):
                with pytest.raises(ValueError,match='identity differs'):
                    u.call(path,os.getuid(),{'method':'submit','request':request()})
        finally: thread.join(3)
    assert not thread.is_alive() and not errors and captured == [b'']


def test_service_config_is_fixed_and_cannot_fall_back_to_local_store(env):
    root, store, state = env
    client = interactive.Client(state,service_socket=root/'service.sock',service_uid=os.getuid(),create=True)
    with pytest.raises(ValueError): interactive.Client(state,store=store.root)
    client.enqueue('start','start',request())
    assert client.flush()['status']['recording_state'] == 'pending'
    assert store.history()['records'] == []
