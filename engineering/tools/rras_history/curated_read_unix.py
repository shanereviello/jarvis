"""Optional isolated curated-reader Unix endpoint; no production entry or ACL change.

Reuse the bounded existing kernel-peer transport with only the curated dispatcher.
"""
import importlib.util
import os
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('curated_unix_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


transport=local('unix')


class Server(transport.Server):
    def __init__(self,path,catalog_root,policy,*,on_bound=None):
        transport.uid(os.getuid())
        if os.geteuid()!=os.getuid():raise ValueError('unprivileged curated reader required')
        self.path=transport.endpoint(path)
        self.access=local('curated_read_access').Access(catalog_root,policy)
        self.listener=None;self.identity=None;self.on_bound=on_bound


def server_peer(connection,service_uid):
    """Authenticate the host UID even when its PID is invisible in the client namespace."""
    import socket
    import struct
    transport.uid(service_uid)
    if not hasattr(socket,'SO_PEERCRED'):raise ValueError('Linux peer credentials required')
    pid,uid,gid=struct.unpack('iII',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    if pid<0 or uid!=service_uid:raise ValueError('curated service identity differs')
    # PID zero is Linux's unmapped PID representation across PID namespaces.
    # No liveness/process identity claim is made; exact kernel UID is required.
    return uid


def call(path,service_uid,message):
    """Curated-only host client; private-history transport keeps its strict PID rule."""
    import socket
    import stat
    import time
    transport.uid(service_uid);p=transport.endpoint(path);transport.parents(p,service_uid)
    info=p.lstat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid!=service_uid or
            stat.S_IMODE(info.st_mode) not in (0o600,0o660)):raise ValueError('trusted curated socket required')
    deadline=time.monotonic()+transport.DEADLINE_SECONDS
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        transport.remaining(connection,deadline);connection.connect(str(p))
        server_peer(connection,service_uid)
        transport.send(connection,message,transport.REQUEST_LIMIT,deadline)
        response=transport.receive(connection,transport.RESPONSE_LIMIT,deadline)
    if type(response) is not dict or response.get('contract')!=transport.CONTRACT or type(response.get('ok')) is not bool:
        raise ValueError('invalid curated service response')
    if response['ok']:
        if set(response)!={'contract','ok','result'}:raise ValueError('invalid curated response')
        return response['result']
    if set(response)!={'contract','ok','error'} or response['error']!='refused':raise ValueError('invalid curated refusal')
    raise ValueError('curated service refused request')
