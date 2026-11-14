import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from test_reporting_n8n_codex import config

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/n8n_planning_dispatch.py'
spec=importlib.util.spec_from_file_location('planning_dispatch_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_dispatch_and_reconcile_are_inactive_separate_and_do_not_retry(config):
    result=m.render(config,'http://172.19.0.1:8767','separate-planning-token')
    assert not result['production_ready'] and result['stop_delivery_candidate'] and not result['stop_delivery_verified']
    for key in ('dispatch','reconcile','stop'):
        workflow=result['workflows'][key]
        assert not workflow['active']
        node=next(x for x in workflow['nodes'] if x['name']=='Call planning runtime')
        assert node['retryOnFail'] is False and node['credentials']['httpHeaderAuth']['id']=='separate-planning-token'
    outbound=result['workflows']['outbound']
    assert not outbound['active'] and result['outbox_delivery_candidate'] and not result['outbox_delivery_verified']
    assert all('linear_bridge.codex_outbox' not in n['parameters'].get('query','') for n in outbound['nodes'])
    with pytest.raises(ValueError):m.render(config,'http://8.8.8.8:8767','separate-planning-token')
    with pytest.raises(ValueError):m.render(config,'http://172.19.0.1:8767',config['credentials']['runtime_header'])


def test_generated_planning_dispatch_code_compiles(config):
    node=shutil.which('node')
    if not node and os.environ.get('SHRR_NODE_DOCKER')!='1':pytest.skip('Node required')
    result=m.render(config,'http://172.19.0.1:8767','separate-planning-token')
    scripts=[n['parameters']['jsCode'] for w in result['workflows'].values() for n in w['nodes'] if n['type'].endswith('.code')]
    program='const a='+json.dumps(scripts)+'; for(const s of a)new Function("$input","$",s);'
    command=[node,'-e',program] if node else ['docker','exec','-i','n8n','node','-e',program]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
