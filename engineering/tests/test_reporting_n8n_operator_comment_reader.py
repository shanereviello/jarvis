import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from test_reporting_n8n_codex import config,uid

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/n8n_operator_comment_reader.py'
spec=importlib.util.spec_from_file_location('operator_comment_reader_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_inactive_reader_has_separate_header_and_no_retry(config):
    workflow=module.render(config,'operator-private',[uid(30)],[uid(31)])
    assert not workflow['active'] and workflow['settings']['saveDataSuccessExecution']=='none'
    nodes={x['name']:x for x in workflow['nodes']}
    assert nodes['Private operator comment']['parameters']['authentication']=='headerAuth'
    assert nodes['Read native comment']['retryOnFail'] is False
    with pytest.raises(ValueError):module.render(config,config['credentials']['runtime_header'],[uid(30)],[uid(31)])
    with pytest.raises(ValueError):module.render(config,'operator-private',[uid(30)],[config['app_user_id']])


def test_generated_comment_validation_refuses_bot_and_missing_fields(config):
    node=shutil.which('node')
    if not node and os.environ.get('SHRR_NODE_DOCKER')!='1':pytest.skip('Node required')
    workflow=module.render(config,'operator-private',[uid(30)],[uid(31)])
    scripts=[n['parameters']['jsCode'] for n in workflow['nodes'] if n['type'].endswith('.code')]
    reply={'statusCode':200,'body':{'data':{'viewer':{'id':config['app_user_id'],'organization':{'id':config['organization_id']}},
      'comment':{'id':uid(32),'body':'fixture','createdAt':'fixture','editedAt':None,'archivedAt':None,'botActor':None,'externalUser':None,
       'onBehalfOf':None,'user':{'id':uid(31),'app':False},'issue':{'id':uid(33),'team':{'id':uid(30)},'project':{'id':uid(34)}}}}}}
    program='''const scripts=SCRIPTS;for(const s of scripts)new Function('$input','$',s);
const fn=new Function('$input','$',scripts[1]);const reply=REPLY;
const input={first:()=>({json:reply})};const saved=()=>({first:()=>({json:{comment_id:ID}})});
if(!fn(input,saved)[0].json.permitted)throw Error('valid comment rejected');
reply.body.data.comment.botActor={type:'oauthClient'};if(fn(input,saved)[0].json.permitted)throw Error('bot accepted');
reply.body.data.comment.botActor=null;delete reply.body.data.comment.onBehalfOf;
if(fn(input,saved)[0].json.permitted)throw Error('incomplete response accepted');'''.replace('SCRIPTS',json.dumps(scripts)).replace('REPLY',json.dumps(reply)).replace('ID',json.dumps(uid(32)))
    command=[node,'-e',program] if node else ['docker','exec','-i','n8n','node','-e',program]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
