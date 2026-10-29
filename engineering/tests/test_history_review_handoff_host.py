"""Pinned packet fixture tests; actual distinct UID custody requires sudo."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from test_engineering_history_local import module,DOC
from test_history_managed_review import inputs

p=module('review_handoff_package');driver=module('review_handoff_driver');probe=module('review_handoff_probe')
SOURCE=Path(__file__).resolve().parents[2]


@pytest.fixture
def candidate(tmp_path):
    repo=tmp_path/'source';repo.mkdir()
    for name in p.SOURCE_FILES:
        target=repo/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/name,target)
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.PIPE).decode().strip()
    git('init','-q');git('add','.');git('-c','user.name=Fixture','-c','user.email=f@invalid','-c','commit.gpgsign=false','commit','-qm','fixture')
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'synthetic.py').write_text('SYNTHETIC=True\n')
    dest=tmp_path/'candidate';result=p.build(repo,vendor,dest,git('rev-parse','HEAD'))
    return dest,result


def test_producer_and_receiver_bytes_pinned(candidate):
    dest,result=candidate;manifest,files=p.verify(dest,result['manifest_sha256'])
    for name in ('review_document_export','review_document_link','review_handoff_probe'):
        key='engineering/tools/rras_history/'+name+'.py';assert files[key]==(SOURCE/key).read_bytes()
    assert manifest['scope']=='isolated-synthetic-only' and result['root_mutations'] is False


@pytest.mark.parametrize('name',['../x','/etc/passwd','vendor//x','vendor/../x','vendor/e.pth','extra.py'])
def test_unsafe_fixture_path_refused(name):
    with pytest.raises(ValueError):p.safe_name(name)


@pytest.mark.parametrize('change',['source','scope','fifo'])
def test_changed_or_nonregular_fixture_refused(candidate,change):
    dest,result=candidate;target=dest/'engineering/tools/rras_history/review_document_export.py'
    if change=='source':target.write_text('changed')
    elif change=='fifo':target.unlink();os.mkfifo(target)
    else:
        path=dest/p.MANIFEST;value=json.loads(path.read_bytes());value['scope']='production';raw=p.encoded(value)
        path.write_bytes(raw);result['manifest_sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):p.verify(dest,result['manifest_sha256'])


@pytest.mark.parametrize('role,uid',[('seed',0),('export',0),('init',61111),('service',61111),('resume',1000),('denial',61113),('denial',996)])
def test_roles_have_fixed_network_identity_caps_and_groups(role,uid):
    args=driver.command(role,uid)
    assert args[args.index('--reuid')+1]==str(uid)
    for flag in ('--net','--clear-groups','--no-new-privs','--pdeathsig=TERM','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all'):assert flag in args


@pytest.mark.parametrize('role,uid',[('seed',1000),('resume',0),('denial',0),('launch',1000)])
def test_unknown_or_escalated_role_refused(role,uid):
    with pytest.raises(ValueError):driver.command(role,uid)


def test_generated_bootstrap_refuses_existing_scope_before_mutation(tmp_path,monkeypatch):
    path=tmp_path/'helper.py';sha=p.emit_helper(path);assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
    spec=importlib.util.spec_from_file_location('review_handoff_bootstrap',path);tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
    assert tool.STATE==driver.STATE==probe.STATE
    assert '/opt/rras-engineering/releases/native-10/venv/bin/python' in path.read_text()
    monkeypatch.setattr(tool.os,'getuid',lambda:0);monkeypatch.setattr(tool.os,'geteuid',lambda:0)
    monkeypatch.setattr(tool,'protected',lambda _:None);exists=tool.Path.exists
    monkeypatch.setattr(tool.Path,'exists',lambda value:True if value==tool.STATE else exists(value))
    monkeypatch.setattr(tool,'verify',lambda *_:pytest.fail('existing scope must refuse before payload read'))
    with pytest.raises(ValueError,match='preserve existing'):tool.stage(tmp_path,'a'*64)


def test_client_loss_resume_replay_uses_real_sqlite_only(inputs,tmp_path,monkeypatch):
    review,_,work,narrative=inputs;review['request']['repository_id']='example_library';work['body']['repository_id']='example_library'
    c=module('contract');rid=c.digest(c.encoded(review));package=module('managed_review').build(review,rid,work,narrative,DOC)
    packet=module('review_document_link').build({'work_request':work,'package':package})
    state=tmp_path/'fixture';state.mkdir(mode=0o700);(state/'client').mkdir(mode=0o700);(state/'history').mkdir(mode=0o700)
    handoff=state/'handoffs'/('document-'+'8'*32);handoff.mkdir(mode=0o700,parents=True)
    for name,value in (('packet.json',packet),('handoff.json',{'packet_sha256':c.digest(c.encoded(packet))})):
        path=handoff/name;path.write_bytes(c.encoded(value));path.chmod(0o600)
    history=module('store').Store(state/'history',create=True)
    def call(message):
        if message['method']=='submit':return history.submit(message['request'],peer_uid=os.getuid())
        if message['method']=='history':return history.history()
        assert message['method']=='document';raw,meta=history.document(message['document_id'],message['version'])
        return {'markdown':raw.decode(),'manifest':meta,'authority_granted':False}
    monkeypatch.setattr(probe,'STATE',state);monkeypatch.setattr(probe,'SERVICE',os.getuid());monkeypatch.setattr(probe,'CLIENT',os.getuid());monkeypatch.setattr(probe,'call',call)
    assert probe.client('lost-response')=={'pending_preserved':True}
    assert probe.client('resume')=={'exact_readback':True,'authority_granted':False}
    assert probe.client('replay')=={'history_records':2,'same_receipt_replay':True,'authority_granted':False}
