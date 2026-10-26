"""Offline pinned fixture checks; real ownership/systemd acceptance needs sudo."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch
import pytest
import test_history_document_approval as adapter

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    path=ROOT/'tools/rras_native'/(name+'.py')
    spec=importlib.util.spec_from_file_location('test_document_host_'+name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


p=module('document_host_package')


@pytest.fixture
def committed(tmp_path):
    release=module('prepare_workflow_release');repo=tmp_path/'source';repo.mkdir()
    prefix='engineering/tools/rras_native/'
    names=[prefix+name for name in (*release.MODULES,*release.ASSETS)]+list(release.DOCUMENT_FILES)
    names += [prefix+name+'.py' for name in ('probe_approved_launch','probe_workflow_host','document_host_cases','probe_document_approval')]
    names+=['engineering/contracts/workflow-v1.schema.json','engineering/contracts/examples/library-managed.json']
    for name in names:
        target=repo/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT.parent/name,target)
    def git(*args):return subprocess.run(['git','-C',str(repo),*args],capture_output=True,check=True).stdout.decode().strip()
    git('init','-q');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','fixture')
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'fixture.py').write_text('SYNTHETIC=True\n')
    return repo,git('rev-parse','HEAD'),vendor,git


@pytest.fixture
def candidate(committed,tmp_path):
    repo,commit,vendor,_=committed;dest=tmp_path/'candidate';result=p.build(repo,vendor,dest,commit)
    return dest,result


def test_committed_package_exact_fake_runner_and_dependencies(candidate):
    dest,result=candidate;manifest,files=p.verify(dest,result['manifest_sha256'])
    worker=files['engineering/tools/rras_native/manual_runner.py']
    assert worker==p.fake_worker(files) and b'RRAS-APPROVAL-OFFLINE-FIXTURE' in worker
    assert b'from hermes' not in worker and result['root_mutations'] is False
    for name in ('document_approval','document_host_cases','probe_document_approval'):
        assert 'engineering/tools/rras_native/'+name+'.py' in files
    assert 'engineering/tools/rras_history/managed_review.py' in files
    assert manifest['scope']=='isolated-synthetic-only'


def test_uncommitted_source_cannot_enter_payload(committed,tmp_path):
    repo,commit,vendor,_=committed
    source=repo/'engineering/tools/rras_native/document_approval.py';original=source.read_bytes();source.write_text('UNCOMMITTED_PRIVATE_FIXTURE')
    dest=tmp_path/'candidate';result=p.build(repo,vendor,dest,commit)
    assert (dest/'engineering/tools/rras_native/document_approval.py').read_bytes()==original


@pytest.mark.parametrize('name',['../escape','/etc/passwd','vendor//x','vendor/../x','vendor/site.pth','vendor/__pycache__/x.pyc','entry.py'])
def test_payload_path_refusal(name):
    with pytest.raises(ValueError):p.safe_name(name)


@pytest.mark.parametrize('change',['payload','symlink','hardlink','fifo','scope','real_runner'])
def test_changed_candidate_refused(candidate,change):
    dest,result=candidate;target=dest/'engineering/tools/rras_native/manual_runner.py'
    manifest=json.loads((dest/p.MANIFEST).read_bytes())
    if change=='payload':target.write_text('different')
    elif change=='symlink':target.unlink();target.symlink_to(dest/p.MANIFEST)
    elif change=='hardlink':os.link(target,dest/'other')
    elif change=='fifo':target.unlink();os.mkfifo(target)
    elif change=='scope':manifest['scope']='production'
    elif change=='real_runner':
        target.write_bytes((ROOT/'tools/rras_native/manual_runner.py').read_bytes())
        manifest['files']['engineering/tools/rras_native/manual_runner.py']=hashlib.sha256(target.read_bytes()).hexdigest()
    if change in ('scope','real_runner'):
        raw=p.encoded(manifest);(dest/p.MANIFEST).write_bytes(raw);result['manifest_sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises((ValueError,OSError)):p.verify(dest,result['manifest_sha256'])


def test_stdlib_helper_paths_and_existing_fixture_refusal(tmp_path,monkeypatch):
    path=tmp_path/'helper.py';sha=p.emit_helper(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
    s=importlib.util.spec_from_file_location('document_bootstrap',path);tool=importlib.util.module_from_spec(s);s.loader.exec_module(tool)
    assert tool.STATE==p.STATE==module('probe_document_approval').STATE
    monkeypatch.setattr(tool.os,'getuid',lambda:0);monkeypatch.setattr(tool.os,'geteuid',lambda:0)
    monkeypatch.setattr(tool,'protected',lambda _:None)
    exists=tool.Path.exists
    monkeypatch.setattr(tool.Path,'exists',lambda value:True if value==p.STATE else exists(value))
    monkeypatch.setattr(tool,'verify',lambda *_:pytest.fail('existing fixture must refuse before mutation'))
    with pytest.raises(ValueError,match='preserve existing'):tool.stage(tmp_path,'a'*64)


def test_helper_refuses_unprivileged_before_candidate_reads(tmp_path,monkeypatch):
    path=tmp_path/'helper.py';p.emit_helper(path)
    s=importlib.util.spec_from_file_location('document_bootstrap_unprivileged',path);tool=importlib.util.module_from_spec(s);s.loader.exec_module(tool)
    monkeypatch.setattr(tool.os,'getuid',lambda:1000)
    with pytest.raises(ValueError,match='sudo'):tool.stage(tmp_path,'a'*64)


def test_document_case_logic_with_real_git_and_fake_service(tmp_path):
    # Mock root custody only, as in the source adapter suite. No sudo/model call.
    x=adapter.DocumentApprovalTests();x.setUp();cases=module('document_host_cases');original=cases.local
    try:
        with patch.object(cases,'local',side_effect=lambda name:x.d if name=='document_approval' else x.approval if name=='approval' else original(name)),\
             patch.object(adapter.m.os,'getuid',return_value=0):
            bundle=cases.initialize(adapter.m,x.state,x.captured,x.config_path,x.work)
        cases.local=lambda name:x.d if name=='document_approval' else x.approval if name=='approval' else original(name)
        def invoke(auth):return x.invoke(auth)[0]
        result=cases.negative_launches(invoke,x.state,x.captured,x.config_path,bundle,x.jobs)
        assert len(result)==5 and list(x.jobs.iterdir())==[]
        assert x.invoke(bundle['first']['authorization_id'])[0]['host_stop_verified'] is True
        assert x.invoke(bundle['legacy']['authorization_id'])[0]['host_stop_verified'] is True
    finally:x.doCleanups()
