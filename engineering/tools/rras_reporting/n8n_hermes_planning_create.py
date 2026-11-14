"""Render an inactive, non-retrying Jarvis draft issue creator."""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_planning_create_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration,creator_header,team_ids,scopes,project_scopes,fallback_scope,jarvis_oauth):
    config=local('n8n_codex').configuration(configuration);app=config['app_user_id']
    workflow=local('n8n_hermes_planning_reader').render(config,creator_header,team_ids,scopes,project_scopes,fallback_scope,jarvis_oauth,issue=True)
    nodes=workflow['nodes'];named={n['name']:n for n in nodes}
    named['Private planning origin']['parameters']['path']='rras-jarvis-planning-create-'+app
    validate=named['Validate exact dispatch']['parameters']['jsCode']
    validate=validate.replace('issue_id,native','native,plan_id,proposal').replace('(true&&!uuid(b.issue_id))',"(typeof b.plan_id!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/.test(b.plan_id)||!b.proposal||Object.keys(b.proposal).sort().join()!=='description,title'||typeof b.proposal.title!=='string'||!b.proposal.title.trim()||b.proposal.title.length>200||typeof b.proposal.description!=='string'||!b.proposal.description.trim()||b.proposal.description.length>20000)")
    named['Validate exact dispatch']['parameters']['jsCode']=validate
    # Keep the independently verified origin, but replace issue lookup with one
    # non-retrying mutation. The host's journal owns create-once coordination.
    nodes[:]=[n for n in nodes if n['name'] not in ('Prepare Jarvis issue read','Read Jarvis issue','Verify Jarvis issue')]
    mutation='mutation PlanningIssueCreate($input:IssueCreateInput!){issueCreate(input:$input){success issue{id}}}'
    prepare="""const v=$input.first().json,b=$('Validate exact dispatch').first().json;
if(v.permitted!==true||!v.origin||!b.proposal.title.startsWith(b.plan_id+': ')||
 !b.proposal.description.includes('<!-- rras-draft-work:'))throw new Error('Verified origin and exact plan required');
return [{json:{native:b.native,request:{query:MUTATION,variables:{input:{teamId:v.origin.team_id,projectId:v.origin.project_id,
 title:b.proposal.title,description:b.proposal.description}}}}}];""".replace('MUTATION',json.dumps(mutation))
    assess="""const saved=$('Prepare Jarvis draft issue').first().json,reply=$input.first().json,result=reply.body?.data?.issueCreate;
const ok=reply.statusCode===200&&!reply.body?.errors&&result?.success===true&&typeof result.issue?.id==='string'&&
 /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(result.issue.id);
return [{json:ok?{contract:'hermes-planning-create.v1',native:saved.native,created:true,issue_id:result.issue.id}:{created:false}}];"""
    def code(name,js):return dict(name=name,type='n8n-nodes-base.code',typeVersion=2,parameters=dict(mode='runOnceForAllItems',jsCode=js))
    native=json.loads(json.dumps(named['Read native planning origin']));native['name']='Create Jarvis draft issue';native['parameters']['body']='={{ JSON.stringify($json.request) }}'
    nodes[-1:-1]=[code('Prepare Jarvis draft issue',prepare),native,code('Assess Jarvis draft issue',assess)]
    for i,node in enumerate(nodes):
        node['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:jarvis-create:'+app+':'+node['name']));node['position']=[240*i,0]
        if node['type'].endswith('.webhook'):node['webhookId']=node['id']
    workflow['connections']={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    workflow['name']='Jarvis draft issue creator (inactive)'
    return workflow
