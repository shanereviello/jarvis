import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/hermes_planning_entry.py'
spec=importlib.util.spec_from_file_location('jarvis_planning_entry_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_entry_closes_server_on_exit(monkeypatch):
    events=[]
    class Server:
        def serve_forever(self,poll_interval):events.append(('serve',poll_interval))
        def server_close(self):events.append(('close',))
    def local(name):
        if name=='hermes_planning_scope':return SimpleNamespace(Resolver=lambda path:('scope',path))
        if name=='hermes_planning_service':return SimpleNamespace(assemble=lambda *args:Server())
        raise AssertionError(name)
    monkeypatch.setattr(module,'local',local)
    module.run({},'/private/scopes.json',b'reader',b'bridge')
    assert events==[('serve',0.2),('close',)]


def test_entry_rejects_relative_scope(monkeypatch):
    monkeypatch.setattr(module,'local',lambda name:pytest.fail('must refuse before service assembly'))
    with pytest.raises(ValueError):module.run({},'scopes.json',b'reader',b'bridge')
