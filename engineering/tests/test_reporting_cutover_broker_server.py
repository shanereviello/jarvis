import importlib.util
import os
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/codex_cutover_broker_server.py'
spec = importlib.util.spec_from_file_location('cutover_server_fixture', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_listener_refuses_unprivileged_caller_without_modifying_path(tmp_path):
    if os.getuid() == 0:
        pytest.skip('requires unprivileged fixture')
    path = tmp_path / 'broker.sock'
    with pytest.raises(ValueError, match='root service'):
        with module.listener(path, 1234):
            pass
    assert not path.exists()


def test_cross_uid_probe_passes_broker_to_listener():
    probe_path = path.with_name('probe_cutover_broker_cross_uid.py')
    probe_spec = importlib.util.spec_from_file_location('cross_uid_probe_fixture', probe_path)
    probe = importlib.util.module_from_spec(probe_spec)
    probe_spec.loader.exec_module(probe)
    listener, broker = object(), object()
    class Server:
        def serve_once(self, actual_listener, actual_broker):
            assert actual_listener is listener and actual_broker is broker
            return True
    assert probe.accept(Server(), listener, broker)
