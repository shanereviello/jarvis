"""Render an inactive fixed-query native Linear issue reader."""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec = importlib.util.spec_from_file_location('operator_issue_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration, operator_header, team_ids):
    config = local('n8n_codex').configuration(configuration);identifier = local('onboarding_drafts').identifier
    if (type(operator_header) is not str or not operator_header.strip() or len(operator_header) > 128 or
            operator_header in config['credentials'].values()):
        raise ValueError('separate operator reader credential required')
    if type(team_ids) is not list or not team_ids or len(team_ids) > 128 or len(set(team_ids)) != len(team_ids):
        raise ValueError('bounded team grants required')
    for item in team_ids:identifier(item)
    app, org = config['app_user_id'], config['organization_id'];nodes = []
    def node(name, kind, version, parameters, credential=None):
        obj = dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'rras:v05:operator-issue:' + app + ':' + name)), name=name,
            type='n8n-nodes-base.' + kind, typeVersion=version, position=[len(nodes)*240,0], parameters=parameters)
        if kind == 'webhook':obj['webhookId'] = obj['id']
        if credential:obj['credentials'] = {credential[0]:dict(id=credential[1],name='Protected operator credential reference')}
        nodes.append(obj);return obj
    node('Private operator issue','webhook',2.1,dict(httpMethod='POST',path='rras-operator-issue-'+app,
        responseMode='responseNode',authentication='headerAuth',options={}),('httpHeaderAuth',operator_header))
    query = local('onboarding_linear_issue_reader').QUERY
    node('Prepare exact issue read','code',2,dict(mode='runOnceForAllItems',jsCode="""const b=$input.first().json.body;
if(!b||Object.keys(b).sort().join()!=='issue_id'||typeof b.issue_id!=='string'||
 !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(b.issue_id))throw new Error('Exact issue required');
return [{json:{issue_id:b.issue_id,native_request:{query:QUERY,variables:{id:b.issue_id}}}}];""".replace('QUERY',json.dumps(query))))
    native = node('Read native issue','httpRequest',4.2,dict(method='POST',url='https://api.linear.app/graphql',
        authentication='genericCredentialType',genericAuthType='oAuth2Api',sendBody=True,contentType='raw',rawContentType='application/json',
        body='={{ JSON.stringify($json.native_request) }}',options=dict(timeout=15000,response=dict(response=dict(fullResponse=True,neverError=True)))),
        ('oAuth2Api',config['credentials']['codex_oauth']))
    native.update(onError='continueRegularOutput',retryOnFail=False)
    js="""const expected=$('Prepare exact issue read').first().json,reply=$input.first().json,data=reply.body?.data;
if(reply.statusCode!==200||reply.body?.errors||data?.viewer?.id!==APP||data?.viewer?.organization?.id!==ORG||
 data?.issue?.id!==expected.issue_id||!TEAMS.includes(data?.issue?.team?.id)||!data?.issue?.project?.id)
 return [{json:{permitted:false}}];
return [{json:{permitted:true,data}}];"""
    for key,value in [('APP',app),('ORG',org),('TEAMS',team_ids)]:js=js.replace(key,json.dumps(value))
    node('Verify native issue','code',2,dict(mode='runOnceForAllItems',jsCode=js))
    node('Respond with native issue','respondToWebhook',1.4,dict(respondWith='json',responseBody='={{ $json }}',options=dict(responseCode=200)))
    connections = {a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    return dict(name='Operator verified issue reader (inactive)',active=False,nodes=nodes,connections=connections,
        settings=dict(executionOrder='v1',saveDataErrorExecution='none',saveDataSuccessExecution='none',
                      saveManualExecutions=False,executionTimeout=30),tags=[],pinData={})
