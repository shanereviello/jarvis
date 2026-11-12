"""Render an inactive app-attributed draft issue creator; never retries."""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('planning_issue_create_workflow_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration,creator_header,team_ids,scopes,project_scopes,fallback_scope):
    config=local('n8n_codex').configuration(configuration)
    workflow=local('n8n_planning_reader').render(config,creator_header,team_ids,scopes,project_scopes,fallback_scope)
    nodes=workflow['nodes'];named={node['name']:node for node in nodes};app=config['app_user_id']
    named['Private planning origin']['parameters']['path']='rras-planning-create-'+app
    named['Validate exact dispatch']['parameters']['jsCode']="""const b=$input.first().json.body;
const uuid=x=>typeof x==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(x);
if(!b||Object.keys(b).sort().join()!=='dispatch_id,plan_id,proposal'||!uuid(b.dispatch_id)||
 typeof b.plan_id!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/.test(b.plan_id)||
 !b.proposal||Object.keys(b.proposal).sort().join()!=='description,title'||typeof b.proposal.title!=='string'||
 !b.proposal.title.trim()||b.proposal.title.length>200||typeof b.proposal.description!=='string'||
 !b.proposal.description.trim()||b.proposal.description.length>20000)throw new Error('Bounded draft issue required');
return [{json:b}];"""
    mutation='mutation PlanningIssueCreate($input:IssueCreateInput!){issueCreate(input:$input){success issue{id}}}'
    prepare="""const verified=$input.first().json,request=$('Validate exact dispatch').first().json;
if(!verified.permitted||!verified.origin||verified.dispatch_id!==request.dispatch_id||![null,'continue'].includes(verified.signal))throw new Error('Verified planning origin required');
const expected=request.plan_id+': ';
if(!request.proposal.title.startsWith(expected)||!request.proposal.description.includes('<!-- rras-draft-work:'))throw new Error('Exact plan marker required');
return [{json:{dispatch_id:request.dispatch_id,request:{query:MUTATION,variables:{input:{teamId:verified.origin.team_id,
 projectId:verified.origin.project_id,title:request.proposal.title,description:request.proposal.description}}}}}];""".replace('MUTATION',json.dumps(mutation))
    assess="""const saved=$('Prepare draft issue create').first().json,reply=$input.first().json;
const issue=reply.body?.data?.issueCreate;
const valid=reply.statusCode===200&&!reply.body?.errors&&issue?.success===true&&
 typeof issue.issue?.id==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(issue.issue.id);
return [{json:valid?{contract:'codex-planning-create.v1',dispatch_id:saved.dispatch_id,created:true,issue_id:issue.issue.id}:{created:false}}];"""
    def code(name,text):return dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:planning-create:'+app+':'+name)),name=name,
        type='n8n-nodes-base.code',typeVersion=2,position=[0,0],parameters=dict(mode='runOnceForAllItems',jsCode=text))
    native=json.loads(json.dumps(named['Read native planning origin']));native['name']='Create native draft issue'
    native['parameters']['body']='={{ JSON.stringify($json.request) }}'
    nodes[-1:-1]=[code('Prepare draft issue create',prepare),native,code('Assess draft issue create',assess)]
    for i,node in enumerate(nodes):
        node['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:planning-create:'+app+':'+node['name']))
        node['position']=[240*i,0]
        if node['type'].endswith('.webhook'):node['webhookId']=node['id']
    workflow['connections']={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    workflow['name']='Codex draft issue creator (inactive)'
    return workflow
