"""Inactive, read-only native-context lookup for Jarvis reporting tools."""
import importlib.util
import json
from pathlib import Path
import uuid


def render(configuration):
    spec=importlib.util.spec_from_file_location('hermes_context_handoff',Path(__file__).with_name('n8n_handoff.py'))
    handoff=importlib.util.module_from_spec(spec);spec.loader.exec_module(handoff)
    template=handoff.render(configuration)['workflows']['jarvis_request'];policy=configuration['policy'];org=policy['organization_id']
    result=json.loads(json.dumps(template));result['name']='Jarvis exact native engineering context v0.4 (inactive)'
    webhook,validate,read,reply=result['nodes']
    webhook['parameters']['path']='rras-jarvis-engineering-context'
    validate['parameters']['jsCode']="""const value=$input.first().json.body;
const keys=['contract','organization_id','session_id','hermes_session_id','run_id'];
const uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v);
if(!value||Object.keys(value).sort().join()!==keys.sort().join()||value.contract!=='jarvis-native-context.v1'||
 value.organization_id!==ORG||!uuid(value.session_id)||!/^run_[0-9a-f]{32}$/.test(value.run_id)||
 value.hermes_session_id!=='linear:'+value.organization_id+':'+value.session_id)throw new Error('Exact actual native context required');
return [{json:value}];""".replace('ORG',json.dumps(org))
    issues=','.join("'"+value+"'::uuid" for value in policy['issues'])
    read['parameters']=dict(operation='executeQuery',query=f"""SELECT (SELECT jsonb_build_object(
 'session_id',e.session_id,'issue_id',e.issue_id,'binding',e.binding,'parent_handoff_id',h.id,'depth',coalesce(h.depth,0),
 'delivery_id',e.delivery_id)
 FROM linear_bridge.jarvis_engineering_runs e JOIN linear_bridge.hermes_runs r
 ON r.hermes_run_id=e.run_id AND r.agent_session_id=e.session_id::text
 LEFT JOIN linear_bridge.native_handoffs h ON h.organization_id=e.organization_id AND h.recipient='jarvis' AND h.target_session_id=e.session_id
 WHERE e.organization_id='{org}'::uuid AND e.issue_id IN ({issues}) AND e.run_id=$1::text AND e.session_id=$2::uuid
 AND e.hermes_session_id=$3::text) AS context""",
        options=dict(queryReplacement='={{ [$json.run_id,$json.session_id,$json.hermes_session_id] }}'))
    reply['parameters']['responseBody']='={{ {context:$json.context||null,execution_started:false} }}'
    for node in result['nodes']:node['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:jarvis-native-context:'+node['name']))
    webhook['webhookId']=webhook['id']
    return result


def checkpoint(configuration):
    result=render(configuration);result['name']='Jarvis scoped engineering checkpoint v0.4 (inactive)'
    webhook,validate,save,reply=result['nodes'];webhook['parameters']['path']='rras-jarvis-engineering-checkpoint'
    base=validate['parameters']['jsCode']
    validate['parameters']['jsCode']=base.replace('const value=$input.first().json.body;',
        """const frame=$input.first().json.body;
if(!frame||Object.keys(frame).sort().join()!==['id','native','report'].sort().join())throw new Error('Exact native checkpoint frame required');
const value={contract:'jarvis-native-context.v1',...frame.native};""").replace('return [{json:value}];',"""
if(!uuid(frame.id)||frame.report?.operation!=='checkpoint.report'||frame.report?.source?.kind!=='agent_reported'||
 frame.report?.source?.namespace!=='hermes_runtime_adapter'||frame.report?.source?.id!==value.run_id)throw new Error('Fixed attributed checkpoint required');
const report_json=JSON.stringify(frame.report);
if(report_json.length>32768)throw new Error('Bounded checkpoint required');
return [{json:{...value,id:frame.id,report_json}}];""")
    org=configuration['policy']['organization_id']
    save['parameters']=dict(operation='executeQuery',query=f"SELECT linear_bridge.jarvis_engineering_checkpoint($1::uuid,'{org}'::uuid,$2::uuid,$3::text,$4::text,$5::text) AS request_id",
        options=dict(queryReplacement='={{ [$json.id,$json.session_id,$json.hermes_session_id,$json.run_id,$json.report_json] }}'))
    reply['parameters']['responseBody']='={{ {staged:true,request_id:$json.request_id,execution_started:false} }}'
    for node in result['nodes']:node['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:jarvis-native-checkpoint:'+node['name']))
    webhook['webhookId']=webhook['id']
    return result
