"""Render an inactive private, read-only Linear decision comment reader."""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('operator_comment_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration,operator_header,team_ids,human_ids):
    c=local('n8n_codex').configuration(configuration);d=local('onboarding_drafts')
    if (type(operator_header) is not str or not operator_header.strip() or len(operator_header)>128 or
            operator_header in c['credentials'].values()):raise ValueError('separate operator reader credential required')
    for values in (team_ids,human_ids):
        if type(values) is not list or not values or len(values)>128 or len(set(values))!=len(values):raise ValueError('bounded identity grants required')
        for item in values:d.identifier(item)
    if any(item in c['agent_actor_ids'] for item in human_ids):raise ValueError('human and agent identities must differ')
    app,org=c['app_user_id'],c['organization_id'];nodes=[]
    def node(name,kind,version,parameters,credential=None):
        obj=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:operator-comment:'+app+':'+name)),name=name,
                 type='n8n-nodes-base.'+kind,typeVersion=version,position=[len(nodes)*240,0],parameters=parameters)
        if kind=='webhook':obj['webhookId']=obj['id']
        if credential:obj['credentials']={credential[0]:dict(id=credential[1],name='Protected operator credential reference')}
        nodes.append(obj);return obj
    node('Private operator comment','webhook',2.1,dict(httpMethod='POST',path='rras-operator-comment-'+app,
        responseMode='responseNode',authentication='headerAuth',options={}),('httpHeaderAuth',operator_header))
    query=local('onboarding_linear_comment_reader').QUERY
    node('Prepare exact comment read','code',2,dict(mode='runOnceForAllItems',jsCode="""const b=$input.first().json.body;
if(!b||Object.keys(b).sort().join()!=='comment_id'||typeof b.comment_id!=='string'||
 !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(b.comment_id))throw new Error('Exact comment required');
return [{json:{comment_id:b.comment_id,native_request:{query:QUERY,variables:{id:b.comment_id}}}}];""".replace('QUERY',json.dumps(query))))
    native=node('Read native comment','httpRequest',4.2,dict(method='POST',url='https://api.linear.app/graphql',
        authentication='genericCredentialType',genericAuthType='oAuth2Api',sendBody=True,contentType='raw',rawContentType='application/json',
        body='={{ JSON.stringify($json.native_request) }}',options=dict(timeout=15000,response=dict(response=dict(fullResponse=True,neverError=True)))),
        ('oAuth2Api',c['credentials']['codex_oauth']))
    native.update(onError='continueRegularOutput',retryOnFail=False)
    js="""const expected=$('Prepare exact comment read').first().json,reply=$input.first().json,data=reply.body?.data;
const viewer=data?.viewer,comment=data?.comment,issue=comment?.issue;
const has=(o,k)=>o!==null&&typeof o==='object'&&Object.hasOwn(o,k);
if(reply.statusCode!==200||reply.body?.errors||viewer?.id!==APP||viewer?.organization?.id!==ORG||
 comment?.id!==expected.comment_id||!HUMANS.includes(comment?.user?.id)||comment?.user?.app!==false||
 !TEAMS.includes(issue?.team?.id)||!issue?.project?.id||
 !['id','body','createdAt','editedAt','archivedAt','botActor','externalUser','onBehalfOf','user','issue'].every(k=>has(comment,k))||
 comment.editedAt!==null||comment.archivedAt!==null||comment.botActor!==null||comment.externalUser!==null||comment.onBehalfOf!==null)
 return [{json:{permitted:false}}];
return [{json:{permitted:true,data}}];"""
    for key,val in [('APP',app),('ORG',org),('HUMANS',human_ids),('TEAMS',team_ids)]:js=js.replace(key,json.dumps(val))
    node('Verify operator comment','code',2,dict(mode='runOnceForAllItems',jsCode=js))
    node('Respond with native comment','respondToWebhook',1.4,dict(respondWith='json',responseBody='={{ $json }}',options=dict(responseCode=200)))
    connections={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    return dict(name='Operator verified comment reader (inactive)',active=False,nodes=nodes,connections=connections,
        settings=dict(executionOrder='v1',saveDataErrorExecution='none',saveDataSuccessExecution='none',saveManualExecutions=False,executionTimeout=30),tags=[],pinData={})
