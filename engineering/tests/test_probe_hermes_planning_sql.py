import importlib.util
from pathlib import Path


path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/probe_hermes_planning_sql.py'
spec=importlib.util.spec_from_file_location('probe_sql_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_probe_uses_exact_query_with_only_aggregate_output(monkeypatch):
    captured={};monkeypatch.setattr(module.os,'geteuid',lambda:0)
    monkeypatch.setattr(module.subprocess,'run',lambda argv,**kwargs:captured.update(argv=argv,**kwargs))
    module.main();sql=captured['input']
    assert 'CROSS JOIN LATERAL' in sql and "jsonb_build_object('action'" in sql
    assert 'GROUP BY action' in sql and 'promptContext' in sql
    assert all(slot not in sql for slot in ('$1','$2','$3','$4'))
    assert not any(word in sql.upper() for word in (' INSERT ',' UPDATE ',' DELETE ',' ALTER '))
