from pathlib import Path
import yaml

def test_ordinary_adapter_start_does_not_require_migration_service():
    root=Path(__file__).resolve().parents[1]
    config=yaml.safe_load((root/'deploy/jarvis-activity/compose.yaml').read_text())
    assert config['services']['jarvis-activity-migrate']['profiles']==['migration']
    dependencies=config['services']['jarvis-activity-adapter']['depends_on']
    assert dependencies=={'jarvis-activity-postgres':{'condition':'service_healthy'}}
    assert 'runner_egress' not in config['networks']
