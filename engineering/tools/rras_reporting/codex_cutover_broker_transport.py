"""Bounded single-operation transport for the fixed cutover broker.

The caller supplies an already accepted Unix socket. Service lifecycle, socket
permissions and trusted broker construction are intentionally separate.
"""
import importlib.util
from pathlib import Path
import socket
import stat
import time


def unix():
    path = Path(__file__).resolve().parents[1] / 'rras_history/unix.py'
    spec = importlib.util.spec_from_file_location('cutover_transport_unix', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def serve(connection, broker):
    transport = unix()
    deadline = time.monotonic() + 120
    peer = transport.peer(connection)
    if peer != broker.peer_uid:
        raise ValueError('broker peer refused')
    request = transport.receive(connection, 4096, deadline)
    if type(request) is not dict or set(request) != {'operation'}:
        raise ValueError('one broker operation required')
    result = broker.call(peer, request['operation'])
    transport.send(connection, {'result': result}, 4096, deadline)


def call(path, operation):
    """Send only an operation after authenticating the root socket and peer."""
    transport = unix()
    endpoint = transport.endpoint(path)
    transport.parents(endpoint, 0)
    info = endpoint.lstat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0 or
            stat.S_IMODE(info.st_mode) not in (0o600, 0o660)):
        raise ValueError('root-controlled broker socket required')
    deadline = time.monotonic() + 120
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        transport.remaining(connection, deadline)
        connection.connect(str(endpoint))
        if transport.peer(connection) != 0:
            raise ValueError('root broker identity required')
        transport.send(connection, {'operation': operation}, 4096, deadline)
        response = transport.receive(connection, 4096, deadline)
    if type(response) is not dict or set(response) != {'result'}:
        raise ValueError('invalid broker response')
    return response['result']
