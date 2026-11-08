"""Execute generated reader Code nodes; no outside API or OAuth credentials."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from test_reporting_linear_observer import P,T,A,O,I

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
spec=importlib.util.spec_from_file_location('n8n_linear_reader_test',ROOT/'n8n_linear_observer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def config():return dict(contract='engineering-linear-reader.v1',organization_id=O,team_id=T,actor_id=A,project_id=P,
    credentials=dict(oauth='synthetic-oauth-reference',reader_header='synthetic-reader-reference'))


@pytest.fixture
def node():
    binary=os.environ.get('SHRR_TEST_NODE') or shutil.which('node')
    if not binary:pytest.skip('reviewed Node executable required for generated code execution')
    return binary


def execute(node,code,body,prior=None):
    script='''const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
try {const fn=new Function('$json','$',input.code);const value=fn(input.body,()=>({first:()=>({json:input.prior})}));
process.stdout.write(JSON.stringify({ok:true,value}));}
catch(e){process.stdout.write(JSON.stringify({ok:false}));}'''
    result=subprocess.run([node,'-e',script],input=json.dumps(dict(code=code,body=body,prior=prior)),text=True,capture_output=True,timeout=10)
    assert result.returncode==0;return json.loads(result.stdout)


def test_inactive_reader_has_fixed_endpoints_credentials_and_no_mutation():
    workflow=m.render(config())
    assert workflow['active'] is False and len(workflow['nodes'])==4
    webhook=workflow['nodes'][0]
    assert webhook['parameters']['authentication']=='headerAuth'
    assert webhook['parameters']['path'].endswith(P)
    assert workflow['settings']['saveDataSuccessExecution']=='none'
    assert all(not n['retryOnFail'] for n in workflow['nodes'])
    http=workflow['nodes'][2]
    assert http['parameters']['url']=='https://api.linear.app/graphql'
    assert http['parameters']['body']=='={{ JSON.stringify($json.graphql) }}'


def test_generated_reader_accepts_cursor_and_rejects_arbitrary_query_or_project(node):
    prepare,_=m.scripts(config());body=dict(operation='issues',object_id=P,after='native-cursor')
    accepted=execute(node,prepare,dict(body=body))
    assert accepted['ok']
    result=accepted['value'][0]['json']['graphql']
    assert result['variables']==dict(id=P,after='native-cursor') and 'mutation' not in result['query']
    for changed in [dict(body,operation='mutation'),dict(body,object_id=I),dict(body,query='arbitrary'),dict(body,after='x'*513)]:
        assert not execute(node,prepare,dict(body=changed))['ok']
    comment=execute(node,prepare,dict(body=dict(operation='comments',object_id=I,after=None)))
    assert comment['ok'] and comment['value'][0]['json']['graphql']['variables']['id']==P
    assert 'project(id:$id)' in comment['value'][0]['json']['graphql']['query']
    assert I in comment['value'][0]['json']['graphql']['query']


def test_generated_response_validator_refuses_graphql_errors_actor_and_scope(node):
    _,validate=m.scripts(config());prior=dict(operation='issues',object_id=P)
    value=dict(data=dict(viewer=dict(id=A,organization=dict(id=O)),project=dict(id=P,
        issues=dict(nodes=[dict(id=I,project=dict(id=P),team=dict(id=T))],pageInfo=dict(hasNextPage=False,endCursor=None)))))
    assert execute(node,validate,value,prior)['ok']
    for fault in ('errors','actor','project','team','page'):
        changed=copy.deepcopy(value)
        if fault=='errors':changed['errors']=[dict(message='partial response')]
        if fault=='actor':changed['data']['viewer']['id']=I
        if fault=='project':changed['data']['project']['id']=I
        if fault=='team':changed['data']['project']['issues']['nodes'][0]['team']['id']=I
        if fault=='page':changed['data']['project']['issues']['pageInfo']['hasNextPage']='yes'
        assert not execute(node,validate,changed,prior)['ok']
