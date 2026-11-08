"""Execute actual n8n origin-verification JavaScript against native response DTOs."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from test_reporting_native_handoff import fixture,uid,m


def test_native_human_context_and_correlated_agent_origin_are_distinct():
    node=shutil.which('node');installed=importlib.util.find_spec('playwright')
    if not node and installed:node=str(Path(installed.origin).parent/'driver/node')
    if not node:pytest.skip('Node is required to execute the n8n Code contract')
    policy,ctx,args,intent=fixture()
    origin_policy=dict(organization_id=policy['organization_id'],app_user_id=policy['agents']['codex'],
        agent_actor_ids=list(policy['agents'].values()),issues=policy['issues'])
    envelope=dict(action='created',session_id=uid(60),issue_id=uid(4),binding=ctx['binding'],origin_comment_id=None)
    response=dict(statusCode=200,body=dict(data=dict(viewer=dict(id=policy['agents']['codex'],organization=dict(id=uid(1))),
        agentSession=dict(id=uid(60),appUser=dict(id=policy['agents']['codex']),issue=dict(id=uid(4)),
            creator=dict(id=uid(6),app=False),comment=None,sourceComment=None))))
    handoff=dict(id=intent['id'],organization_id=uid(1),body=intent,comment_id=intent['comment_id'],
        comment_state='confirmed',session_state='uncertain',source_quiescence=dict(state='completed'),state='requested',target_session_id=None)
    source=Path(m.__file__).with_name('n8n_native_origin.js').read_text()
    script=source+"""
const assert=require('node:assert/strict'),fs=require('node:fs');
const {policy,e,r,h}=JSON.parse(fs.readFileSync(0,'utf8'));
assert.equal(verifyOrigin(e,r,policy).permitted,true);
assert.equal(verifyOrigin(e,r,policy).observation.human_approval_inferred,false);
const unknown=structuredClone(r);unknown.body.data.agentSession.creator=null;
assert.equal(verifyOrigin(e,unknown,policy).permitted,false);
const agent=structuredClone(r);agent.body.data.agentSession.sourceComment={id:h.comment_id,user:{id:h.body.sender_app_user_id,app:true}};
// A human creator does not turn an agent's source comment into a human request.
assert.equal(verifyOrigin(e,agent,policy).permitted,false);
const accepted=verifyOrigin(e,agent,policy,h);assert.equal(accepted.permitted,true);
assert.equal(accepted.correlated_handoff_id,h.id);
for(const mutate of [x=>x.h.target_session_id='wrong',x=>x.h.body.binding.architecture_version=99,
 x=>x.h.comment_state='uncertain',x=>x.h.source_quiescence=null,x=>x.h.body.sender_app_user_id=policy.app_user_id,
 x=>x.r.body.data.viewer.id=h.body.sender_app_user_id,x=>x.r.body.data.agentSession.issue.id='wrong']){
 const x=structuredClone({e,r:agent,h});mutate(x);assert.equal(verifyOrigin(x.e,x.r,policy,x.h).permitted,false);
}
const prompt={...e,action:'prompted',source_actor_id:'human'};
const nativePrompt=structuredClone(r);nativePrompt.body.data.sourceActor={id:'human',app:false};
assert.equal(verifyOrigin(prompt,nativePrompt,policy).permitted,true);
nativePrompt.body.data.sourceActor.app=true;assert.equal(verifyOrigin(prompt,nativePrompt,policy).permitted,false);
console.log('native-origin-cases-passed');
"""
    result=subprocess.run([node,'-e',script],input=json.dumps(dict(policy=origin_policy,e=envelope,r=response,h=handoff)),text=True,capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='native-origin-cases-passed'
