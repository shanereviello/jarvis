"""Hash checked transformation retains the existing restricted Jarvis request."""
import copy
import hashlib
import json
import pytest
from test_reporting_n8n_handoff import m as handoff_module,configuration as handoff_configuration


m=handoff_module.local('n8n_jarvis_admission')


@pytest.fixture
def configuration():return handoff_configuration()


def snapshot():
    normal=dict(name='Normalize and Validate',type='n8n-nodes-base.code',parameters=dict(jsCode='const issue = session.issue ?? body.issue ?? {};'))
    start=dict(name='Start Restricted Hermes Run',type='n8n-nodes-base.httpRequest',credentials={'httpHeaderAuth':{'id':'existing-hermes'}},parameters=dict(
        method='POST',url='http://hermes:8642/v1/runs',options={'timeout':10000},body="={{ JSON.stringify({input: $('Normalize and Validate').item.json.prompt, session_id: 'fixture', instructions: 'You are not authorized to modify repositories, run terminal commands, access files, deploy, merge, push, or create an execution request.'}) }}"))
    only=dict(name='Only New Deliveries',type='n8n-nodes-base.code',parameters={'jsCode':'return $input.all();'})
    record=dict(name='Record Hermes Run',type='n8n-nodes-base.postgres',parameters={'query':'SELECT 1;'})
    return dict(id='existing-jarvis-flow',name='Existing restricted Jarvis',versionId='existing-version',active=True,nodes=[normal,only,start,record],
        connections={'Only New Deliveries':{'main':[[{'node':'Start Restricted Hermes Run','type':'main','index':0}]]},
            'Start Restricted Hermes Run':{'main':[[{'node':'Record Hermes Run','type':'main','index':0}]]}})


def render(value,configuration):return m.render(value,hashlib.sha256(m.encoded(value)).hexdigest(),configuration)


def test_inactive_patch_preserves_existing_identity_and_restrictions(configuration):
    original=snapshot();saved=copy.deepcopy(original);result=render(original,configuration);value=result['workflow']
    assert original==saved and value['id']==saved['id'] and value['versionId']==saved['versionId'] and not value['active']
    nodes={n['name']:n for n in value['nodes']};old={n['name']:n for n in original['nodes']}
    for name in ('Only New Deliveries','Record Hermes Run'):assert nodes[name]==old[name]
    expected=copy.deepcopy(old['Start Restricted Hermes Run']);expected['parameters']['body']=nodes['Start Restricted Hermes Run']['parameters']['body']
    assert nodes['Start Restricted Hermes Run']==expected
    selected=nodes['Select mapped engineering context']['parameters']['jsCode']
    assert "You are not authorized to modify repositories, run terminal commands, access files" in selected
    assert "Object.hasOwn(policy.issues,n.issueId)" in selected and 'engineering_run_body:runBody' in selected
    assert value['connections']['Mapped engineering issue']['main'][1][0]['node']=='Start Restricted Hermes Run'
    assert value['connections']['Verified engineering origin']['main'][1][0]['node']=='Report unconfirmed engineering origin'
    read=nodes['Read actual Jarvis native origin']
    ref=configuration['credentials']['jarvis_oauth'];assert read['credentials'][ref['type']]['id']==ref['id']
    assert read['retryOnFail'] is False
    assert all('terminal' not in name.lower() for name in nodes)


def test_changed_snapshot_or_topology_is_not_patched(configuration):
    value=snapshot();digest=hashlib.sha256(m.encoded(value)).hexdigest();value['name']='changed'
    with pytest.raises(ValueError,match='changed'):m.render(value,digest,configuration)
    for changed in ('url','body'):
        value=snapshot();value['nodes'][2]['parameters'][changed]='unexpected'
        with pytest.raises(ValueError):render(value,configuration)
    value=snapshot();value['connections']['Only New Deliveries']['main'].append([])
    with pytest.raises(ValueError,match='topology'):render(value,configuration)
