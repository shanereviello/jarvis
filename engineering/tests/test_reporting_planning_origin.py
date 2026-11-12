"""Native-origin acceptance is planning only; no human approval is inferred."""
import json
import os
import shutil
import subprocess
from pathlib import Path
import pytest


def test_planning_origin_distinguishes_human_app_scope_and_project():
    node=shutil.which('node')
    if not node and os.environ.get('SHRR_NODE_DOCKER')!='1':pytest.skip('Node required for the actual n8n verifier')
    source=(Path(__file__).resolve().parents[1]/'tools/rras_reporting/n8n_planning_origin.js').read_text()
    script=source+r'''
const assert=require('assert');
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const policy={organization_id:id(1),agents:{jarvis:id(2),codex:id(3)},team_ids:[id(4)],scopes:[{kind:'repository',id:'jarvis'}]};
const envelope={agent:'codex',action:'prompted',session_id:id(5),issue_id:id(6),source_actor_id:id(7)};
const reply={statusCode:200,body:{data:{viewer:{id:id(3),organization:{id:id(1)}},sourceActor:{id:id(7),app:false},
 agentSession:{id:id(5),appUser:{id:id(3)},issue:{id:id(6),team:{id:id(4)},project:{id:id(8),url:'https://linear.app/fixture/project/test'}}}}}};
const resolution={organization_id:id(1),project_id:id(8),scope:{kind:'repository',id:'jarvis'}};
let accepted=verifyPlanningOrigin(envelope,reply,policy,resolution);
assert.equal(accepted.permitted,true);assert.equal(accepted.human_approval_inferred,false);
assert.equal(accepted.origin.project_identifier,id(8));
for(const change of [
 x=>x.reply.body.data.sourceActor.app=true,
 x=>x.reply.body.data.sourceActor.id=id(2),
 x=>x.reply.body.data.viewer.id=id(2),
 x=>x.reply.body.data.agentSession.issue.project.id=id(9),
 x=>x.reply.body.data.agentSession.issue.team.id=id(9),
 x=>x.resolution.scope.id='other',
 x=>x.envelope.issue_id=id(9),
 x=>x.reply.body.data.agentSession.issue.project.url='https://linear.app/fixture/project?a=secret',
]) {const x=structuredClone({envelope,reply,policy,resolution});change(x);
 assert.equal(verifyPlanningOrigin(x.envelope,x.reply,x.policy,x.resolution).permitted,false);}
const created=structuredClone({envelope,reply,policy,resolution});created.envelope.action='created';
created.envelope.origin_comment_id='comment';created.reply.body.data.agentSession.sourceComment={id:'comment',user:{id:id(7),app:false}};
assert.equal(verifyPlanningOrigin(created.envelope,created.reply,created.policy,created.resolution).permitted,true);
created.reply.body.data.agentSession.sourceComment.user.app=true;
assert.equal(verifyPlanningOrigin(created.envelope,created.reply,created.policy,created.resolution).permitted,false);
'''
    command=[node,'-e',script] if node else ['docker','exec','-i','n8n','node','-e',script]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
