from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_hermes_release_retires_only_legacy_mounts_and_write_roots():
    old = yaml.safe_load((ROOT / 'deploy/hermes/compose.yaml').read_text())['services']['hermes']
    new = yaml.safe_load((ROOT / 'deploy/hermes/compose.release.yaml').read_text())
    service = new['services']['hermes']
    assert new['name'] == 'hermes'
    assert service['command'] == old['command']
    assert service['restart'] == old['restart']
    assert service['pull_policy'] == 'never'
    assert ':?' in service['image']
    assert 'ports' not in service and 'build' not in service
    assert new['networks']['jarvis-net']['external'] is True
    roots = service['environment']['HERMES_WRITE_SAFE_ROOT'].split(':')
    assert roots == ['/opt/data', '/workspace/jarvis-artifacts', '/workspace/shared']
    assert service['environment']['HERMES_UID'] == old['environment']['HERMES_UID']
    assert service['environment']['HERMES_GID'] == old['environment']['HERMES_GID']
    mounts = {m['source']: m for m in service['volumes']}
    assert set(mounts) == {'/srv/hermes/data', '/srv/git/jarvis', '/srv/git/robot_ws',
                           '/srv/notes/jarvis-artifacts', '/srv/shared/jarvis'}
    for source, mount in mounts.items():
        assert mount['bind']['create_host_path'] is False
        assert mount.get('read_only', False) is source.startswith('/srv/git/')
    reference = ROOT / 'deploy/hermes/skills/devops/containerized-agent-operations/references/hermes-safe-write-roots.md'
    text = reference.read_text()
    assert '/workspace/jarvis-tasks' not in text and '/workspace/robot-tasks' not in text
