"""Synthetic probes for actual systemd/ACL acceptance; no production data."""
import errno
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import sys
import traceback

ROOT=Path(__file__).resolve().parents[3]
STATE=Path('/var/lib/rras-history-unit-acceptance-attempt03-20261023')
RUNTIME=Path('/run/rras-history-unit-acceptance-attempt03-20261023')
SERVICE=61091
sys.path.insert(0,str(ROOT/'vendor'))


def local(name):
    spec=importlib.util.spec_from_file_location('unit_probe_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def process_boundary():
    assert os.getuid()==os.geteuid()!=0
    fields=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    assert fields['NoNewPrivs'].strip()=='1'
    for name in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb'):assert int(fields[name].strip(),16)==0
    assert set(os.getgroups()) <= {os.getgid()}
    return dict(uid=os.getuid(),gid=os.getgid(),supplementary_groups=os.getgroups(),no_new_privileges=True,capabilities=False)


def denied(path,flags, *, missing_allowed=False):
    try:fd=os.open(path,flags|os.O_NOFOLLOW|os.O_NONBLOCK)
    except PermissionError:return
    except FileNotFoundError:
        if missing_allowed:return
        raise
    else:os.close(fd);raise ValueError('fixture access unexpectedly allowed')


def unit_boundary():
    identity=process_boundary();assert identity['uid']==SERVICE
    # Test the actual unit's read-only mount boundary with a DAC-writable file.
    try:fd=os.open(STATE/'outside-write-probe',os.O_WRONLY)
    except OSError as exc:assert exc.errno==errno.EROFS
    else:os.close(fd);raise ValueError('unit filesystem unexpectedly writable')
    try:connection=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    except OSError as exc:assert exc.errno in (errno.EAFNOSUPPORT,errno.EPERM,errno.EACCES)
    else:connection.close();raise ValueError('unit INET socket unexpectedly allowed')
    assert not Path('/proc/cpuinfo').exists()
    denied(Path('/proc/1/status'),os.O_RDONLY,missing_allowed=True)
    scratch=STATE/'private'/('unit-write-'+str(os.getpid()))
    fd=os.open(scratch,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(b'synthetic unit write probe\n');stream.flush();os.fsync(stream.fileno())
    return dict(identity=identity,readonly_mount_denied=True,inet_socket_denied=True,
                restricted_proc_verified=True,private_store_writable=True)


def child(role):
    identity=process_boundary()
    uid=os.getuid();assert uid in (61091,61092,61093,61094,61095,996,997,1000)
    transport=local('unix')
    if role=='rpc':
        raw=sys.stdin.buffer.read(local('contract').MAX_REQUEST+1)
        request=local('contract').decode(raw)
        try:result=dict(accepted=True,value=transport.call(RUNTIME/'service.sock',SERVICE,request))
        except (ValueError,OSError):result=dict(accepted=False)
    elif role in ('client','flush'):
        assert uid in (61092,1000)
        path=STATE/('client-'+str(uid))
        if role=='client':
            request=local('contract').decode(sys.stdin.buffer.read(local('contract').MAX_REQUEST+1))
            client=local('interactive').Client(path,service_socket=RUNTIME/'service.sock',service_uid=SERVICE,create=True)
            client.enqueue('start','synthetic-start',request,session_id='synthetic-unit-session')
        else:client=local('interactive').Client(path)
        result=client.flush()
    elif role=='denial':
        assert uid!=SERVICE
        for path in (STATE/'private/history.sqlite3',STATE/'policy.json',STATE/'root-private/sentinel'):
            denied(path,os.O_RDONLY)
        denied(Path(__file__),os.O_WRONLY)
        result=dict(private_data_denied=True,policy_denied=True,root_fixture_denied=True,source_write_denied=True)
    elif role=='unit-check':
        result=unit_boundary()
    else:raise ValueError('unknown probe role')
    return dict(contract='history-unit-probe.v1',identity=identity,result=result)


if __name__=='__main__':
    try:
        if len(sys.argv)!=2:raise ValueError('fixed probe role required')
        print(json.dumps(child(sys.argv[1])))
    except Exception as exc:
        frames=[dict(file=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(exc.__traceback__)]
        print(json.dumps(dict(contract='history-unit-probe-error.v1',exception_type=type(exc).__name__,
                              frames=frames,role=sys.argv[1] if len(sys.argv)==2 else 'invalid')),file=sys.stderr)
        raise SystemExit(1)
