"""Root-owned Unix listener for one fixed cutover broker; no daemon installer.

The caller constructs the broker from protected state, supplies independent
verifiers and retains the operator lock and restart guard for this whole scope.
"""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import socket
import stat


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_server_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def listener(path, peer_gid):
    transport = local('codex_cutover_broker_transport').unix()
    if os.getuid() != 0 or os.geteuid() != 0 or type(peer_gid) is not int or peer_gid <= 0:
        raise ValueError('root service and dedicated peer group required')
    path = transport.endpoint(path)
    transport.parents(path, 0)
    parent = path.parent.lstat()
    if parent.st_uid != 0 or stat.S_IMODE(parent.st_mode) not in (0o700, 0o710, 0o750):
        raise ValueError('root-controlled socket directory required')
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    identity = None
    try:
        # Bind never unlinks an existing path, even if an earlier service died.
        server.bind(str(path))
        info = path.lstat()
        identity = (info.st_dev, info.st_ino)
        os.chown(path, 0, peer_gid)
        os.chmod(path, 0o660)
        server.listen(4)
        server.settimeout(0.2)
        yield server
    finally:
        server.close()
        if identity is not None:
            try:
                info = path.lstat()
                if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == identity:
                    path.unlink()
            except FileNotFoundError:
                pass


def serve_once(server, broker):
    try:
        connection, _ = server.accept()
    except socket.timeout:
        return False
    with connection:
        try:
            local('codex_cutover_broker_transport').serve(connection, broker)
        except (ValueError, OSError, TimeoutError):
            # No implicit retry: a mutation may have completed before the reply.
            return True
    return True
