import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from test_reporting_n8n_codex import config, uid

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/n8n_operator_issue_reader.py'
spec = importlib.util.spec_from_file_location('operator_issue_reader_fixture', path)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_issue_workflow_is_inactive_scoped_and_does_not_retry(config):
    workflow = module.render(config, 'private-issue-header', [uid(30)])
    nodes = {item['name']:item for item in workflow['nodes']}
    assert not workflow['active'] and nodes['Read native issue']['retryOnFail'] is False
    assert workflow['settings']['saveDataSuccessExecution'] == 'none'
    with pytest.raises(ValueError):module.render(config, config['credentials']['runtime_header'], [uid(30)])


def test_issue_workflow_checks_native_team_and_identity(config):
    node = shutil.which('node')
    if node is None and os.environ.get('SHRR_NODE_DOCKER') != '1':pytest.skip('Node required')
    workflow = module.render(config, 'private-issue-header', [uid(30)])
    scripts = [x['parameters']['jsCode'] for x in workflow['nodes'] if x['type'].endswith('.code')]
    reply = {'statusCode':200,'body':{'data':{'viewer':{'id':config['app_user_id'],
        'organization':{'id':config['organization_id']}},'issue':{'id':uid(32),'team':{'id':uid(30)},'project':{'id':uid(34)}}}}}
    program = '''const scripts=SCRIPTS;for(const s of scripts)new Function('$input','$',s);
const fn=new Function('$input','$',scripts[1]),reply=REPLY;
const input={first:()=>({json:reply})},saved=()=>({first:()=>({json:{issue_id:ID}})});
if(!fn(input,saved)[0].json.permitted)throw Error('valid issue refused');
reply.body.data.issue.team.id=OTHER;if(fn(input,saved)[0].json.permitted)throw Error('wrong team accepted');'''
    for key,value in [('SCRIPTS',scripts),('REPLY',reply),('ID',uid(32)),('OTHER',uid(31))]:
        program = program.replace(key,json.dumps(value))
    command = [node,'-e',program] if node else ['docker','exec','-i','n8n','node','-e',program]
    result = subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr
