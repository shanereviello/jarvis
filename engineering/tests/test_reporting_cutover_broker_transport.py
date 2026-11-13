import importlib.util
import os
from pathlib import Path
import socket
import threading
import time

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/codex_cutover_broker_transport.py'
spec = importlib.util.spec_from_file_location('cutover_transport_fixture', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_transport_uses_kernel_peer_and_only_operation():
    class Broker:
        peer_uid = os.getuid()
        def call(self, peer, operation):
            assert peer == self.peer_uid and operation == 'digest'
            return 'a' * 64
    client, server = socket.socketpair()
    errors = []
    def worker():
        try:
            with server:
                module.serve(server, Broker())
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=worker)
    thread.start()
    transport = module.unix()
    with client:
        transport.send(client, {'operation': 'digest'}, 4096, time.monotonic() + 5)
        assert transport.receive(client, 4096, time.monotonic() + 5) == {'result': 'a' * 64}
    thread.join(5)
    assert not thread.is_alive() and not errors


def test_transport_rejects_other_peer_before_reading_request():
    class Broker:
        peer_uid = os.getuid() + 100
    client, server = socket.socketpair()
    try:
        import pytest
        with pytest.raises(ValueError, match='peer refused'):
            module.serve(server, Broker())
    finally:
        client.close()
        server.close()


def test_client_refuses_non_socket(tmp_path):
    import pytest
    path = tmp_path / 'not-a-socket'
    path.write_text('fixture')
    with pytest.raises(ValueError):
        module.call(path, 'digest')
