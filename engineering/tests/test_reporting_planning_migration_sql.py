import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'tools/rras_reporting/planning_migration_sql.py'
spec=importlib.util.spec_from_file_location('planning_migration_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_migration_rejects_changed_inputs_and_wraps_both_in_one_transaction():
    schema=(ROOT/'contracts/linear-codex-planning-v1.sql').read_bytes()
    grants=(ROOT/'contracts/linear-codex-planning-n8n-grants-v1.sql').read_bytes()
    sql=module.build(schema,grants)
    assert sql.startswith('BEGIN;\n') and sql.rstrip().endswith('COMMIT;')
    assert sql.count('\nCOMMIT;')==1
    assert sql.index('LOCK TABLE') < sql.index('CREATE TABLE linear_bridge.codex_planning_sessions')
    assert sql.index('GRANT EXECUTE') < sql.index('DO $verify$') < sql.rindex('COMMIT;')
    with pytest.raises(ValueError):module.build(schema+b' ',grants)
    with pytest.raises(ValueError):module.build(schema,grants+b' ')
