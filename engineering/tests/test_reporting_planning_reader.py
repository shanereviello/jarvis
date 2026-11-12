import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from test_reporting_n8n_codex import config,uid

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/n8n_planning_reader.py'
spec=importlib.util.spec_from_file_location('planning_reader_fixture',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec=importlib.util.spec_from_file_location('planning_issue_reader_fixture',path.with_name('n8n_planning_issue_reader.py'))
issues=importlib.util.module_from_spec(spec);spec.loader.exec_module(issues)
spec=importlib.util.spec_from_file_location('planning_issue_create_fixture',path.with_name('n8n_planning_issue_create.py'))
create=importlib.util.module_from_spec(spec);spec.loader.exec_module(create)


def test_inactive_reader_requires_fixed_scope_and_private_credentials(config):
    scope=dict(kind='non_git',id='jarvis-non-git')
    workflow=m.render(config,'distinct-reader',[uid(30)],[scope],{},scope)
    assert not workflow['active'] and workflow['settings']['saveDataSuccessExecution']=='none'
    names={node['name']:node for node in workflow['nodes']}
    assert names['Private planning origin']['parameters']['authentication']=='headerAuth'
    assert 'codex_planning_events' in names['Read retained planning event']['parameters']['query']
    assert names['Read native planning origin']['retryOnFail'] is False
    with pytest.raises(ValueError):m.render(config,config['credentials']['runtime_header'],[uid(30)],[scope],{},scope)
    with pytest.raises(ValueError):m.render(config,'distinct-reader',[uid(30)],[scope],{},dict(kind='repository',id='other'))


def test_generated_reader_code_compiles_in_n8n(config):
    node=shutil.which('node')
    if not node and os.environ.get('SHRR_NODE_DOCKER')!='1':pytest.skip('Node required')
    scope=dict(kind='non_git',id='jarvis-non-git');workflow=m.render(config,'distinct-reader',[uid(30)],[scope],{},scope)
    scripts=[n['parameters']['jsCode'] for n in workflow['nodes'] if n['type'].endswith('.code')]
    program='const a='+json.dumps(scripts)+'; for(const s of a)new Function("$input","$",s);'
    command=[node,'-e',program] if node else ['docker','exec','-i','n8n','node','-e',program]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr


def test_generated_issue_reader_rechecks_origin_and_issue(config):
    node=shutil.which('node')
    if not node and os.environ.get('SHRR_NODE_DOCKER')!='1':pytest.skip('Node required')
    scope=dict(kind='non_git',id='jarvis-non-git')
    workflow=issues.render(config,'distinct-reader',[uid(30)],[scope],{},scope)
    names=[n['name'] for n in workflow['nodes']]
    assert names.index('Verify selected planning origin')<names.index('Read native issue')<names.index('Verify native planning issue')
    scripts=[n['parameters']['jsCode'] for n in workflow['nodes'] if n['type'].endswith('.code')]
    program='const a='+json.dumps(scripts)+'; for(const s of a)new Function("$input","$",s);'
    command=[node,'-e',program] if node else ['docker','exec','-i','n8n','node','-e',program]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr


def test_inactive_issue_creator_has_one_nonretrying_mutation(config):
    node=shutil.which('node')
    if not node and os.environ.get('SHRR_NODE_DOCKER')!='1':pytest.skip('Node required')
    scope=dict(kind='non_git',id='jarvis-non-git')
    workflow=create.render(config,'separate-creator',[uid(30)],[scope],{},scope)
    assert not workflow['active']
    native=next(n for n in workflow['nodes'] if n['name']=='Create native draft issue')
    assert native['retryOnFail'] is False
    scripts=[n['parameters']['jsCode'] for n in workflow['nodes'] if n['type'].endswith('.code')]
    program='const a='+json.dumps(scripts)+'; for(const s of a)new Function("$input","$",s);'
    command=[node,'-e',program] if node else ['docker','exec','-i','n8n','node','-e',program]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
