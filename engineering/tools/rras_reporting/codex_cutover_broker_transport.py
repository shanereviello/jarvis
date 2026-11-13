"""Bounded single-operation transport for the fixed cutover broker.

The caller supplies an already accepted Unix socket. Service lifecycle, socket
permissions and trusted broker construction are intentionally separate.
"""
import importlib.util
from pathlib import Path
import time


def unix():
    path = Path(__file__).resolve().parents[1] / 'rras_history/unix.py'
    spec = importlib.util.spec_from_file_location('cutover_transport_unix', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def serve(connection, broker):
    transport = unix()
    deadline = time.monotonic() + 5
    peer = transport.peer(connection)
    if peer != broker.peer_uid:
        raise ValueError('broker peer refused')
    request = transport.receive(connection, 4096, deadline)
    if type(request) is not dict or set(request) != {'operation'}:
        raise ValueError('one broker operation required')
    result = broker.call(peer, request['operation'])
    transport.send(connection, {'result': result}, 4096, deadline)
