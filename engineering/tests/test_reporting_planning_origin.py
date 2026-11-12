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
const originQuery=planningOriginQuery(envelope,{app_user_id:id(3)});
assert.equal(originQuery.variables.id,id(5));assert.equal(originQuery.variables.actor,id(7));
assert.equal(planningIssueQuery(id(10)).variables.id,id(10));
assert.throws(()=>planningIssueQuery('not a UUID'));
let accepted=verifyPlanningOrigin(envelope,reply,policy,resolution);
assert.equal(accepted.permitted,true);assert.equal(accepted.human_approval_inferred,false);
assert.equal(accepted.origin.project_identifier,id(8));
const issueReply={statusCode:200,body:{data:{viewer:{id:id(3),organization:{id:id(1)}},
 issue:{id:id(10),identifier:'ENG-10',url:'https://linear.app/fixture/issue/ENG-10',team:{id:id(4)},project:{id:id(8)}}}}};
assert.equal(verifyPlanningIssue(accepted.origin,id(10),issueReply,policy).permitted,true);
for(const change of [
 x=>x.body.data.issue.project.id=id(9),x=>x.body.data.issue.team.id=id(9),
 x=>x.body.data.viewer.id=id(2),x=>x.body.data.issue.id=id(11),
 x=>x.body.data.issue.url='https://linear.app/fixture/issue/ENG-10?token=secret',
]) {const x=structuredClone(issueReply);change(x);assert.equal(verifyPlanningIssue(accepted.origin,id(10),x,policy).permitted,false);}
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
const ambiguous=structuredClone({envelope,reply,policy,resolution});ambiguous.envelope.action='created';
ambiguous.envelope.responsible_human_id=id(7);ambiguous.envelope.origin_comment_id='root';
ambiguous.reply.body.data.agentSession.sourceComment=null;ambiguous.reply.body.data.agentSession.sourceMetadata=null;
ambiguous.reply.body.data.agentSession.comment={id:'root',user:null};
ambiguous.reply.body.data.agentSession.creator={id:id(7),app:false};
assert.equal(verifyPlanningOrigin(ambiguous.envelope,ambiguous.reply,ambiguous.policy,ambiguous.resolution).permitted,false);
assert(!planningOriginQuery(envelope,{app_user_id:id(3)}).query.includes('isArtificialAgentSessionRoot'));
'''
    command=[node,'-e',script] if node else ['docker','exec','-i','n8n','node','-e',script]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
