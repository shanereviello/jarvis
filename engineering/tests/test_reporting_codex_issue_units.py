import importlib.util
from pathlib import Path
import uuid
import pytest

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
spec=importlib.util.spec_from_file_location('issue_units_test',ROOT/'codex_issue_units.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ISSUE=str(uuid.UUID(int=3))
RELEASE='/opt/rras-engineering/releases/standardized-history-9e7954c07fdb'


def test_inactive_issue_unit_pins_working_and_only_writable_checkout(tmp_path):
    root=str(tmp_path/'checkout');value=m.render(ISSUE,root,RELEASE)
    assert value['socket_path']=='/run/rras-codex-runtime/coding-'+ISSUE+'.sock'
    assert 'WorkingDirectory='+root+'\n' in value['service']
    assert [line for line in value['service'].splitlines() if line.startswith('ReadWritePaths=')]==['ReadWritePaths='+root]
    assert 'ProtectSystem=strict\n' in value['service'] and 'NoNewPrivileges=yes\n' in value['service']
    assert 'AF_NETLINK' in value['service'] and 'Accept=yes\n' in value['listener']
    assert value['service_name'].replace('@.service','.socket')==value['socket_name']
    assert '\nService=' not in value['listener']


@pytest.mark.parametrize('workspace',['/tmp/some space','/tmp/../etc','relative','/tmp/%i','/tmp/x\nUser=root'])
def test_refuses_unsafe_systemd_paths(workspace):
    with pytest.raises(ValueError):m.render(ISSUE,workspace,RELEASE)


def test_refuses_invalid_issue_identity(tmp_path):
    with pytest.raises(ValueError):m.render('REV-50',str(tmp_path/'work'),RELEASE)
