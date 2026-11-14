"""Render an inactive private reader for a proposed Linear issue."""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('planning_issue_reader_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration,reader_header,team_ids,scopes,project_scopes,fallback_scope):
    config=local('n8n_codex').configuration(configuration)
    workflow=local('n8n_planning_reader').render(config,reader_header,team_ids,scopes,project_scopes,fallback_scope)
    nodes=workflow['nodes'];named={node['name']:node for node in nodes}
    named['Private planning origin']['parameters']['path']='rras-planning-issue-'+config['app_user_id']
    named['Validate exact dispatch']['parameters']['jsCode']="""const b=$input.first().json.body;
const uuid=x=>typeof x==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(x);
if(!b||Object.keys(b).sort().join()!=='dispatch_id,issue_id'||!uuid(b.dispatch_id)||!uuid(b.issue_id))throw new Error('Exact dispatch and issue required');
return [{json:{dispatch_id:b.dispatch_id,issue_id:b.issue_id}}];"""
    source=Path(__file__).with_name('n8n_planning_origin.js').read_text()
    prepare=source+"""\nconst verified=$input.first().json,requested=$('Validate exact dispatch').first().json;
if(!verified.permitted||!verified.origin||verified.dispatch_id!==requested.dispatch_id)throw new Error('Verified planning origin required');
return [{json:{origin:verified.origin,dispatch_id:requested.dispatch_id,issue_id:requested.issue_id,native_request:planningIssueQuery(requested.issue_id)}}];"""
    app=config['app_user_id'];other=next(actor for actor in config['agent_actor_ids'] if actor!=app)
    policy=dict(organization_id=config['organization_id'],agents=dict(codex=app,jarvis=other))
    assess=source+'\nconst policy='+json.dumps(policy)+""";
const saved=$('Prepare native issue read').first().json,reply=$input.first().json;
const result=verifyPlanningIssue(saved.origin,saved.issue_id,reply,policy);
return [{json:result.permitted?{contract:'codex-planning-issue.v1',dispatch_id:saved.dispatch_id,origin:saved.origin,...result}:{permitted:false}}];"""
    def code(name,text):return dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:planning-issue:'+app+':'+name)),name=name,
        type='n8n-nodes-base.code',typeVersion=2,position=[0,0],parameters=dict(mode='runOnceForAllItems',jsCode=text))
    native=json.loads(json.dumps(named['Read native planning origin']))
    native['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:planning-issue:'+app+':native-read'))
    native['name']='Read native issue';native['parameters']['body']='={{ JSON.stringify($json.native_request) }}'
    nodes[-1:-1]=[code('Prepare native issue read',prepare),native,code('Verify native planning issue',assess)]
    for i,node in enumerate(nodes):
        node['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:planning-issue:'+app+':'+node['name']))
        node['position']=[240*i,0]
        if node['type'].endswith('.webhook'):node['webhookId']=node['id']
    workflow['connections']={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    workflow['name']='Codex verified planning issue reader (inactive)'
    return workflow
