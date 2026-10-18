from pathlib import Path
import yaml

def test_ordinary_adapter_start_does_not_require_migration_service():
    root=Path(__file__).resolve().parents[1]
    config=yaml.safe_load((root/'deploy/jarvis-activity/compose.yaml').read_text())
    assert config['services']['jarvis-activity-migrate']['profiles']==['migration']
    dependencies=config['services']['jarvis-activity-adapter']['depends_on']
    assert dependencies=={'jarvis-activity-postgres':{'condition':'service_healthy'}}
    assert 'runner_egress' not in config['networks']


def test_release_reuses_data_and_networks_without_implicit_upgrade():
    root=Path(__file__).resolve().parents[1]
    config=yaml.safe_load((root/'deploy/jarvis-activity/compose.release.yaml').read_text())
    assert set(config['services'])=={'jarvis-activity-postgres','jarvis-activity-adapter'}
    assert config['volumes']['jarvis_activity_pgdata']=={'external':True,'name':'jarvis-activity_jarvis_activity_pgdata'}
    assert {v['name'] for v in config['networks'].values()}=={'jarvis-activity_activity_internal','jarvis-activity_controller_internal'}
    for service in config['services'].values():
        assert service['pull_policy']=='never' and service['restart']=='no'
        assert ':?' in service['image']
        assert not any(key in service for key in ('build','ports','command'))
        for mount in service['volumes']:
            if mount['type']=='bind':
                assert mount['bind']['create_host_path'] is False
                assert '/srv/hermes-dev' not in mount['source']
    pg=config['services']['jarvis-activity-postgres']
    adapter=config['services']['jarvis-activity-adapter']
    pg_password=next(m for m in pg['volumes'] if m['target']=='/run/secrets/jarvis_activity_app_password')
    adapter_password=next(m for m in adapter['volumes'] if m['target']=='/run/secrets/jarvis_activity_app_password')
    assert pg_password['source']!=adapter_password['source']
    assert pg_password['read_only'] and adapter_password['read_only']
    roles={m['target']:m['read_only'] for m in adapter['volumes'] if '/runner-state/' in m['target']}
    assert roles=={'/srv/jarvis-activity/runner-state/phase4b-controller-staging':True,
                  '/srv/jarvis-activity/runner-state/phase4b-controller-retained':False,
                  '/srv/jarvis-activity/runner-state/phase5a-executor-staging':False,
                  '/srv/jarvis-activity/runner-state/phase5a-executor-retained':False}
    assert adapter['read_only'] and adapter['cap_drop']==['ALL']
