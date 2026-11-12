import os
from pathlib import Path
import shutil
import subprocess
import pytest


def test_unmapped_planning_event_never_becomes_execution_binding():
    node=shutil.which('node')
    if not node and os.environ.get('SHRR_NODE_DOCKER')!='1':pytest.skip('Node required')
    root=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
    script=(root/'n8n_codex_admission.js').read_text()+'\n'+(root/'n8n_codex_planning_admission.js').read_text()+r'''
const assert=require('assert');
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const policy={planning_enabled:true,organization_id:id(1),app_user_id:id(2),oauth_client_id:'a'.repeat(32),agent_actor_ids:[id(2),id(3)],issues:{}};
const input={headers:{'x-rras-codex-verified':'v1','x-rras-codex-body-sha256':'a'.repeat(64),'linear-delivery':id(4)},
 body:{type:'AgentSessionEvent',action:'prompted',webhookTimestamp:1000,organizationId:id(1),
 agentSession:{id:id(5),issueId:id(6)},agentActivity:{id:id(7),userId:id(8),content:{type:'prompt',body:'Draft a design'}}}};
const out=admitPlanning(input,policy,1000);
assert.equal(out.envelope.contract,'codex-planning-event.v1');assert.equal(out.envelope.mode,'planning');
assert.equal(Object.hasOwn(out.envelope,'binding'),false);
assert.throws(()=>admit(input,policy,1000));
assert.throws(()=>admitPlanning(input,{...policy,planning_enabled:false},1000));
assert.throws(()=>admitPlanning(input,{...policy,issues:{[id(6)]:{}}},1000));
const bad=structuredClone(input);bad.headers['x-rras-codex-verified']='no';
assert.throws(()=>admitPlanning(bad,policy,1000));
'''
    command=[node,'-e',script] if node else ['docker','exec','-i','n8n','node','-e',script]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
