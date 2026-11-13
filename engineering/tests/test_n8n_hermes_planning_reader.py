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
    workflow=module.render(config,'private-reader',[uid(30)],[scope],{},scope,dict(id='jarvis-oauth',type='linearOAuth2Api'),issue)
    assert workflow['active'] is False
    nodes={n['name']:n for n in workflow['nodes']}
    assert 'webhook_receipts' in nodes['Read retained planning event']['parameters']['query']
    assert nodes['Read native planning origin']['credentials']['linearOAuth2Api']['id']=='jarvis-oauth'
    assert nodes['Read native planning origin']['parameters']['authentication']=='predefinedCredentialType'
    assert nodes['Read native planning origin']['parameters']['nodeCredentialType']=='linearOAuth2Api'
    assert nodes['Private planning origin']['parameters']['path'].startswith('rras-jarvis-planning-')
    if issue:assert 'Verify Jarvis issue' in nodes
    scripts=[n['parameters']['jsCode'] for n in workflow['nodes'] if n['type'].endswith('.code')]
    if not NODE.is_file():pytest.skip('Node runtime unavailable')
    result=subprocess.run([str(NODE),'-e','for(const s of '+json.dumps(scripts)+') new Function("$input","$",s)'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_jarvis_must_have_separate_credential(config):
    scope=dict(kind='non_git',id='jarvis-non-git')
    with pytest.raises(ValueError):
        module.render(config,'private-reader',[uid(30)],[scope],{},scope,dict(id=config['credentials']['codex_oauth'],type='oAuth2Api'))
    workflow=module.render(config,'private-reader',[uid(30)],[scope],{},scope,dict(id='other-jarvis',type='oAuth2Api'))
    native=next(n for n in workflow['nodes'] if n['name']=='Read native planning origin')
    assert native['parameters']['authentication']=='genericCredentialType' and native['parameters']['genericAuthType']=='oAuth2Api'


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


def test_origin_workflow_rechecks_human_source_against_linear(config):
    if not NODE.is_file():pytest.skip('Node runtime unavailable')
    scope=dict(kind='non_git',id='jarvis-non-git')
    workflow=module.render(config,'private-reader',[uid(30)],[scope],{},scope,dict(id='jarvis-oauth',type='linearOAuth2Api'))
    scripts={n['name']:n['parameters']['jsCode'] for n in workflow['nodes'] if n['type'].endswith('.code')}
    app=config['app_user_id'];org=config['organization_id'];session=uid(2);issue=uid(3);comment=uid(4);human=uid(5);project=uid(6)
    native=dict(organization_id=org,session_id=session,hermes_session_id='linear:'+org+':'+session,run_id='run_'+'a'*32)
    row=dict(hermes_run_id=native['run_id'],status='running',organization_id=org,receipt_organization_id=org,
        agent_session_id=session,receipt_session_id=session,hermes_session_id=native['hermes_session_id'],
        event_type='AgentSessionEvent',action='created',delivery_id=uid(7),issue_id=issue,
        raw_payload=dict(action='created',agentSession=dict(id=session,issueId=issue,sourceCommentId=comment)))
    reply=dict(statusCode=200,body=dict(data=dict(viewer=dict(id=app,organization=dict(id=org)),
        agentSession=dict(id=session,appUser=dict(id=app),issue=dict(id=issue,team=dict(id=uid(30)),
        project=dict(id=project,url='https://linear.app/test/project/example')),sourceComment=dict(id=comment,user=dict(id=human,app=False))))))
    program="""const scripts=__S__,native=__N__,row=__R__,reply=__L__;
const call=(name,current,saved)=>new Function('$input','$',scripts[name])({first:()=>({json:current}),all:()=>[{json:current}]},name=>({first:()=>({json:saved[name]})}))[0].json;
const prepared=call('Prepare native planning read',row,{'Validate exact dispatch':{native}});
const result=call('Verify selected planning origin',reply,{'Prepare native planning read':prepared});
if(result.contract!=='hermes-planning-origin.v1'||result.origin.source_actor!==__H__||result.source_verified!==true)throw Error('verified origin missing');
reply.body.data.agentSession.sourceComment.user.app=true;
const denied=call('Verify selected planning origin',reply,{'Prepare native planning read':prepared});
if(denied.permitted!==false)throw Error('app actor accepted');"""
    for key,value in [('S',scripts),('N',native),('R',row),('L',reply),('H',human)]:
        program=program.replace('__'+key+'__',json.dumps(value))
    result=subprocess.run([str(NODE),'-e',program],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_jarvis_create_workflow_compiles_and_does_not_retry(config):
    if not NODE.is_file():pytest.skip('Node runtime unavailable')
    scope=dict(kind='non_git',id='jarvis-non-git')
    create=module.local('n8n_hermes_planning_create')
    workflow=create.render(config,'creator-header',[uid(30)],[scope],{},scope,dict(id='jarvis-oauth',type='linearOAuth2Api'))
    nodes={n['name']:n for n in workflow['nodes']}
    assert not workflow['active'] and nodes['Create Jarvis draft issue']['retryOnFail'] is False
    assert nodes['Create Jarvis draft issue']['credentials']['linearOAuth2Api']['id']=='jarvis-oauth'
    assert 'issue_id' not in nodes['Validate exact dispatch']['parameters']['jsCode']
    scripts=[n['parameters']['jsCode'] for n in workflow['nodes'] if n['type'].endswith('.code')]
    result=subprocess.run([str(NODE),'-e','for(const s of '+json.dumps(scripts)+') new Function("$input","$",s)'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    org=config['organization_id'];session=uid(2)
    native=dict(organization_id=org,session_id=session,hermes_session_id='linear:'+org+':'+session,run_id='run_'+'a'*32)
    body=dict(native=native,plan_id='PLAN-1',proposal=dict(title='PLAN-1: Example',description='Draft'))
    code=nodes['Validate exact dispatch']['parameters']['jsCode']
    program='const f=new Function("$input","$",'+json.dumps(code)+'); const b='+json.dumps(body)+'; if(f({first:()=>({json:{body:b}})},null)[0].json.plan_id!=="PLAN-1")throw Error("valid request refused"); b.plan_id="../bad"; let refused=false;try{f({first:()=>({json:{body:b}})},null)}catch(e){refused=true}if(!refused)throw Error("bad plan accepted");'
    result=subprocess.run([str(NODE),'-e',program],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
