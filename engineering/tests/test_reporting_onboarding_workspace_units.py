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
    workspace = str(tmp_path / 'workspace');release = '/opt/rras-engineering/releases/fixture'
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
        service_name='fixture@.service',socket_name='fixture.socket',service_sha256='a'*64,socket_sha256='b'*64,native_release='/opt/release')
    service = dict(FragmentPath='/etc/systemd/system/fixture@.service',DropInPaths='',User='rras-codex-native',
        Group='rras-codex-native',WorkingDirectory='/srv/issue',ProtectSystem='strict',NoNewPrivileges='yes',
        PrivateTmp='yes',PrivateDevices='yes',ProtectHome='yes',ReadWritePaths='/srv/issue',
        RestrictAddressFamilies='AF_UNIX AF_INET AF_INET6 AF_NETLINK')
    socket = dict(FragmentPath='/etc/systemd/system/fixture.socket',DropInPaths='')
    def run(command, **_):
        values = service if command[2].endswith('.service') else socket
        return SimpleNamespace(returncode=0,stdout=''.join(k+'='+v+'\n' for k,v in values.items()))
    verifier = effective.Verifier('/etc/systemd/system',lambda _:True,run=run)
    assert verifier(request)
    service['DropInPaths'] = '/etc/systemd/system/override.conf'
    with pytest.raises(ValueError,match='isolation'):verifier(request)
    service['DropInPaths'] = ''
    with pytest.raises(ValueError,match='sandbox'):
        effective.Verifier('/etc/systemd/system',lambda _:False,run=run)(request)
