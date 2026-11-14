import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_n8n_import_stage.py'
spec=importlib.util.spec_from_file_location('n8n_import_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def inputs():
    workflows={};tokens={};ids={};workflow_ids={}
    for i,(placeholder,name) in enumerate(module.TOKENS.items(),1):
        ids[name]=f'{i:016x}';tokens[name]=f'{i:064x}'
    for i,name in enumerate(sorted(module.WORKFLOWS),20):
        placeholder=list(module.TOKENS)[(i-20)%len(module.TOKENS)]
        workflows[name]=dict(name=name,active=False,nodes=[dict(type='n8n-nodes-base.webhook',
            parameters=dict(path='fixture-'+name),credentials=dict(httpHeaderAuth=dict(id=placeholder,name='pending')))])
        workflow_ids[name]=f'{i:016x}'
    return workflows,ids,tokens,workflow_ids


def test_builds_only_inactive_workflows_and_replaces_references():
    values=inputs();result=module.build(*values)
    assert len(result['credentials'])==6 and len(result['workflows'])==8
    assert all(not item['active'] for item in result['workflows'])
    assert all(item['data']['name']=='Authorization' and item['data']['value'].startswith('Bearer ') for item in result['credentials'])
    assert all(node['credentials']['httpHeaderAuth']['id'] in values[1].values() for item in result['workflows'] for node in item['nodes'])
    assert 'PENDING_' in str(values[0])


def test_rejects_active_workflow_and_unexpected_reference():
    values=inputs();values[0]['codex-origin']['active']=True
    with pytest.raises(ValueError):module.build(*values)
    values=inputs();values[0]['codex-origin']['nodes'][0]['credentials']['httpHeaderAuth']['id']='other'
    with pytest.raises(ValueError):module.build(*values)
