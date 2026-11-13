import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
from test_reporting_n8n_codex import config,uid

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/n8n_hermes_planning_reader.py'
spec=importlib.util.spec_from_file_location('jarvis_reader_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
NODE=Path(__file__).resolve().parents[3]/'project-test-venv/lib/python3.13/site-packages/playwright/driver/node'


@pytest.mark.parametrize('issue',[False,True])
def test_inactive_reader_uses_exact_run_and_jarvis_credential(config,issue):
    scope=dict(kind='non_git',id='jarvis-non-git')
    workflow=module.render(config,'private-reader',[uid(30)],[scope],{},scope,'jarvis-oauth',issue)
    assert workflow['active'] is False
    nodes={n['name']:n for n in workflow['nodes']}
    assert 'webhook_receipts' in nodes['Read retained planning event']['parameters']['query']
    assert nodes['Read native planning origin']['credentials']['oAuth2Api']['id']=='jarvis-oauth'
    assert nodes['Private planning origin']['parameters']['path'].startswith('rras-jarvis-planning-')
    if issue:assert 'Verify Jarvis issue' in nodes
    scripts=[n['parameters']['jsCode'] for n in workflow['nodes'] if n['type'].endswith('.code')]
    if not NODE.is_file():pytest.skip('Node runtime unavailable')
    result=subprocess.run([str(NODE),'-e','for(const s of '+json.dumps(scripts)+') new Function("$input","$",s)'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_jarvis_must_have_separate_credential(config):
    scope=dict(kind='non_git',id='jarvis-non-git')
    with pytest.raises(ValueError):
        module.render(config,'private-reader',[uid(30)],[scope],{},scope,config['credentials']['codex_oauth'])


def test_retained_payload_must_match_active_run_and_issue():
    if not NODE.is_file():pytest.skip('Node runtime unavailable')
    org,session,issue,delivery=map(uid,[1,2,3,4])
    native=dict(organization_id=org,session_id=session,hermes_session_id='linear:'+org+':'+session,run_id='run_'+'a'*32)
    row=dict(hermes_run_id=native['run_id'],status='running',organization_id=org,receipt_organization_id=org,
        agent_session_id=session,receipt_session_id=session,hermes_session_id=native['hermes_session_id'],
        event_type='AgentSessionEvent',action='prompted',delivery_id=delivery,issue_id=issue,
        raw_payload=dict(action='prompted',agentSession=dict(id=session,issueId=issue),agentActivity=dict(userId=uid(5))))
    source=path.with_name('n8n_hermes_planning_receipt.js').read_text()
    script=source+'\nconst n='+json.dumps(native)+',r='+json.dumps(row)+""";
if(hermesPlanningEnvelope(n,r).source_actor_id!=="""+json.dumps(uid(5))+""")throw Error('actor lost');
r.raw_payload.agentSession.issueId='wrong';
let rejected=false;try { hermesPlanningEnvelope(n,r); } catch(e) { rejected=true; }
if(!rejected)throw Error('mismatched issue accepted');"""
    result=subprocess.run([str(NODE),'-e',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
