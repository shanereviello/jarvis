"""One inactive selected-project reader for native Jarvis runs and checkpoints."""
import importlib.util
import json
from pathlib import Path
import uuid


def render(value,postgres_reference,header_reference):
    spec=importlib.util.spec_from_file_location('selected_hermes_history',Path(__file__).with_name('hermes_history.py'))
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source);selected=source.configuration(value)
    spec=importlib.util.spec_from_file_location('selected_hermes_history_template',Path(__file__).with_name('n8n_handoff_history.py'))
    template=importlib.util.module_from_spec(spec);spec.loader.exec_module(template)
    result=template.render(dict(selected,contract='native-handoff-history-source.v1'),postgres_reference,header_reference)
    project=next(iter(selected['contexts'].values()))[0]['context']['project_id'];org=selected['policy']['organization_id']
    issues=','.join("'"+key+"'::uuid" for key in selected['contexts'])
    webhook,validate,read,formatting,reply=result['nodes'];webhook['parameters']['path']='rras-hermes-engineering-history-'+project
    validate['parameters']['jsCode']="""const b=$input.first().json.body;
if(!b||Object.keys(b).sort().join()!==['after_run','after_checkpoint','after_admission'].sort().join()||
 !Number.isSafeInteger(b.after_run)||b.after_run<0||!Number.isSafeInteger(b.after_checkpoint)||b.after_checkpoint<0)
 throw new Error('Only bounded configured-project cursors are accepted');
if(!Number.isSafeInteger(b.after_admission)||b.after_admission<0)throw new Error('Bounded admission cursor required');
return [{json:b}];"""
    scoped=f"e.organization_id='{org}'::uuid AND e.issue_id IN ({issues}) AND e.binding->>'project_id'='{project}'"
    query=f"""WITH admissions AS (
 SELECT a.sequence,a.delivery_id,a.organization_id,a.session_id,a.issue_id,a.binding,a.handoff_id,
 to_char(a.observed_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS observed_at
 FROM linear_bridge.jarvis_engineering_admissions a WHERE a.organization_id='{org}'::uuid AND a.issue_id IN ({issues})
 AND a.binding->>'project_id'='{project}' AND a.permitted AND a.sequence>$3::bigint ORDER BY a.sequence LIMIT 16),checkpoints AS (
 SELECT c.sequence,c.id,c.run_id,c.organization_id,c.issue_id,c.report_json,c.report_sha256,
 to_char(c.observed_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS observed_at
 FROM linear_bridge.jarvis_engineering_checkpoints c JOIN linear_bridge.jarvis_engineering_runs e ON e.run_id=c.run_id
 WHERE {scoped} AND c.sequence>$2::bigint ORDER BY c.sequence LIMIT 16),scan AS (
 SELECT e.run_id,e.sequence FROM linear_bridge.jarvis_engineering_runs e WHERE {scoped}
 AND e.sequence>$1::bigint ORDER BY e.sequence LIMIT 16),wanted AS (
 SELECT run_id FROM scan UNION SELECT run_id FROM checkpoints),runs AS (
 SELECT e.sequence,e.run_id,e.delivery_id,e.organization_id,e.session_id,e.issue_id,e.hermes_session_id,e.binding,a.handoff_id,
 CASE WHEN octet_length(r.status)<=128 THEN r.status ELSE NULL END AS status,
 to_char(a.observed_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS admitted_at,
 to_char(e.recorded_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS recorded_at,
 to_char(r.completed_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS completed_at
 FROM wanted w JOIN linear_bridge.jarvis_engineering_runs e ON e.run_id=w.run_id
 JOIN linear_bridge.jarvis_engineering_admissions a ON a.delivery_id=e.delivery_id
 JOIN linear_bridge.hermes_runs r ON r.hermes_run_id=e.run_id AND r.agent_session_id=e.session_id::text
 WHERE {scoped})
 SELECT jsonb_build_object('contract','hermes-runtime-history-page.v1',
 'admissions',coalesce((SELECT jsonb_agg(to_jsonb(admissions) ORDER BY sequence) FROM admissions),'[]'::jsonb),
 'runs',coalesce((SELECT jsonb_agg(to_jsonb(runs) ORDER BY sequence) FROM runs),'[]'::jsonb),
 'checkpoints',coalesce((SELECT jsonb_agg(to_jsonb(checkpoints) ORDER BY sequence) FROM checkpoints),'[]'::jsonb),
 'next_run_after',CASE WHEN (SELECT count(*) FROM scan)<16 THEN 0 ELSE (SELECT max(sequence) FROM scan) END,
 'next_checkpoint_after',coalesce((SELECT max(sequence) FROM checkpoints),$2::bigint),
 'next_admission_after',coalesce((SELECT max(sequence) FROM admissions),$3::bigint)) AS page"""
    read['parameters']=dict(operation='executeQuery',query=query,options=dict(queryReplacement='={{ [$json.after_run,$json.after_checkpoint,$json.after_admission] }}'))
    formatting['parameters']['jsCode']="""const p=$input.first().json.page;
if(!p||p.contract!=='hermes-runtime-history-page.v1'||!Array.isArray(p.runs)||p.runs.length>32||
 !Array.isArray(p.admissions)||p.admissions.length>16||!Number.isSafeInteger(p.next_admission_after)||p.next_admission_after<0||
 !Array.isArray(p.checkpoints)||p.checkpoints.length>16||!Number.isSafeInteger(p.next_run_after)||p.next_run_after<0||
 !Number.isSafeInteger(p.next_checkpoint_after)||p.next_checkpoint_after<0||JSON.stringify(p).length>1048576)
 throw new Error('Bounded selected native page required');
return [{json:p}];"""
    for node in result['nodes']:node['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras-hermes-history:'+project+':'+node['name']))
    result['name']='Selected native Jarvis engineering history '+project+' (inactive)'
    return result
