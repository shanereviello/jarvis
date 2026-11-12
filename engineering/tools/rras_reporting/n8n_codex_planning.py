"""Render a synthetic inactive inbound candidate; no n8n writes or activation.

This is deliberately only the inbound half: planning dispatch, native
verification, acknowledgement, and reconciliation must be wired and tested
before a candidate may be installed.
"""
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('n8n_planning_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def render(configuration):
    base=local('n8n_codex');config=base.configuration(configuration);package=base.render(config)
    inbound=package['workflows']['inbound'];nodes=inbound['nodes'];named={node['name']:node for node in nodes}
    expected={'Codex verified webhook','Admit Codex event','Retain Codex event','Acknowledge durable receipt'}
    if set(named)!=expected:raise ValueError('reviewed inbound topology required')
    policy={key:config[key] for key in ('organization_id','app_user_id','oauth_client_id','agent_actor_ids','issues')}
    policy['planning_enabled']=True
    root=Path(__file__).resolve().parent
    source=(root/'n8n_codex_admission.js').read_text()+'\n'+(root/'n8n_codex_planning_admission.js').read_text()
    named['Admit Codex event']['parameters']['jsCode']=source+'\nconst policy='+json.dumps(policy)+';\nreturn [{json:admitCodexRoute($input.first().json,policy)}];'
    route=dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:codex-planning-route')),name='Select planning route',
        type='n8n-nodes-base.if',typeVersion=2.2,position=[480,180],parameters=dict(conditions=dict(
            options=dict(typeValidation='strict'),conditions=[dict(id='planning-route',leftValue='={{ $json.route }}',
            rightValue='planning',operator=dict(type='string',operation='equals'))],combinator='and'),options={}))
    retained=json.loads(json.dumps(named['Retain Codex event']))
    retained['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras:v05:codex-planning-retain'))
    retained['name']='Retain Codex planning event';retained['position']=[720,180]
    retained['parameters']['query']='SELECT * FROM linear_bridge.codex_planning_accept($1::uuid,$2::uuid,$3::uuid,$4::text,$5::jsonb)'
    nodes.extend([route,retained])
    def connection(name):return dict(node=name,type='main',index=0)
    inbound['connections']={
        'Codex verified webhook':dict(main=[[connection('Admit Codex event')]]),
        'Admit Codex event':dict(main=[[connection('Select planning route')]]),
        'Select planning route':dict(main=[[connection('Retain Codex planning event')],[connection('Retain Codex event')]]),
        'Retain Codex event':dict(main=[[connection('Acknowledge durable receipt')]]),
        'Retain Codex planning event':dict(main=[[connection('Acknowledge durable receipt')]])}
    inbound['name']='Codex v0.5 planning ingress candidate (inactive)'
    return dict(contract='codex-planning-ingress-candidate.v1',workflow=inbound,active=False,
                dispatch_complete=False,production_ready=False)
