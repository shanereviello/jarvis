import importlib.util
from pathlib import Path
from test_reporting_n8n_codex import config

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/n8n_codex_planning.py'
spec=importlib.util.spec_from_file_location('n8n_codex_planning_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_inactive_candidate_keeps_execution_and_planning_routes_separate(config):
    result=module.render(config);workflow=result['workflow'];nodes={node['name']:node for node in workflow['nodes']}
    assert not result['production_ready'] and not workflow['active'] and not result['dispatch_complete']
    branches=workflow['connections']['Select planning route']['main']
    assert branches[0][0]['node']=='Retain Codex planning event'
    assert branches[1][0]['node']=='Retain Codex event'
    assert 'codex_planning_accept' in nodes['Retain Codex planning event']['parameters']['query']
    assert 'codex_accept(' in nodes['Retain Codex event']['parameters']['query']
    assert nodes['Retain Codex planning event']['credentials']==nodes['Retain Codex event']['credentials']
