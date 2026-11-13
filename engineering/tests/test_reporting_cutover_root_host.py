from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/codex_cutover_root_host.py'
spec = importlib.util.spec_from_file_location('cutover_host_fixture', path)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


@pytest.mark.parametrize('success', [True, False])
def test_host_only_releases_mask_after_consistent_completion(monkeypatch, success):
    state = {'acquired':False, 'released':False}
    class Guard:
        def __init__(self, *_): pass
        def acquire(self): state['acquired'] = True
        def verified(self): return state['acquired'] and not state['released']
        def release(self, check):
            assert check()
            state['released'] = True
    class Files:
        def __init__(self, *_): pass
        def digest(self): return 'new' if state.get('complete') else 'old'
    class Broker:
        def __init__(self, **_):
            self.stage, self.old, self.new, self.plan_sha, self.value = 'new', 'old', 'new', 'plan', {'plan':{}}
    @contextmanager
    def listener(*_): yield object()
    def serve(_, broker):
        if not success: raise OSError('simulated interrupted connection')
        broker.stage = 'complete'
        state['complete'] = True
    modules = {'codex_cutover_persistent_guard':SimpleNamespace(Guard=Guard),
        'codex_cutover_root_files':SimpleNamespace(Files=Files),
        'codex_cutover_fixed_broker':SimpleNamespace(Broker=Broker),
        'codex_cutover_broker_server':SimpleNamespace(listener=listener, serve_once=serve)}
    @contextmanager
    def lock(_): yield
    monkeypatch.setattr(host, 'local', lambda name:modules[name])
    monkeypatch.setattr(host, 'lock', lock)
    args = dict(unit='fixture.service', socket_path='/fixture', peer_uid=1, peer_gid=1,
        policy_path='/policy', audit_dir='/audit', transition={}, verify_journal=lambda *_:True,
        verify_evidence=lambda _:True)
    if success:
        assert host.run(**args)['completed']
        assert state['released']
    else:
        with pytest.raises(OSError):host.run(**args)
        assert state['acquired'] and not state['released']


def test_host_refuses_stale_evidence_before_masking(monkeypatch):
    state = {'acquired':False}
    class Guard:
        def __init__(self, *_): pass
        def acquire(self): state['acquired'] = True
        def verified(self): return False
    class Files:
        def __init__(self, *_): pass
        def digest(self): return 'old'
    class Broker:
        def __init__(self, **_): self.old, self.value = 'old', {'plan':{}}
    modules = {'codex_cutover_persistent_guard':SimpleNamespace(Guard=Guard),
        'codex_cutover_root_files':SimpleNamespace(Files=Files),
        'codex_cutover_fixed_broker':SimpleNamespace(Broker=Broker)}
    @contextmanager
    def lock(_): yield
    monkeypatch.setattr(host, 'local', lambda name:modules[name])
    monkeypatch.setattr(host, 'lock', lock)
    with pytest.raises(ValueError, match='evidence'):
        host.run(unit='fixture.service', socket_path='/fixture', peer_uid=1, peer_gid=1,
            policy_path='/policy', audit_dir='/audit', transition={}, verify_journal=lambda *_:True,
            verify_evidence=lambda _:False)
    assert not state['acquired']
