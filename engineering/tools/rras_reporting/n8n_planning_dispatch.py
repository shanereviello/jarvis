"""Render inactive Codex planning dispatch and reconciliation workflows."""
import importlib.util
import ipaddress
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('planning_dispatch_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration,runtime_origin,planning_header):
    base=local('n8n_codex');c=base.configuration(configuration);origin=base.url(runtime_origin,False)
    from urllib.parse import urlsplit
    parsed=urlsplit(origin)
    try:address=ipaddress.ip_address(parsed.hostname)
    except ValueError:raise ValueError('fixed private runtime IP required') from None
    if (not address.is_private or address.is_unspecified or parsed.path not in ('','/') or
            type(planning_header) is not str or not planning_header.strip() or len(planning_header)>128 or planning_header in c['credentials'].values()):
        raise ValueError('separate private planning runtime binding required')
    org,app=c['organization_id'],c['app_user_id']
    select=f"organization_id='{org}'::uuid AND app_user_id='{app}'::uuid"
    def workflow(kind):
        nodes=[]
        def node(name,typ,version,parameters,credential=None):
            value=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:planning:'+kind+':'+name)),name=name,
                type='n8n-nodes-base.'+typ,typeVersion=version,position=[240*len(nodes),0],parameters=parameters)
            if credential:value['credentials']={credential[0]:dict(id=credential[1],name='Protected planning credential reference')}
            nodes.append(value);return value
        node('Poll planning queue','scheduleTrigger',1.2,dict(rule=dict(interval=[dict(field='seconds',secondsInterval=5)])))
        if kind=='dispatch':
            query=f"""WITH candidate AS (SELECT e.id FROM linear_bridge.codex_planning_events e WHERE {select.replace('organization_id','e.organization_id').replace('app_user_id','e.app_user_id')}
 AND e.state='pending' AND coalesce(e.envelope->>'signal','')<>'stop' AND NOT EXISTS
 (SELECT 1 FROM linear_bridge.codex_planning_events a WHERE a.organization_id=e.organization_id AND a.app_user_id=e.app_user_id
 AND a.state IN ('dispatching','running','uncertain')) ORDER BY e.received_at,e.id LIMIT 1 FOR UPDATE SKIP LOCKED)
 UPDATE linear_bridge.codex_planning_events e SET state='dispatching',updated_at=now() FROM candidate WHERE e.id=candidate.id RETURNING e.*"""
        elif kind=='reconcile':
            query=f"""SELECT id,envelope FROM linear_bridge.codex_planning_events WHERE {select}
 AND coalesce(envelope->>'signal','')<>'stop' AND (state='running' OR
 (state IN ('dispatching','uncertain') AND updated_at < now()-interval '60 seconds'))
 ORDER BY updated_at,id LIMIT 1"""
        else:
            query=f"""WITH candidate AS (SELECT e.id FROM linear_bridge.codex_planning_events e WHERE {select.replace('organization_id','e.organization_id').replace('app_user_id','e.app_user_id')}
 AND e.state='pending' AND e.envelope->>'signal'='stop' ORDER BY e.received_at,e.id LIMIT 1 FOR UPDATE SKIP LOCKED)
 UPDATE linear_bridge.codex_planning_events e SET state='dispatching',updated_at=now() FROM candidate WHERE e.id=candidate.id
 RETURNING e.*,(SELECT a.id FROM linear_bridge.codex_planning_events a WHERE a.organization_id=e.organization_id AND a.app_user_id=e.app_user_id
 AND a.session_id=e.session_id AND a.state='running' ORDER BY a.updated_at DESC LIMIT 1) AS target_dispatch"""
        node('Select retained planning event','postgres',2.6,dict(operation='executeQuery',query=query,options={}),('postgres',c['credentials']['postgres']))
        if kind=='dispatch':
            prepare="""const row=$input.first().json;if(!row.id)return [];const e=row.envelope;
if(!e||e.contract!=='codex-planning-event.v1'||e.mode!=='planning'||e.binding!==undefined)throw new Error('Planning event required');
return [{json:{event_id:row.id,url:ORIGIN+'/v1/planning/dispatch',request:{dispatch_id:row.id,organization_id:e.organization_id,
 app_user_id:e.app_user_id,session_id:e.session_id,issue_id:e.issue_id,message:e.message}}}];""".replace('ORIGIN',json.dumps(origin))
        elif kind=='reconcile':
            prepare="""const row=$input.first().json;if(!row.id)return [];
return [{json:{event_id:row.id,url:ORIGIN+'/v1/planning/runs/'+encodeURIComponent(row.id)}}];""".replace('ORIGIN',json.dumps(origin))
        else:
            prepare="""const row=$input.first().json;if(!row.id)return [];const e=row.envelope;
if(!e||e.contract!=='codex-planning-event.v1'||e.signal!=='stop')throw new Error('Native stop event required');
return [{json:{event_id:row.id,has_target:!!row.target_dispatch,url:ORIGIN+'/v1/planning/interrupt',request:{
 stop_dispatch_id:row.id,target_dispatch_id:row.target_dispatch,session_id:e.session_id,issue_id:e.issue_id,
 organization_id:e.organization_id,app_user_id:e.app_user_id,message:e.message},
 runtime_result:{dispatch:row.id,state:'failed',reason:'No active planning turn for this session.'}}}];""".replace('ORIGIN',json.dumps(origin))
        node('Prepare planning runtime request','code',2,dict(mode='runOnceForAllItems',jsCode=prepare))
        if kind=='stop':
            node('Known planning target','if',2.2,dict(conditions=dict(options=dict(typeValidation='strict'),conditions=[dict(id='target',
                leftValue='={{ $json.has_target }}',rightValue=True,operator=dict(type='boolean',operation='true',singleValue=True))],combinator='and'),options={}))
        parameters=dict(method='GET' if kind=='reconcile' else 'POST',url='={{ $json.url }}',authentication='genericCredentialType',
            genericAuthType='httpHeaderAuth',options=dict(timeout=20000,response=dict(response=dict(fullResponse=True,neverError=True))))
        if kind!='reconcile':parameters.update(sendBody=True,contentType='raw',rawContentType='application/json',body='={{ JSON.stringify($json.request) }}')
        http=node('Call planning runtime','httpRequest',4.2,parameters,('httpHeaderAuth',planning_header))
        http.update(onError='continueRegularOutput',retryOnFail=False)
        assess="""const request=$('Prepare planning runtime request').first().json,reply=$input.first().json,body=reply.body||{};
const states=['running','completed','failed','interrupted','uncertain','interrupt_requested'];
const good=reply.statusCode>=200&&reply.statusCode<300&&body.dispatch===request.event_id&&states.includes(body.state);
const result=good?body:{dispatch:request.event_id,state:'uncertain',reason:'Planning runtime outcome unconfirmed; do not retry.'};
if(result.state==='interrupt_requested')result.state='running';
return [{json:{event_id:request.event_id,runtime_result:result}}];"""
        node('Assess planning result','code',2,dict(mode='runOnceForAllItems',jsCode=assess))
        old="IN ('running','dispatching','uncertain')" if kind=='reconcile' else "= 'dispatching'"
        finish=f"""WITH updated AS (UPDATE linear_bridge.codex_planning_events SET state=$2::jsonb->>'state',runtime_result=$2::jsonb,updated_at=now()
 WHERE {select} AND id=$1::uuid AND state {old} RETURNING *)
 INSERT INTO linear_bridge.codex_planning_outbox(organization_id,app_user_id,session_id,source_key,content)
 SELECT organization_id,app_user_id,session_id,'result:'||id::text||':'||state,
 jsonb_build_object('type',CASE WHEN state='completed' THEN 'response' WHEN state='uncertain' THEN 'thought' ELSE 'error' END,
 'body',CASE WHEN state='completed' THEN left(coalesce(runtime_result->>'result','Planning completed without a captured response; inspect retained evidence.'),10000)
 WHEN state='uncertain' THEN 'Planning outcome is uncertain; retained state needs reconciliation. It was not automatically rerun.'
 WHEN state='interrupted' THEN 'Planning turn interrupted.' ELSE 'Planning could not complete; inspect retained evidence.' END)
 FROM updated WHERE state IN ('completed','uncertain','interrupted','failed')
 ON CONFLICT(organization_id,app_user_id,source_key) DO NOTHING RETURNING id"""
        node('Retain planning result','postgres',2.6,dict(operation='executeQuery',query=finish,
            options=dict(queryReplacement='={{ [$json.event_id,JSON.stringify($json.runtime_result)] }}')),('postgres',c['credentials']['postgres']))
        connections={a['name']:dict(main=[[dict(node=b['name'],type='main',index=0)]]) for a,b in zip(nodes,nodes[1:])}
        if kind=='stop':connections['Known planning target']=dict(main=[[dict(node='Call planning runtime',type='main',index=0)],
            [dict(node='Retain planning result',type='main',index=0)]])
        return dict(name='Codex planning '+kind+' (inactive)',active=False,nodes=nodes,connections=connections,
            settings=dict(executionOrder='v1',saveDataErrorExecution='none',saveDataSuccessExecution='none',saveManualExecutions=False,executionTimeout=60),tags=[],pinData={})
    outbound=base.render(c)['workflows']['outbound']
    outbound['name']='Codex planning outbound (inactive)'
    replaced=0
    for node in outbound['nodes']:
        node['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:planning:outbound:'+node['name']))
        query=node.get('parameters',{}).get('query')
        if type(query) is str and 'linear_bridge.codex_outbox' in query:
            node['parameters']['query']=query.replace('linear_bridge.codex_outbox','linear_bridge.codex_planning_outbox');replaced+=1
    if replaced!=2:raise ValueError('reviewed outbound topology differs')
    workflows={kind:workflow(kind) for kind in ('dispatch','reconcile','stop')};workflows['outbound']=outbound
    return dict(contract='codex-planning-dispatch-candidate.v1',workflows=workflows,
                active=False,outbox_delivery_candidate=True,outbox_delivery_verified=False,stop_delivery_candidate=True,stop_delivery_verified=False,production_ready=False)
