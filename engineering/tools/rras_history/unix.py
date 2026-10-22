"""Bounded Linux Unix-stream transport for passive repository-scoped history.

No TCP, root broker, credential access or coding actions. One request/connection.
"""
import importlib.util
import os
from pathlib import Path
import socket
import sqlite3
import stat
import struct
import time
from jsonschema import ValidationError

REQUEST_LIMIT = 256 * 1024
RESPONSE_LIMIT = 2 * 1024 * 1024
DEADLINE_SECONDS = 5
CONTRACT = 'engineering-history-rpc.v1'


def local(name):
    spec = importlib.util.spec_from_file_location('history_unix_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def uid(value):
    if type(value) is not int or not 1 <= value < 2**32 - 1 or value in (996, 997):
        raise ValueError('inadmissible service identity')
    return value


def endpoint(value, *, socket_path=True):
    p = Path(value)
    if not p.is_absolute() or p.resolve(strict=False) != p or (socket_path and len(os.fsencode(p)) > 107):
        raise ValueError('canonical bounded Unix path required')
    return p


def parents(path, owner):
    """Trusted root/service ancestors; /tmp may be root-owned sticky."""
    for p in (path.parent, *path.parent.parents):
        info = p.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, owner):
            raise ValueError('untrusted endpoint ancestor')
        if info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            raise ValueError('writable endpoint ancestor')
    # The immediate parent cannot be a shared sticky directory.
    info = path.parent.lstat()
    if info.st_mode & 0o022:
        raise ValueError('protected endpoint directory required')


def peer(connection):
    if not hasattr(socket, 'SO_PEERCRED'):
        raise ValueError('Linux peer credentials required')
    pid, peer_uid, gid = struct.unpack('iII', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if pid < 1: raise ValueError('live peer required')
    return peer_uid


def remaining(connection, deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0: raise TimeoutError('history transport deadline')
    connection.settimeout(seconds)


def exact(connection, size, deadline):
    data = bytearray()
    while len(data) < size:
        remaining(connection, deadline)
        part = connection.recv(min(65536, size - len(data)))
        if not part: raise ValueError('truncated history frame')
        data.extend(part)
    return bytes(data)


def receive(connection, maximum, deadline):
    size = struct.unpack('!I', exact(connection, 4, deadline))[0]
    if not 1 <= size <= maximum: raise ValueError('bounded history frame required')
    raw = exact(connection, size, deadline)
    remaining(connection, deadline)
    if connection.recv(1): raise ValueError('one history frame required')
    return local('contract').decode(raw, max_bytes=maximum)


def send(connection, value, maximum, deadline):
    raw = local('contract').encoded(value)
    if not 1 <= len(raw) <= maximum: raise ValueError('bounded history response required')
    remaining(connection, deadline)
    connection.sendall(struct.pack('!I', len(raw)) + raw)
    connection.shutdown(socket.SHUT_WR)


def load_policy(path):
    p = endpoint(path, socket_path=False); parents(p, os.getuid())
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()) or
                info.st_nlink != 1 or info.st_mode & 0o027 or info.st_size > local('contract').MAX_REQUEST):
            raise ValueError('protected regular access policy required')
        return local('contract').decode(stream.read(local('contract').MAX_REQUEST + 1))


class Server:
    def __init__(self, path, store, policy):
        uid(os.getuid())
        if os.geteuid() != os.getuid(): raise ValueError('unprivileged service required')
        self.path = endpoint(path)
        self.access = local('access').Access(store, policy)
        self.listener = None; self.identity = None

    def __enter__(self):
        if self.listener is not None or self.identity is not None: raise ValueError('service already listening')
        parents(self.path, os.getuid())
        if self.path.parent.stat().st_uid != os.getuid():
            raise ValueError('service-owned runtime directory required')
        # Never adopt or unlink an existing path, including a stale socket.
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.path))
            info = self.path.lstat(); self.identity = (info.st_dev, info.st_ino)
            os.chmod(self.path, 0o660)
            listener.listen(8); listener.settimeout(0.2)
            self.listener = listener
            return self
        except BaseException:
            listener.close(); self.cleanup(); raise

    def cleanup(self):
        if self.identity is not None:
            try:
                info = self.path.lstat()
                if (info.st_dev, info.st_ino) == self.identity and stat.S_ISSOCK(info.st_mode):
                    self.path.unlink()
            except FileNotFoundError: pass
            finally: self.identity = None

    def __exit__(self, *exc):
        if self.listener is not None: self.listener.close(); self.listener = None
        self.cleanup()

    def serve_once(self):
        if self.listener is None: raise ValueError('history service not listening')
        try: connection, _ = self.listener.accept()
        except socket.timeout: return False
        with connection:
            deadline = time.monotonic() + DEADLINE_SECONDS
            try:
                caller = peer(connection)
                if caller not in self.access.grants: raise ValueError('access refused')
                message = receive(connection, REQUEST_LIMIT, deadline)
                result = self.access.dispatch(caller, message)
                send(connection, dict(contract=CONTRACT, ok=True, result=result), RESPONSE_LIMIT, deadline)
            except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, ValidationError):
                # Uniform bounded failures contain no submitted text, paths or SQL.
                # A write may already be committed. Retry only with the same key.
                try: send(connection, dict(contract=CONTRACT, ok=False, error='refused'), RESPONSE_LIMIT, deadline)
                except (OSError, ValueError): pass
        return True


def call(path, service_uid, message):
    uid(service_uid); p = endpoint(path); parents(p, service_uid)
    info = p.lstat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != service_uid or
            stat.S_IMODE(info.st_mode) not in (0o600, 0o660)):
        raise ValueError('trusted history socket required')
    deadline = time.monotonic() + DEADLINE_SECONDS
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        remaining(connection, deadline); connection.connect(str(p))
        # Verify the connected process before sending any private narrative.
        if peer(connection) != service_uid: raise ValueError('history service identity differs')
        send(connection, message, REQUEST_LIMIT, deadline)
        response = receive(connection, RESPONSE_LIMIT, deadline)
    if type(response) is not dict or response.get('contract') != CONTRACT or type(response.get('ok')) is not bool:
        raise ValueError('invalid history service response')
    if response['ok']:
        if set(response) != {'contract', 'ok', 'result'}: raise ValueError('invalid history response')
        return response['result']
    if set(response) != {'contract', 'ok', 'error'} or response['error'] != 'refused':
        raise ValueError('invalid history refusal')
    raise ValueError('history service refused request')
