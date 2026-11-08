"""Fixed native identity handoff workflows; no OAuth tokens in generated source."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from test_reporting_native_handoff import fixture,m,uid


def configuration():
    policy,_,_,_=fixture()
    return dict(contract='native-handoff-n8n-config.v1',policy=policy,credentials=dict(postgres='fixture-pg',
        jarvis_oauth=dict(id='fixture-jarvis',type='linearOAuth2Api'),codex_oauth=dict(id='fixture-codex',type='oAuth2Api'),
        jarvis_header='fixture-jarvis-header',codex_header='fixture-codex-header'))


def test_workflows_keep_source_comment_and_recipient_session_credentials_separate():
    c=configuration();package=m.local('n8n_handoff').render(c)
    assert len(package['workflows'])==8 and not package['activation_authorized']
    for role in ('jarvis','codex'):
        recipient='codex' if role=='jarvis' else 'jarvis'
        for key,actor in [('comment',role),('session',recipient),('reconcile',recipient)]:
            w=package['workflows'][role+'_'+key]
            assert w['active'] is False and w['settings']['saveDataSuccessExecution']=='none'
            names={n['name'] for n in w['nodes']}
            for value in w['connections'].values():
                assert all(edge['node'] in names for branch in value['main'] for edge in branch)
            for node in w['nodes']:
                if node['type'].endswith('httpRequest'):
                    assert node['parameters']['url']=='https://api.linear.app/graphql'
                    ref=c['credentials'][actor+'_oauth'];assert node['credentials'][ref['type']]['id']==ref['id']
                    assert node['retryOnFail'] is False
    comment=package['workflows']['jarvis_comment']['nodes'][1]['parameters']['query']
    session=package['workflows']['jarvis_session']['nodes'][1]['parameters']['query']
    assert "comment_state='uncertain'" in comment and 'native_handoff_quiescence' in comment
    assert "session_state='uncertain'" in session and "session_state='pending'" in session
    assert "session_state='uncertain'" not in session.split('WHERE')[1].split('UPDATE')[0]


def test_actual_code_validates_prose_and_builds_exact_same_frozen_comment():
    c=configuration();policy,context,args,intent=fixture()
    args['limitations']=['Unicode café, tools failed','Do not infer approval.'];args['summary']='@Codex *source* (café)'
    intent=m.prepare(policy,'jarvis',context,args);source=Path(m.__file__).with_name('n8n_native_handoff.js').read_text()
    node=shutil.which('node');installed=importlib.util.find_spec('playwright')
    if not node and installed:node=str(Path(installed.origin).parent/'driver/node')
    if not node:pytest.skip('Node is required for actual n8n Code execution')
    package=m.local('n8n_handoff').render(c)
    script=source+"""
const assert=require('node:assert/strict'),fs=require('node:fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));
assert.equal(validateHandoff(input.intent,input.policy,'jarvis').comment_body,input.comment_body);
assert.throws(()=>validateHandoff({...input.intent,recipient:'jarvis'},input.policy,'jarvis'));
assert.throws(()=>validateHandoff({...input.intent,human_approval_inferred:true},input.policy,'jarvis'));
for(const w of Object.values(input.workflows))for(const n of w.nodes){
 if(n.type.endsWith('.code'))new Function('$input','$',n.parameters.jsCode);
 if(n.type.endsWith('.postgres')&&n.parameters.options.queryReplacement)new Function('$json','return '+n.parameters.options.queryReplacement.slice(3,-2));
}
console.log('handoff-code-passed');
"""
    result=subprocess.run([node,'-e',script],input=json.dumps(dict(intent=intent,policy=policy,comment_body=m.comment_body(intent),workflows=package['workflows'])),
        text=True,capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('kind',['shared_identity','shared_credential','unknown_type','unknown_policy'])
def test_incomplete_or_shared_agent_configuration_refused(kind):
    c=configuration()
    if kind=='shared_identity':c['policy']['agents']['jarvis']=c['policy']['agents']['codex']
    if kind=='shared_credential':c['credentials']['jarvis_oauth']['id']=c['credentials']['codex_oauth']['id']
    if kind=='unknown_type':c['credentials']['jarvis_oauth']['type']='unreviewed'
    if kind=='unknown_policy':c['policy']['extra_authority']=True
    with pytest.raises(ValueError):m.local('n8n_handoff').render(c)
