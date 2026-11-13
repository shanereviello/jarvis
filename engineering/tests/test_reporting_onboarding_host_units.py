"""Deployment boundaries required by the onboarding service entries."""
from configparser import ConfigParser
from pathlib import Path


UNITS = Path(__file__).resolve().parents[1] / 'systemd'


def unit(name):
    parser = ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(UNITS / name)
    return parser


def test_operator_owns_distinct_socket_directories_and_remains_inactive_by_default():
    service = unit('rras-onboarding-operator.service')
    assert set(service['Service']['RuntimeDirectory'].split()) == {
        'rras-onboard-review', 'rras-onboard-browser',
        'rras-onboard-admission', 'rras-onboard-jarvis',
    }
    assert service['Service']['RuntimeDirectoryMode'] == '0700'
    assert service['Unit']['ConditionPathExists'].endswith('/host-enabled')
    assert service['Service']['User'] == 'rras-onboard-operator'


def test_access_verifiers_can_fetch_rotating_cloudflare_keys():
    for name in ('rras-onboarding-operator.service', 'rras-onboarding-attestation.service'):
        service = unit(name)['Service']
        assert service.get('IPAddressDeny') != 'any'
        assert {'AF_UNIX', 'AF_INET', 'AF_INET6'} <= set(service['RestrictAddressFamilies'].split())
        assert service['NoNewPrivileges'] == 'yes'


def test_planner_has_distinct_identity_and_does_not_start_without_marker():
    service = unit('rras-codex-planning.service')
    assert service['Service']['User'] == 'rras-codex-planner'
    assert service['Unit']['ConditionPathExists'].endswith('/host-enabled')
    assert service['Service']['StateDirectoryMode'] == '0700'


def test_native_planning_socket_and_process_have_dedicated_read_only_boundary():
    listener=unit('rras-codex-planning-native.socket')
    socket=listener['Socket']
    assert socket['SocketUser']=='rras-codex-planner'
    assert socket['SocketMode']=='0600' and socket['Accept']=='yes'
    assert listener['Unit']['ConditionPathExists'].endswith('/host-enabled')
    service=unit('rras-codex-planning-native@.service')['Service']
    assert service['User']=='rras-codex-native'
    assert service['WorkingDirectory']==service['ReadOnlyPaths']=='/srv/rras-codex-planning/workspace'
    assert service['ProtectSystem']=='strict' and 'ReadWritePaths' not in service
    assert service['StateDirectory']=='rras-codex-planning-native'
    assert 'AF_NETLINK' in service['RestrictAddressFamilies'].split()
    assert '/srv/rras-codex-workspaces-20261111' in service['InaccessiblePaths']
