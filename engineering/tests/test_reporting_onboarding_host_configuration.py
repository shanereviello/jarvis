import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_host_configuration.py'
spec=importlib.util.spec_from_file_location('host_config_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def uid(n):return f'00000000-0000-4000-8000-{n:012d}'


def args():
    return (dict(organization_id=uid(1),team_id=uid(2),codex_app_user_id=uid(3),jarvis_app_user_id=uid(4),human_id=uid(5)),
        dict(issuer='https://fixture.cloudflareaccess.com',audience='fixture',email='owner@example.test',origin='https://fixture.example.test'),
        15678,'172.19.0.1','/opt/rras-engineering/releases/standardized-history-123456789abc',uid(6))


def test_staged_configuration_separates_peers_and_does_not_authorize_execution():
    value=module.build(*args())
    assert value['codex']['runtime_policy']['planning_authorized'] is False
    assert value['codex']['native_peer_uid']==0 and value['codex']['runtime_policy']['peer_uid']==991
    assert value['operator']['planning_peer_uid']==61181 and value['operator']['jarvis_review']['peer_uid']==61180
    assert value['browser']['operator_socket']==value['operator']['browser_socket']
    assert value['operator']['jarvis_review']['scope_path']=='/etc/rras-engineering/onboarding-operator/jarvis-scopes.json'
    assert value['browser']['path_prefix']=='/engineering-approval'
    assert value['scopes']['fallback_scope']=={'kind':'non_git','id':'jarvis-non-git'}
    assert value['codex']['listen_port']!=value['jarvis']['listen_port']!=value['browser']['port']


def test_configuration_rejects_nonprivate_gateway_and_mixed_identity():
    values=list(args());values[3]='8.8.8.8'
    with pytest.raises(ValueError):module.build(*values)
    values=list(args());values[0]['human_id']=values[0]['codex_app_user_id']
    with pytest.raises(ValueError):module.build(*values)
