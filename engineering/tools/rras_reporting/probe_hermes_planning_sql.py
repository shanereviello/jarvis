"""Read-only live PostgreSQL acceptance for the minimized Jarvis receipt query."""
import importlib.util
import os
from pathlib import Path
import subprocess


def main():
    if os.geteuid()!=0:raise ValueError('root Docker launcher required')
    path=Path(__file__).with_name('hermes_planning_receipt.py')
    spec=importlib.util.spec_from_file_location('receipt_query_probe',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    query=module.QUERY
    for slot,column in [('$1','p.run_id'),('$2','p.organization_id'),('$3','p.session_id'),('$4','p.hermes_session_id')]:
        if query.count(slot)!=1:raise ValueError('exact parameterized query required')
        query=query.replace(slot,column)
    sql="""WITH p AS (
 SELECT r.hermes_run_id AS run_id,s.organization_id,s.agent_session_id AS session_id,s.hermes_session_id
 FROM linear_bridge.hermes_runs r JOIN linear_bridge.agent_sessions s ON s.agent_session_id=r.agent_session_id
), results AS (SELECT p.session_id,x.* FROM p CROSS JOIN LATERAL ("""+query+""") x)
SELECT action,count(*) AS matched_runs,
 count(*) FILTER (WHERE raw_payload->'agentSession'->>'id'=session_id) AS matching_session,
 count(*) FILTER (WHERE raw_payload->'agentSession'->>'issueId'=issue_id) AS matching_issue,
 count(*) FILTER (WHERE NOT (raw_payload ? 'promptContext') AND NOT (raw_payload ? 'body')) AS minimized_payload,
 count(*) FILTER (WHERE raw_payload->>'action' IS NULL OR raw_payload->>'action'=action) AS matching_action
FROM results GROUP BY action ORDER BY action;"""
    subprocess.run(['docker','exec','-i','engineering-postgres','psql','-X','-U','shanereviello','-d','n8n',
                    '-P','pager=off','-v','ON_ERROR_STOP=1'],input=sql,text=True,check=True,timeout=60)


if __name__=='__main__':main()
