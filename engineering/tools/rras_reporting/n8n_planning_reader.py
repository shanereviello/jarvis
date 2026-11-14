"""Render an inactive, authenticated native-origin reader for planning."""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('planning_reader_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration,reader_header,team_ids,scopes,project_scopes,fallback_scope):
    config=local('n8n_codex').configuration(configuration);d=local('onboarding_drafts')
    if type(reader_header) is not str or not reader_header.strip() or len(reader_header)>128 or reader_header in config['credentials'].values():
        raise ValueError('separate planning-reader credential reference required')
    if type(team_ids) is not list or not team_ids or len(team_ids)>128 or len(set(team_ids))!=len(team_ids):
        raise ValueError('explicit team grants required')
    for team in team_ids:d.identifier(team)
    if type(scopes) is not list or not scopes or len(scopes)>128:raise ValueError('explicit scope grants required')
    selected=[d.selected_scope(scope) for scope in scopes]
    if type(project_scopes) is not dict or len(project_scopes)>4096:raise ValueError('bounded explicit project scopes required')
    mapped={}
    for project,scope in project_scopes.items():
        d.identifier(project);scope=d.selected_scope(scope)
        if scope not in selected:raise ValueError('project scope outside grant')
        mapped[project]=scope
    if fallback_scope is not None:
        fallback_scope=d.selected_scope(fallback_scope)
        if fallback_scope not in selected or fallback_scope['kind']!='non_git':raise ValueError('explicit non-Git fallback required')
    org=config['organization_id'];app=config['app_user_id'];agents=config['agent_actor_ids']
    if len(agents)!=2 or agents.count(app)!=1:raise ValueError('distinct agent identities required')
    other=next(actor for actor in agents if actor!=app)
    policy=dict(organization_id=org,agents=dict(codex=app,jarvis=other),team_ids=team_ids,scopes=selected)
    nodes=[]
    def node(name,kind,version,parameters,credential=None):
        value=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:planning-origin:'+app+':'+name)),name=name,
            type='n8n-nodes-base.'+kind,typeVersion=version,position=[240*len(nodes),0],parameters=parameters)
        if kind=='webhook':value['webhookId']=value['id']
        if credential:value['credentials']={credential[0]:dict(id=credential[1],name='Protected planning credential reference')}
        nodes.append(value);return value
    node('Private planning origin','webhook',2.1,dict(httpMethod='POST',path='rras-planning-origin-'+app,
        responseMode='responseNode',authentication='headerAuth',options={}),('httpHeaderAuth',reader_header))
    node('Validate exact dispatch','code',2,dict(mode='runOnceForAllItems',jsCode="""const b=$input.first().json.body;
if(!b||Object.keys(b).sort().join()!=='dispatch_id'||typeof b.dispatch_id!=='string'||
 !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(b.dispatch_id))throw new Error('Exact dispatch required');
return [{json:{dispatch_id:b.dispatch_id}}];"""))
    query=f"SELECT id,envelope FROM linear_bridge.codex_planning_events WHERE organization_id='{org}'::uuid AND app_user_id='{app}'::uuid AND id=$1::uuid AND state IN ('dispatching','running')"
    node('Read retained planning event','postgres',2.6,dict(operation='executeQuery',query=query,
        options=dict(queryReplacement='={{ [$json.dispatch_id] }}')),('postgres',config['credentials']['postgres']))
    source=(Path(__file__).with_name('n8n_planning_origin.js')).read_text()
    prepare=source+'\nconst app='+json.dumps(app)+""";
const row=$input.first().json;if(!row.id||row.envelope?.contract!=='codex-planning-event.v1')throw new Error('Retained planning event required');
return [{json:{...row,native_request:planningOriginQuery(row.envelope,{app_user_id:app})}}];"""
    node('Prepare native planning read','code',2,dict(mode='runOnceForAllItems',jsCode=prepare))
    native=node('Read native planning origin','httpRequest',4.2,dict(method='POST',url='https://api.linear.app/graphql',
        authentication='genericCredentialType',genericAuthType='oAuth2Api',sendBody=True,contentType='raw',rawContentType='application/json',
        body='={{ JSON.stringify($json.native_request) }}',options=dict(timeout=15000,response=dict(response=dict(fullResponse=True,neverError=True)))),
        ('oAuth2Api',config['credentials']['codex_oauth']))
    native.update(onError='continueRegularOutput',retryOnFail=False)
    assess=source+'\nconst policy='+json.dumps(policy)+';\nconst mapped='+json.dumps(mapped)+';\nconst fallback='+json.dumps(fallback_scope)+""";
const saved=$('Prepare native planning read').first().json,reply=$input.first().json;
const project=reply.body?.data?.agentSession?.issue?.project?.id;
const scope=Object.hasOwn(mapped,project)?mapped[project]:fallback;
if(!scope)return [{json:{permitted:false}}];
const resolution={organization_id:policy.organization_id,project_id:project,scope};
const result=verifyPlanningOrigin({...saved.envelope,agent:'codex'},reply,policy,resolution);
return [{json:result.permitted?{contract:'codex-planning-origin.v1',dispatch_id:saved.id,issue_id:saved.envelope.issue_id,message:saved.envelope.message,signal:saved.envelope.signal??null,...result}:{permitted:false}}];"""
    node('Verify selected planning origin','code',2,dict(mode='runOnceForAllItems',jsCode=assess))
    node('Respond with verified origin','respondToWebhook',1.4,dict(respondWith='json',responseBody='={{ $json }}',options=dict(responseCode=200)))
    connections={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    return dict(name='Codex verified planning origin reader (inactive)',active=False,nodes=nodes,connections=connections,
        settings=dict(executionOrder='v1',saveDataErrorExecution='none',saveDataSuccessExecution='none',saveManualExecutions=False,executionTimeout=30),tags=[],pinData={})
