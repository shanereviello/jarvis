"""Finish-to-local-Git handoff plus imported publication receipts; no GitHub/model."""
import json
import os
from pathlib import Path
import pwd
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from test_workflow_finish import case
import test_managed_events as managed

pytestmark=pytest.mark.parametrize('case',[{'publication_remote':'git@github.com:fixture/library.git'}],indirect=True)


@pytest.fixture
def pubcase(case):
    c=case;p=managed.module('workflow_publication');a=c.x.a
    # Use actual applicable patch bytes for the admitted fixture repository.
    (c.x.repo/'src/library.py').write_text('value = 2\n');diff=c.x.git('diff','--binary').encode();c.x.git('checkout','--','src/library.py')
    manifest=json.loads(c.reads[c.directory/'manifest.json']);manifest['files']['changes.patch']={'sha256':a.digest(diff),'size_bytes':len(diff)};manifest['files']['additional-artifact-0.json']={'sha256':a.digest(b'{}'),'size_bytes':2}
    export_id=a.digest(a.encoded(manifest));directory=c.root/'index'/c.review['request']['task_id']/'exports'/export_id
    for name in manifest['files']:
        c.reads[directory/name]=diff if name=='changes.patch' else b'{}' if name=='additional-artifact-0.json' else c.reads[c.directory/name]
    c.reads[directory/'manifest.json']=a.encoded(manifest);c.evidence['export']={'export_id':export_id,'path':str(directory)}
    c.reads[c.root/'evidence.json']=a.encoded(c.evidence);c.capture()
    uid=os.getuid();operator=pwd.getpwuid(uid).pw_name;root=c.x.root
    policy={'schema_version':1,'review_branch_publication':'standing-authorized','repositories':{'example_library':{'remote':'git@github.com:fixture/library.git','default_branch':'main'}},'branch_prefix':'codex/','human_required_actions':['merge','deploy']}
    policy_path=root/'policy.json';policy_path.write_bytes(a.encoded(policy));package=root/'handoff';destination=root/'prepared'
    reader=SimpleNamespace(root_bytes=lambda path,limit:Path(path).read_bytes())
    hf=managed.module('publication_handoff');hf_local=hf.local;p_local=p.local
    patches=[patch.object(p,'local',side_effect=lambda name:{'workflow_finish':c.f,'publication_custody':reader,'publication_handoff':hf,'approved_launch':c.x.l,'managed_events':c.x.e}.get(name) or p_local(name)),patch.object(hf,'local',side_effect=lambda name:{'publication_custody':reader,'approved_launch':c.x.l}.get(name) or hf_local(name))]
    for patcher in patches:patcher.start()
    try:
        with patch.object(p.os,'getuid',return_value=0),patch.object(p.os,'geteuid',return_value=0):
            prepared=p.prepare(c.custody,policy_path,destination,package,operator)
        record=json.loads((package/'handoff.json').read_bytes());proof=record['prepared']
        workspace=root/'operator';workspace.mkdir(mode=0o700)
        identity={k:proof[k] for k in ('repository_id','remote','branch','refspec','commit','baseline','export_id')};identity.update(schema_version=1,merge_authorized=False,deploy_authorized=False)
        transport=dict(identity,status='published',remote_write_attempted=True)
        (workspace/'publication-receipt.json').write_bytes(a.encoded(transport));(workspace/'publication-receipt.json').chmod(0o600)
        (workspace/'publication-receipt.json.started').write_bytes(a.encoded(identity));(workspace/'publication-receipt.json.started').chmod(0o600)
        pr={'schema_version':1,'repository':'fixture/library','head_repository':'fixture/library','head_branch':proof['branch'],'head_commit':proof['commit'],'base_branch':'main','number':7,'url':'https://github.com/fixture/library/pull/7','draft':True,'merged':False,'state':'open'}
        pr_path=workspace/'pr.json';pr_path.write_bytes(a.encoded(pr));pr_path.chmod(0o600)
        # Ownership/ancestor boundary mocked only here: tmp fixtures are caller-owned.
        read=lambda path,identity,limit=1024*1024:Path(path).read_bytes()
        with patch.object(p,'operator_bytes',side_effect=read):
            def capture(path,with_pr=True):
                with patch.object(p.os,'getuid',return_value=0),patch.object(p.os,'geteuid',return_value=0):return p.capture(c.custody,package,workspace,path,pr_path if with_pr else None)
            def journal(path):
                with patch.object(p.os,'getuid',return_value=0),patch.object(p.os,'geteuid',return_value=0):return p.record(c.custody,path)
            yield SimpleNamespace(c=c,p=p,root=root,workspace=workspace,pr=pr,pr_path=pr_path,proof=proof,transport=transport,package=package,capture=capture,record=journal,prepared=prepared)
    finally:
        for patcher in reversed(patches):patcher.stop()


def test_local_review_commit_and_imported_branch_pr_facts(pubcase):
    x=pubcase;assert (x.root/'prepared/src/library.py').read_text()=='value = 2\n'
    out=x.root/'publication-custody';assert x.capture(out)['draft_pr_captured'];assert x.record(out)['draft_pr_recorded']
    events=x.c.x.events();assert events[-2]['event_type']=='branch.published' and events[-1]['event_type']=='pull_request.opened'
    assert all(e['provenance']['kind']=='imported' for e in events[-2:])
    assert x.c.x.store.status()['work_items'][0]['release_status']=='not_inferred'
    count=len(events);x.record(out);assert len(x.c.x.events())==count
    assert not x.prepared['remote_contacted']


def test_pr_can_be_recorded_later_without_duplicate_branch(pubcase):
    x=pubcase;first=x.root/'first';x.capture(first,False);x.record(first)
    second=x.root/'second';x.capture(second,True);x.record(second)
    assert len([e for e in x.c.x.events() if e['event_type']=='branch.published'])==1
    assert len([e for e in x.c.x.events() if e['event_type']=='pull_request.opened'])==1


def test_unknown_push_stays_uncertain_and_does_not_retry(pubcase):
    x=pubcase;x.transport.update(status='unknown',error_type='TimeoutError')
    (x.workspace/'publication-receipt.json').write_bytes(x.c.x.a.encoded(x.transport))
    out=x.root/'unknown';x.capture(out,False);result=x.record(out)
    assert result['reported_branch_status']=='unknown' and not result['remote_contacted']
    assert x.c.x.events()[-1]['event_type']=='recovery.recorded'
    with pytest.raises(ValueError):x.capture(x.root/'bad-pr',True)


@pytest.mark.parametrize('field,value',[('head_commit','0'*40),('head_branch','main'),('base_branch','wrong'),('draft',False),('merged',True),('state','closed'),('head_repository','other/library'),('number',True),('url','https://github.com/other/library/pull/7')])
def test_wrong_pr_refused_before_capture(pubcase,field,value):
    x=pubcase;x.pr[field]=value;x.pr_path.write_bytes(x.c.x.a.encoded(x.pr));out=x.root/'bad'
    with pytest.raises(ValueError):x.capture(out)
    assert not out.exists()


@pytest.mark.parametrize('field,value',[('commit','0'*40),('remote','git@github.com:other/library.git'),('merge_authorized',True),('deploy_authorized',True),('remote_write_attempted',False)])
def test_wrong_transport_refused(pubcase,field,value):
    x=pubcase;x.transport[field]=value;(x.workspace/'publication-receipt.json').write_bytes(x.c.x.a.encoded(x.transport))
    with pytest.raises(ValueError):x.capture(x.root/'bad',False)


def test_changed_capture_refused_before_journal(pubcase):
    x=pubcase;out=x.root/'out';x.capture(out);(out/'transport.json').write_bytes(b'{}')
    before=len(x.c.x.events())
    with pytest.raises(ValueError):x.record(out)
    assert len(x.c.x.events())==before


def test_private_publication_details_omitted_from_projection(pubcase):
    x=pubcase;out=x.root/'out';x.capture(out);x.record(out)
    view=x.root/'view.json';x.c.x.store.publish_jarvis(view,x.c.x.work['work_item_id']);raw=view.read_bytes()
    assert str(x.root).encode() not in raw and b'git@github.com' not in raw and b'operator_only' not in raw
    assert b'branch.published' in raw and b'pull_request.opened' in raw


def test_operator_reader_refuses_worker_identity_symlink_and_broad_modes(pubcase):
    x=pubcase;reader=managed.module('workflow_publication').operator_bytes
    with pytest.raises(ValueError):reader(x.pr_path,996)
    link=x.workspace/'link';link.symlink_to(x.pr_path)
    with pytest.raises(ValueError):reader(link,os.getuid())
    # /tmp fixture ancestry is intentionally inadmissible to the actual reader.
    with pytest.raises(ValueError):reader(x.pr_path,os.getuid())


def test_record_does_not_reread_mutable_operator_workspace(pubcase):
    x=pubcase;out=x.root/'out';x.capture(out)
    (x.workspace/'publication-receipt.json').write_bytes(b'{}');x.pr_path.write_bytes(b'{}')
    assert x.record(out)['draft_pr_recorded']


def test_partial_pr_journal_write_repairs_without_duplicate_branch(pubcase):
    x=pubcase;out=x.root/'out';x.capture(out);store=x.c.x.store;original=store.append;failures=[]
    def append(*args,**kwargs):
        event=kwargs.get('transition')
        if event and event[0]['event_type']=='pull_request.opened' and not failures:
            failures.append(True);raise OSError('fixture interrupted append')
        return original(*args,**kwargs)
    with patch.object(x.c.x.e,'journal',return_value=store),patch.object(store,'append',side_effect=append):
        with pytest.raises(OSError):x.record(out)
        x.record(out)
    assert len([e for e in x.c.x.events() if e['event_type']=='branch.published'])==1
    assert len([e for e in x.c.x.events() if e['event_type']=='pull_request.opened'])==1


def test_policy_remote_mismatch_blocks_preparation_before_git(pubcase):
    x=pubcase;path=x.root/'wrong-policy.json';policy=json.loads((x.root/'policy.json').read_bytes())
    policy['repositories']['example_library']['remote']='git@github.com:other/library.git';path.write_bytes(x.c.x.a.encoded(policy))
    destination=x.root/'bad-prepared'
    with patch.object(x.p.os,'getuid',return_value=0),patch.object(x.p.os,'geteuid',return_value=0),pytest.raises(ValueError):
        x.p.prepare(x.c.custody,path,destination,x.root/'bad-package','fixture')
    assert not destination.exists()
