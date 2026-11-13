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
