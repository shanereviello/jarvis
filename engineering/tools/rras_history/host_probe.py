"""Synthetic unprivileged child roles for isolated cross-UID host acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import sys
import time

SERVICE = 61081
SHARED = 61080
CLIENT_A = 61082
CLIENT_B = 61083
UNKNOWN = 61084
READER = 61085
ROOT = Path(__file__).resolve().parents[3]
# Only root-custodied package dependencies; never the user's site-packages.
sys.path.insert(0, str(ROOT / 'vendor'))


def local(name):
    spec = importlib.util.spec_from_file_location('history_host_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def require_no_routes(text):
    # procfs may expose no header at all for an empty network namespace.
    lines=[line.split() for line in text.splitlines() if line.strip()]
    header='Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT'.split()
    if lines not in ([], [header]):
        raise ValueError('network route rows or unexpected route table')


def boundary():
    # setpriv arms PDEATHSIG after credential changes; verify/reset it here too.
    import ctypes
    import signal
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGTERM,0,0,0)!=0 or os.getppid()<=1:
        raise ValueError('live acceptance parent required')
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    assert os.getuid() == os.geteuid() != 0
    assert status['NoNewPrivs'].strip() == '1'
    for field in ('CapEff', 'CapPrm', 'CapInh', 'CapBnd', 'CapAmb'):
        assert int(status[field].strip(), 16) == 0
    assert [name for _, name in socket.if_nameindex()] == ['lo']
    require_no_routes(Path('/proc/net/route').read_text())
    assert not any(key.startswith(('OPENAI_', 'ANTHROPIC_', 'CODEX_', 'GH_', 'GITHUB_')) for key in os.environ)
    assert os.getgroups() == [SHARED]
    return dict(uid=os.getuid(), gid=os.getgid(), network='private_namespace_no_routes',
                no_new_privileges=True, capabilities=False, provider_environment=False)


def read_input():
    return local('contract').decode(sys.stdin.buffer.read(local('contract').MAX_REQUEST + 1))


def denied(path, flags):
    try: fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)
    except PermissionError: return True
    else:
        os.close(fd)
        raise ValueError('fixture access unexpectedly granted')


def run(role, state):
    identity = boundary()
    allowed = (SERVICE, CLIENT_A, CLIENT_B, UNKNOWN, READER, 996, 997, 1000)
    if os.getuid() not in allowed: raise ValueError('unknown fixture identity')
    transport = local('unix'); path = state / 'runtime/service.sock'
    if role == 'init':
        assert os.getuid() == SERVICE
        local('store').Store(state/'private', create=True)
        result = {'initialized': True}
    elif role == 'service':
        assert os.getuid() == SERVICE
        print(json.dumps({'boundary':identity}), flush=True)
        local('service_cli').main(['--socket',str(path),'--store',str(state/'private'),'--policy',str(state/'policy.json')])
        return None
    elif role == 'rpc':
        message = read_input()
        try: result = dict(accepted=True, value=transport.call(path, SERVICE, message))
        except (ValueError, OSError): result = dict(accepted=False)
    elif role in ('client', 'flush'):
        assert os.getuid() in (CLIENT_A, CLIENT_B)
        client_root = state / ('client-a' if os.getuid() == CLIENT_A else 'client-b')
        if role == 'client':
            client = local('interactive').Client(client_root, service_socket=path, service_uid=SERVICE, create=True)
            intent = read_input()
            assert set(intent) == {'kind','key','payload'}
            client.enqueue(intent['kind'],intent['key'],intent['payload'],session_id='synthetic-cross-uid-session')
        else: client = local('interactive').Client(client_root)
        result = client.flush()
    elif role == 'denial':
        assert os.getuid() != SERVICE
        for target in (state/'private/history.sqlite3',state/'root-private/sentinel',state/'policy.json'):
            denied(target,os.O_RDONLY)
        denied(Path(__file__),os.O_WRONLY)
        result = dict(private_store_denied=True, root_fixture_denied=True, policy_denied=True, source_write_denied=True)
    elif role == 'frame':
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(8); connection.connect(str(path))
            connection.sendall(struct.pack('!I',transport.REQUEST_LIMIT+1)); connection.shutdown(socket.SHUT_WR)
            reply = transport.receive(connection,transport.RESPONSE_LIMIT,time.monotonic()+8)
            assert reply == dict(contract=transport.CONTRACT,ok=False,error='refused')
        result = {'oversize_refused':True}
    elif role == 'deadline':
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(8); connection.connect(str(path)); connection.sendall(b'\0')
            assert connection.recv(1) == b''
        result = {'incomplete_frame_stopped':True}
    else: raise ValueError('unknown fixture role')
    return {'boundary':identity,'result':result}


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3: raise ValueError('fixed child arguments required')
        state = Path(sys.argv[2])
        if state.parent != Path('/var/lib') or not state.name.startswith('rras-history-acceptance-'):
            raise ValueError('isolated fixture path required')
        result = run(sys.argv[1],state)
        if result is not None: print(json.dumps(result))
    except Exception:
        sys.stderr.write('History acceptance child refused; preserve fixture evidence.\n')
        raise SystemExit(1)
