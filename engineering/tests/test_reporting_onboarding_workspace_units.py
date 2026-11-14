import importlib.util
import os
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/onboarding_workspace_unit_evidence.py'
spec = importlib.util.spec_from_file_location('workspace_units_fixture', path)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_exact_units_still_require_independent_effective_isolation(tmp_path):
    unit_dir = tmp_path / 'units';unit_dir.mkdir(mode=0o700)
    issue = '00000000-0000-0000-0000-000000000123'
    workspace = str(tmp_path / 'workspace');release = str(tmp_path / 'release')
    binary = Path(release) / 'runtime/bin/codex';binary.parent.mkdir(parents=True);binary.write_bytes(b'fixture');binary.chmod(0o555)
    for parent in (Path(release),Path(release)/'runtime',binary.parent):parent.chmod(0o755)
    units = module.local('codex_issue_units').render(issue,workspace,release)
    for name,body in ((units['service_name'],units['service']), (units['socket_name'],units['listener'])):
        path = unit_dir / name;path.write_text(body);path.chmod(0o644)
    request = dict(issue_id=issue,workspace=workspace,native_socket=units['socket_path'])
    observed = []
    verifier = module.Verifier(unit_dir,release,lambda value:observed.append(value) or True,owner=os.getuid())
    assert verifier(request) and observed[0]['workspace'] == workspace
    with pytest.raises(ValueError,match='isolation'):
        module.Verifier(unit_dir,release,lambda _:False,owner=os.getuid())(request)
    (unit_dir / units['service_name']).write_text(units['service'] + '\nProtectSystem=no\n')
    with pytest.raises(ValueError,match='differ'):
        verifier(request)


def test_unit_verifier_refuses_symlink(tmp_path):
    unit_dir = tmp_path / 'units';unit_dir.mkdir(mode=0o700)
    target = tmp_path / 'target';target.write_text('fixture')
    path = unit_dir / 'alias';path.symlink_to(target)
    verifier = module.Verifier(unit_dir,'/opt/fixture',lambda _:True,owner=os.getuid())
    with pytest.raises(ValueError,match='regular'):
        verifier.read(path)


def test_effective_unit_requires_no_dropins_and_independent_sandbox():
    from types import SimpleNamespace
    effective = module.local('onboarding_workspace_effective_units')
    request = dict(issue_id='00000000-0000-0000-0000-000000000123',workspace='/srv/issue',socket='/run/issue.sock',
        service_name='fixture@.service',socket_name='fixture.socket',service_sha256='a'*64,socket_sha256='b'*64,native_release='/opt/release',native_binary_sha256='c'*64)
    service = dict(FragmentPath='/etc/systemd/system/fixture@.service',DropInPaths='',User='rras-codex-native',
        Group='rras-codex-native',WorkingDirectory='/srv/issue',ProtectSystem='strict',NoNewPrivileges='yes',
        PrivateTmp='yes',PrivateDevices='yes',ProtectHome='yes',ReadWritePaths='/srv/issue',
        RestrictAddressFamilies='AF_UNIX AF_INET AF_INET6 AF_NETLINK')
    socket = dict(FragmentPath='/etc/systemd/system/fixture.socket',DropInPaths='')
    commands = []
    def run(command, **_):
        commands.append(command[2])
        values = service if command[2].endswith('.service') else socket
        return SimpleNamespace(returncode=0,stdout=''.join(k+'='+v+'\n' for k,v in values.items()))
    verifier = effective.Verifier('/etc/systemd/system',lambda _:True,run=run)
    assert verifier(request)
    assert commands == ['fixture@rras-verification.service','fixture.socket']
    service['DropInPaths'] = '/etc/systemd/system/override.conf'
    with pytest.raises(ValueError,match='isolation'):verifier(request)
    service['DropInPaths'] = ''
    with pytest.raises(ValueError,match='sandbox'):
        effective.Verifier('/etc/systemd/system',lambda _:False,run=run)(request)


def test_sandbox_proof_requires_exact_units_freshness_and_no_models():
    from datetime import datetime,timezone
    sandbox = module.local('onboarding_sandbox_proof')
    expected = dict(issue_id='00000000-0000-0000-0000-000000000123',workspace='/srv/issue',socket='/run/issue.sock',
        service_name='fixture@.service',socket_name='fixture.socket',service_sha256='a'*64,socket_sha256='b'*64,native_release='/opt/release',native_binary_sha256='c'*64)
    proof = dict(contract='codex-sandbox-isolation-proof.v1',**expected,issued_at='2026-11-12T12:00:00Z',
        expires_at='2026-11-12T12:10:00Z',native_identity_verified=True,sandbox_own_write_allowed=True,
        sandbox_sibling_write_denied=True,models_started=0)
    now = lambda:datetime(2026,11,12,12,5,tzinfo=timezone.utc)
    verify = sandbox.Verifier('/root/fixture',clock=now,loader=lambda _:proof)
    assert verify(expected)
    with pytest.raises(ValueError,match='exact issue'):verify(dict(expected,workspace='/srv/other'))
    proof['models_started'] = 1
    with pytest.raises(ValueError,match='model-free'):verify(expected)
    proof['models_started'] = 0;proof['expires_at'] = '2026-11-12T12:30:00Z'
    with pytest.raises(ValueError,match='fresh'):verify(expected)


def test_proof_writer_requires_real_probe_and_unchanged_units(tmp_path):
    from datetime import datetime,timezone
    writer = module.local('onboarding_sandbox_proof_writer')
    expected = dict(issue_id='00000000-0000-0000-0000-000000000123',workspace='/srv/issue',socket='/run/issue.sock',
        service_name='fixture@.service',socket_name='fixture.socket',service_sha256='a'*64,socket_sha256='b'*64,native_release='/opt/release',native_binary_sha256='c'*64)
    result = dict(native_identity_verified=True,sandbox_own_write_allowed=True,sandbox_sibling_write_denied=True,models_started=0)
    audit = tmp_path / 'audit';audit.mkdir(mode=0o700)
    calls = []
    saved = writer.create(audit,'fixture.proof',expected,lambda value:calls.append(value) or True,
        lambda _:result,owner=os.getuid(),clock=lambda:datetime(2026,11,12,12,0,tzinfo=timezone.utc))
    assert len(calls) == 2 and not saved['execution_authorized']
    import json
    proof = json.loads((audit/'fixture.proof').read_bytes())
    verify = module.local('onboarding_sandbox_proof').Verifier('/root/fixture',loader=lambda _:proof,
        clock=lambda:datetime(2026,11,12,12,5,tzinfo=timezone.utc))
    assert verify(expected)
    states = iter([True,False])
    with pytest.raises(ValueError,match='changed'):
        writer.create(audit,'changed.proof',expected,lambda _:next(states),lambda _:result,owner=os.getuid())
    assert not (audit/'changed.proof').exists()


def test_native_probe_is_model_free_and_refuses_unprivileged_invocation():
    import ast
    probe = module.local('onboarding_native_sandbox_probe')
    compile(probe.CHILD,'native-probe-fixture','exec')
    tree = ast.parse(probe.CHILD)
    nested = [node.value for node in ast.walk(tree) if isinstance(node,ast.Assign)
              and any(isinstance(target,ast.Name) and target.id == 'code' for target in node.targets)]
    assert len(nested) == 1
    compile(ast.literal_eval(nested[0]),'native-inner-fixture','exec')
    assert "'thread/start'" in probe.CHILD and "'command/exec'" in probe.CHILD
    assert "'turn/start'" not in probe.CHILD
    if os.geteuid() != 0:
        with pytest.raises(ValueError,match='root'):
            probe.probe({})


def test_producer_wires_current_units_and_native_probe(monkeypatch):
    from types import SimpleNamespace
    producer = module.local('onboarding_sandbox_producer')
    expected = {'fixture':'unit-binding'}
    calls = []
    class Effective:
        def __init__(self, _, __):pass
        def __call__(self, value):calls.append('effective');return value == expected
    class Units:
        def __init__(self, _, __, capture):self.capture = capture
        def __call__(self, request):calls.append('units');return self.capture(expected)
    def probe(value):calls.append('probe');assert value == expected;return {'fixture':'result'}
    def write(_, __, value, recheck, native_probe):
        assert recheck(value) and native_probe(value) == {'fixture':'result'} and recheck(value)
        return {'models_started':0,'execution_authorized':False}
    modules = {'onboarding_workspace_effective_units':SimpleNamespace(Verifier=Effective),
        'onboarding_workspace_unit_evidence':SimpleNamespace(Verifier=Units),
        'onboarding_native_sandbox_probe':SimpleNamespace(probe=probe),
        'onboarding_sandbox_proof_writer':SimpleNamespace(create=write)}
    monkeypatch.setattr(producer, 'local', lambda name:modules[name])
    monkeypatch.setattr(producer.os, 'getuid', lambda:0)
    monkeypatch.setattr(producer.os, 'geteuid', lambda:0)
    config = dict(unit_directory='/unit',native_release='/release',proof_directory='/proof',proof_name='fixture.proof',
        request=dict(issue_id='fixture',workspace='/work',native_socket='/socket'))
    assert not producer.produce(config)['execution_authorized']
    assert calls == ['units','effective','units','effective','probe','units','effective']
