"""Inactive package rendering; pure JS admission and isolated PostgreSQL probe inputs."""
import copy
import importlib.util
import json
from pathlib import Path
import uuid
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('n8n_fixture',ROOT/'tools/rras_reporting/n8n_codex.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def uid(n):return str(uuid.UUID(int=n))

@pytest.fixture
def config():
    return dict(contract='codex-n8n-config.v1',organization_id=uid(1),app_user_id=uid(2),
        oauth_client_id=uid(3),agent_actor_ids=[uid(2),uid(20)],
        issues={uid(4):dict(project_id='prj_'+'1'*32,work_id='wrk_'+'2'*32,plan_id='SHRR-03',
            work_revision_sha256='3'*64,architecture_version=4,architecture_sha256='4'*64)},
        n8n_redirect_url='https://n8n.example.com/rest/oauth2-credential/callback',
        verified_webhook_url='https://agents.example.com/webhooks/codex',
        runtime_origin='http://codex-runtime:8766',
        credentials=dict(postgres='fixture-pg',edge_header='fixture-edge',
                         runtime_header='fixture-runtime',codex_oauth='fixture-codex-oauth'))


def test_inactive_codex_only_registration_and_transport(config):
    package=m.render(config)
    assert package['registration']['requested_scopes']==['read','write','app:mentionable','app:assignable']
    assert not package['registration']['install_now']
    assert package['registration']['preserve_existing_jarvis']
    assert len(package['workflows'])==4
    for workflow in package['workflows'].values():
        assert workflow['active'] is False
        names={n['name'] for n in workflow['nodes']}
        for source,edges in workflow['connections'].items():
            assert source in names
            for branch in edges['main']:
                assert all(e['node'] in names for e in branch)
        assert workflow['settings']['saveDataSuccessExecution']=='none'
        for node in workflow['nodes']:
            for kind,ref in node.get('credentials',{}).items():
                assert ref['id'] in config['credentials'].values()
            if node['type'].endswith('httpRequest'):
                assert node['retryOnFail'] is False


@pytest.mark.parametrize('field',['organization_id','app_user_id','oauth_client_id','agent_actor_ids',
                                  'verified_webhook_url','n8n_redirect_url','credentials','issues','runtime_origin'])
def test_unsafe_or_missing_binding_is_refused(config,field):
    changed=copy.deepcopy(config)
    if field.endswith('_id'):changed[field]='invalid'
    elif field=='agent_actor_ids':changed[field]=[]
    elif field=='credentials':changed[field]['codex_oauth']=changed[field]['runtime_header']
    elif field=='issues':changed[field]={}
    elif field=='runtime_origin':changed[field]='http://user:secret@runtime/'
    else:changed[field]='http://unverified.example.com/'
    with pytest.raises(ValueError):m.render(changed)


def test_no_blind_outbox_retry_or_runtime_relaunch(config):
    package=m.render(config)
    out=package['workflows']['outbound']
    claim=next(n for n in out['nodes'] if n['name']=='Claim Codex reply')
    assert "SET state='uncertain'" in claim['parameters']['query']
    assert "state='pending'" in claim['parameters']['query']
    verify=next(n for n in out['nodes'] if n['name']=='Verify Codex actor')['parameters']['jsCode']
    assert config['app_user_id'] in verify and config['organization_id'] in verify
    dispatch=package['workflows']['dispatch']
    query=next(n for n in dispatch['nodes'] if n['name']=='Claim Codex dispatch')['parameters']['query']
    assert "('dispatching','running','uncertain')" in query
    assert 'FOR UPDATE SKIP LOCKED' in query


def test_linear_hex_client_id_is_preserved_without_uuid_conversion(config):
    config['oauth_client_id']='0123456789abcdef0123456789abcdef'
    package=m.render(config)
    admission=package['workflows']['inbound']['nodes'][1]['parameters']['jsCode']
    assert config['oauth_client_id'] in admission
    assert '01234567-89ab-cdef-0123-456789abcdef' not in admission


def test_graphql_documents_are_kept_out_of_n8n_expression_templates(config):
    nodes={n['name']:n for n in m.render(config)['workflows']['outbound']['nodes']}
    viewer=json.loads(nodes['Read Codex actor']['parameters']['body'])
    assert viewer['query'].startswith('query CodexViewer ')
    assert nodes['Publish Codex activity']['parameters']['body']=='={{ JSON.stringify($json.publication_request) }}'
    construction=nodes['Verify Codex actor']['parameters']['jsCode']
    assert 'AgentActivityCreateInput!' in construction
    assert 'id:row.id,agentSessionId:row.session_id,content:row.content' in construction


@pytest.mark.parametrize('client',[None,32,'', 'a'*31,'a'*33,'g'*32,'a'*32+'\n'])
def test_invalid_linear_client_ids_are_refused(config,client):
    config['oauth_client_id']=client
    with pytest.raises(ValueError):m.render(config)


def test_registration_uses_n8n_callback_and_both_scopes():
    spec=importlib.util.spec_from_file_location('setup_n8n_fixture',ROOT/'tools/rras_reporting/linear_setup.py')
    setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
    callback='https://n8n.example.com/rest/oauth2-credential/callback'
    webhook='https://agents.example.com/webhooks/codex'
    result=setup.n8n_setup(callback,webhook)
    assert result['transport']=='existing-n8n' and result['preserve_existing_jarvis']
    assert set(result['agents'])=={'codex'}
    app=result['agents']['codex']
    assert app['manifest']['oauth']['redirect_uris']==[callback]
    assert app['manifest']['webhook']['url']==webhook
    assert 'app:mentionable' in app['requested_scopes'] and 'app:assignable' in app['requested_scopes']
    with pytest.raises(ValueError):setup.n8n_setup('https://agents.example.com/oauth/codex/callback',webhook)
    with pytest.raises(ValueError):setup.n8n_setup(callback,'https://agents.example.com/webhooks/jarvis')
