"""Render inactive Jarvis planning readers using retained native deliveries."""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('jarvis_reader_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration,reader_header,team_ids,scopes,project_scopes,fallback_scope,jarvis_oauth,issue=False):
    config=local('n8n_codex').configuration(configuration)
    if type(jarvis_oauth) is not str or not jarvis_oauth.strip() or jarvis_oauth==config['credentials']['codex_oauth']:
        raise ValueError('separate Jarvis OAuth credential reference required')
    workflow=local('n8n_planning_reader').render(config,reader_header,team_ids,scopes,project_scopes,fallback_scope)
    nodes=workflow['nodes'];named={n['name']:n for n in nodes}
    app=config['app_user_id'];other=next(x for x in config['agent_actor_ids'] if x!=app)
    policy=dict(organization_id=config['organization_id'],agents=dict(jarvis=app,codex=other),team_ids=team_ids,scopes=scopes)
    kind='issue' if issue else 'origin'
    named['Private planning origin']['parameters']['path']='rras-jarvis-planning-'+kind+'-'+app
    named['Validate exact dispatch']['parameters']['jsCode']="""const b=$input.first().json.body,n=b?.native;
const uuid=x=>typeof x==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(x);
if(!b||Object.keys(b).sort().join()!==FIELDS||!n||Object.keys(n).sort().join()!=='hermes_session_id,organization_id,run_id,session_id'||
 n.organization_id!==ORG||!uuid(n.session_id)||!/^run_[0-9a-f]{32}$/.test(n.run_id)||
 n.hermes_session_id!=='linear:'+n.organization_id+':'+n.session_id|| (ISSUE&&!uuid(b.issue_id))) throw new Error('Exact native run required');
return [{json:b}];""".replace('FIELDS',json.dumps('issue_id,native' if issue else 'native')).replace('ORG',json.dumps(config['organization_id'])).replace('ISSUE','true' if issue else 'false')
    named['Read retained planning event']['parameters']['query']=local('hermes_planning_receipt').QUERY
    named['Read retained planning event']['parameters']['options']['queryReplacement']='={{ [$json.native.run_id,$json.native.organization_id,$json.native.session_id,$json.native.hermes_session_id] }}'
    source=Path(__file__).with_name('n8n_planning_origin.js').read_text()
    receipt=Path(__file__).with_name('n8n_hermes_planning_receipt.js').read_text()
    named['Prepare native planning read']['parameters']['jsCode']=source+'\n'+receipt+'\nconst app='+json.dumps(app)+""";
const native=$('Validate exact dispatch').first().json.native,rows=$input.all();
if(rows.length!==1)throw new Error('One exact receipt required');
const envelope=hermesPlanningEnvelope(native,rows[0].json);
return [{json:{native,envelope,native_request:planningOriginQuery(envelope,{app_user_id:app})}}];"""
    named['Read native planning origin']['credentials']={'oAuth2Api':dict(id=jarvis_oauth,name='Protected Jarvis OAuth reference')}
    named['Verify selected planning origin']['parameters']['jsCode']=source+'\nconst policy='+json.dumps(policy)+';\nconst mapped='+json.dumps(project_scopes)+';\nconst fallback='+json.dumps(fallback_scope)+""";
const saved=$('Prepare native planning read').first().json,reply=$input.first().json;
const project=reply.body?.data?.agentSession?.issue?.project?.id;
const scope=Object.hasOwn(mapped,project)?mapped[project]:fallback;
if(!scope)return [{json:{permitted:false}}];
const result=verifyPlanningOrigin(saved.envelope,reply,policy,{organization_id:policy.organization_id,project_id:project,scope});
return [{json:result.permitted?{contract:'hermes-planning-origin.v1',native:saved.native,app_user_id:policy.agents.jarvis,
 active:true,source_verified:true,origin:result.origin,permitted:true}:{permitted:false}}];"""
    # Origin consumers expect an exact fixed response, with no extra permitted field.
    if not issue:
        named['Verify selected planning origin']['parameters']['jsCode']=named['Verify selected planning origin']['parameters']['jsCode'].replace(',permitted:true}', '}')
    else:
        prepare=source+"""\nconst v=$input.first().json,b=$('Validate exact dispatch').first().json;
if(v.permitted!==true||!v.origin)throw new Error('Verified origin required');
return [{json:{native:v.native,origin:v.origin,issue_id:b.issue_id,native_request:planningIssueQuery(b.issue_id)}}];"""
        assess=source+'\nconst policy='+json.dumps(policy)+""";
const saved=$('Prepare Jarvis issue read').first().json,result=verifyPlanningIssue(saved.origin,saved.issue_id,$input.first().json,policy);
return [{json:result.permitted?{contract:'hermes-planning-issue.v1',native:saved.native,origin:saved.origin,issue:result.issue,permitted:true}:{permitted:false}}];"""
        def code(name,js):return dict(name=name,type='n8n-nodes-base.code',typeVersion=2,position=[0,0],parameters=dict(mode='runOnceForAllItems',jsCode=js))
        native=json.loads(json.dumps(named['Read native planning origin']));native['name']='Read Jarvis issue'
        nodes[-1:-1]=[code('Prepare Jarvis issue read',prepare),native,code('Verify Jarvis issue',assess)]
    for i,node in enumerate(nodes):
        node['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:jarvis-planning:'+kind+':'+app+':'+node['name']))
        node['position']=[240*i,0]
        if node['type'].endswith('.webhook'):node['webhookId']=node['id']
    workflow['connections']={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    workflow['name']='Jarvis verified planning '+kind+' reader (inactive)'
    return workflow
