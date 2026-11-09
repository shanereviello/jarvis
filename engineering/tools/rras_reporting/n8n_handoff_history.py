"""Render one inactive read-only handoff-event endpoint for one selected project."""
import importlib.util
import json
from pathlib import Path
import uuid


def render(selected,postgres_reference,header_reference):
    spec=importlib.util.spec_from_file_location('selected_handoff_history',Path(__file__).with_name('handoff_history.py'))
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source);selected=source.configuration(selected)
    if any(type(x) is not str or not x.strip() or len(x)>128 for x in (postgres_reference,header_reference)) or postgres_reference==header_reference:
        raise ValueError('separate bounded database/read-only header credential references required')
    project=next(iter(selected['contexts'].values()))[0]['context']['project_id'];org=selected['policy']['organization_id']
    issues=','.join("'"+key+"'" for key in selected['contexts'])
    nodes=[]
    def node(name,kind,version,parameters,credential=None):
        value=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras-handoff-read:'+project+':'+name)),name=name,
            type='n8n-nodes-base.'+kind,typeVersion=version,position=[240*len(nodes),0],parameters=parameters)
        if kind=='webhook':value['webhookId']=value['id']
        if credential:value['credentials']={credential[0]:dict(id=credential[1],name='Selected handoff reader credential reference')}
        nodes.append(value);return value
    node('Private selected handoff history','webhook',2.1,dict(httpMethod='POST',path='rras-native-handoff-events-'+project,
        responseMode='responseNode',authentication='headerAuth',options={}),('httpHeaderAuth',header_reference))
    node('Validate bounded event cursor','code',2,dict(mode='runOnceForAllItems',jsCode="""const b=$input.first().json.body;
if(!b||JSON.stringify(Object.keys(b))!==JSON.stringify(['after'])||!Number.isSafeInteger(b.after)||b.after<0)
 throw new Error('Only the configured project cursor is accepted');
return [{json:{after:b.after}}];"""))
    query=f"""WITH selected AS (SELECT e.sequence,e.id,e.organization_id,e.state,e.snapshot,
 to_char(e.observed_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS observed_at
 FROM linear_bridge.native_handoff_events e WHERE e.organization_id='{org}'::uuid AND e.sequence>$1::bigint
 AND e.snapshot->>'issue_id' IN ({issues}) AND e.snapshot->'body'->'binding'->>'project_id'='{project}'
 ORDER BY e.sequence LIMIT 32),bounded AS (SELECT *,sum(octet_length(snapshot::text)+4096) OVER(ORDER BY sequence) AS bytes FROM selected)
 SELECT sequence,id,organization_id,state,snapshot,observed_at FROM bounded WHERE bytes<=1048576 ORDER BY sequence"""
    value=node('Read only selected immutable events','postgres',2.6,dict(operation='executeQuery',query=query,
        options=dict(queryReplacement='={{ [$json.after] }}')),('postgres',postgres_reference));value['alwaysOutputData']=True
    node('Return bounded native event page','code',2,dict(mode='runOnceForAllItems',jsCode="""const events=$input.all().map(x=>x.json).filter(x=>x.sequence!=null).map(x=>({...x,sequence:Number(x.sequence)}));
if(events.length>32||events.some(x=>!Number.isSafeInteger(x.sequence)||x.sequence<1))throw new Error('Bounded native event page required');
return [{json:{contract:'native-handoff-event-page.v1',events}}];"""))
    node('Respond with selected history','respondToWebhook',1.4,dict(respondWith='json',responseBody='={{ $json }}',options=dict(responseCode=200)))
    connections={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
    return dict(name='Selected native handoff history '+project+' (inactive)',active=False,nodes=nodes,connections=connections,
        settings=dict(executionOrder='v1',saveDataErrorExecution='none',saveDataSuccessExecution='none',saveManualExecutions=False,executionTimeout=30),tags=[],pinData={})
