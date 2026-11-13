import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

path = Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_cutover_peer_entry.py'
spec = importlib.util.spec_from_file_location('cutover_peer_fixture',path)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_peer_binds_request_and_requires_live_protected_broker(monkeypatch):
    runtime = module.local('codex_runtime')
    request = {'issue_id':'fixture'}
    plan = {'evidence_sha256':hashlib.sha256(runtime.encoded(request)).hexdigest(),'authority':{'fixture':True}}
    config = dict(contract='codex-issue-cutover-host.v1',request=request,transition={'plan':plan,'old':{},'new':{}},
        operator_socket='/operator',operator_uid=123,workspace_root='/work',native_release='/release',sandbox_proof='/proof',
        execution_grants='/grants',audit_directory='/audit',broker_socket='/broker')
    calls = []
    class Files:
        def __init__(self, _):pass
        def verify(self):calls.append('verify');return True
    class Adapter:
        def __init__(self, root, submitted, verify, authority, files, lock):
            assert root == '/var/lib/rras-codex-adapter/runtime' and submitted == request
            with lock():assert verify(request) and authority(request) == plan['authority']
            with pytest.raises(ValueError,match='changed'):verify({'issue_id':'other'})
    def execute(adapter, expected_plan_sha256):
        assert expected_plan_sha256 == hashlib.sha256(runtime.encoded(plan)).hexdigest()
        return {'models_started':0}
    modules = {'codex_runtime':runtime,'codex_cutover_broker_client':SimpleNamespace(Files=Files),
        'codex_cutover_journal_adapter':SimpleNamespace(Adapter=Adapter),
        'codex_issue_cutover':SimpleNamespace(execute=execute)}
    monkeypatch.setattr(module,'local',lambda name:modules[name])
    monkeypatch.setattr(module.pwd,'getpwnam',lambda _:SimpleNamespace(pw_uid=61180,pw_gid=61180))
    monkeypatch.setattr(module.os,'getuid',lambda:61180);monkeypatch.setattr(module.os,'geteuid',lambda:61180)
    monkeypatch.setattr(module.os,'getgid',lambda:61180);monkeypatch.setattr(module.os,'getegid',lambda:61180)
    monkeypatch.setattr(module.os,'getgroups',lambda:[])
    assert module.run(config) == {'models_started':0}
    assert len(calls) == 3
