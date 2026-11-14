import importlib.util
from pathlib import Path

import pytest


path=Path(__file__).parents[1]/'tools/rras_reporting/hermes_planning_receipt.py'
spec=importlib.util.spec_from_file_location('receipt',path)
receipt=importlib.util.module_from_spec(spec);spec.loader.exec_module(receipt)


def fixture():
    org='00000000-0000-4000-8000-000000000001'
    session='00000000-0000-4000-8000-000000000002'
    native=dict(organization_id=org,session_id=session,hermes_session_id='linear:'+org+':'+session,run_id='run_'+'a'*32)
    row=dict(hermes_run_id=native['run_id'],status='running',organization_id=org,receipt_organization_id=org,
        agent_session_id=session,receipt_session_id=session,hermes_session_id=native['hermes_session_id'],
        event_type='AgentSessionEvent',action='created',delivery_id='delivery',issue_id='issue',raw_payload={})
    return native,row


def test_exact_active_receipt_is_evidence_only():
    native,row=fixture()
    assert receipt.bind(native)==[native['run_id'],native['organization_id'],native['session_id'],native['hermes_session_id']]
    assert receipt.receipt(native,[row])['delivery_id']=='delivery'
    assert 'JOIN linear_bridge.webhook_receipts w ON w.delivery_id=r.delivery_id' in receipt.QUERY
    assert "jsonb_build_object('action'" in receipt.QUERY
    assert "w.raw_payload\n" not in receipt.QUERY and 'promptContext' not in receipt.QUERY


@pytest.mark.parametrize('field,value',[
    ('status','completed'),('event_type','Other'),('action','deleted'),
    ('receipt_organization_id','other'),('receipt_session_id','other'),('raw_payload',None),
])
def test_other_or_inactive_delivery_refused(field,value):
    native,row=fixture();row[field]=value
    with pytest.raises(ValueError):receipt.receipt(native,[row])


def test_missing_or_ambiguous_receipt_refused():
    native,row=fixture()
    for rows in ([],[row,row]):
        with pytest.raises(ValueError):receipt.receipt(native,rows)
