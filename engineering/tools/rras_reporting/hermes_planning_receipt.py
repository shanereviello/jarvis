"""Exact retained Linear delivery lookup for an active Jarvis native run.

The receipt is evidence for a separate live Linear origin check, not authority
to plan on its own. This module does not open a database or change a workflow.
"""
import importlib.util
from pathlib import Path


QUERY = """SELECT r.hermes_run_id, r.status, s.organization_id,
 s.agent_session_id, s.hermes_session_id, s.issue_id,
 w.delivery_id, w.event_type, w.action, w.organization_id AS receipt_organization_id,
 w.agent_session_id AS receipt_session_id,
 jsonb_build_object('action',w.raw_payload->'action',
   'agentSession',jsonb_build_object(
     'id',w.raw_payload->'agentSession'->>'id',
     'issueId',COALESCE(w.raw_payload->'agentSession'->>'issueId',w.raw_payload->'agentSession'->'issue'->>'id'),
     'sourceCommentId',COALESCE(w.raw_payload->'agentSession'->>'sourceCommentId',w.raw_payload->'agentSession'->>'commentId',
         w.raw_payload->'agentSession'->'sourceComment'->>'id',w.raw_payload->'agentSession'->'comment'->>'id'),
     'creatorId',COALESCE(w.raw_payload->'agentSession'->>'creatorId',w.raw_payload->'agentSession'->'creator'->>'id')),
   'agentActivity',jsonb_build_object('userId',COALESCE(w.raw_payload->'agentActivity'->>'userId',
         w.raw_payload->'agentActivity'->'user'->>'id'))) AS raw_payload
FROM linear_bridge.hermes_runs r
JOIN linear_bridge.agent_sessions s ON s.agent_session_id=r.agent_session_id
JOIN linear_bridge.webhook_receipts w ON w.delivery_id=r.delivery_id
WHERE r.hermes_run_id=$1 AND s.organization_id=$2 AND s.agent_session_id=$3
 AND s.hermes_session_id=$4
LIMIT 2"""


def bind(native):
    spec=importlib.util.spec_from_file_location('planning_receipt_native',Path(__file__).with_name('hermes_native_context.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if type(native) is not dict or module.parse('api_server',native.get('hermes_session_id'),native.get('run_id'))!=native:
        raise ValueError('exact native run required')
    return [native['run_id'],native['organization_id'],native['session_id'],native['hermes_session_id']]


def receipt(native, rows):
    bind(native)
    if type(rows) is not list or len(rows)!=1 or type(rows[0]) is not dict:
        raise ValueError('one retained native delivery required')
    row=rows[0]
    if (row.get('hermes_run_id')!=native['run_id'] or row.get('status')!='running' or
            row.get('organization_id')!=native['organization_id'] or row.get('receipt_organization_id')!=native['organization_id'] or
            row.get('agent_session_id')!=native['session_id'] or row.get('receipt_session_id')!=native['session_id'] or
            row.get('hermes_session_id')!=native['hermes_session_id'] or
            row.get('event_type')!='AgentSessionEvent' or row.get('action') not in ('created','prompted') or
            not row.get('delivery_id') or not row.get('issue_id') or type(row.get('raw_payload')) is not dict):
        raise ValueError('active exact native delivery required')
    return dict(action=row['action'],issue_id=row['issue_id'],delivery_id=str(row['delivery_id']),raw_payload=row['raw_payload'])
