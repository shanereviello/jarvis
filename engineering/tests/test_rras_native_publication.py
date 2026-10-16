import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('publisher',ROOT/'tools/rras_native/publication.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
a=m.local('activity')

def git(root,*args):
    return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-C',str(root),*args],stderr=subprocess.DEVNULL)

@pytest.fixture
def fixture(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();git(repo,'init','-q');git(repo,'config','user.name','Test');git(repo,'config','user.email','test@localhost')
    (repo/'calc.py').write_text('value = 1\n');git(repo,'add','.');git(repo,'commit','-qm','baseline')
    baseline=git(repo,'rev-parse','HEAD').decode().strip()
    (repo/'calc.py').write_text('value = 2\n');patch=git(repo,'diff','--binary');git(repo,'checkout','--','calc.py')
    request=dict(schema_version=1,task_id='TASK-fixture',repository_id='jarvis',objective='change value',allowed_paths=['calc.py'],validation_argv=['/usr/bin/true'],worker_timeout_seconds=30,validation_timeout_seconds=10,commit_policy='leave_uncommitted')
    review=dict(request=request,baseline_commit=baseline,canonical_repository=str(repo))
    host=dict(review_id=a.digest(a.encoded(review)),service_exit=0,host_stop_verified=True,work=str(tmp_path/'run/work'))
    workspace=str(tmp_path/'run/repo/.worktrees/task')
    files={'changes.patch':patch,'additional-artifact-0.json':b'{}','additional-artifact-1.json':a.encoded(request)}
    manifest=dict(worktree=workspace,task=dict(task_id='TASK-fixture',repository_id='jarvis',baseline_commit=baseline),head_commit=baseline,binding=dict(hermes_task='t_one',hermes_run='1'),files={k:dict(sha256=a.digest(v),size_bytes=len(v)) for k,v in files.items()})
    evidence=dict(workspace=workspace,export=dict(export_id=a.digest(a.encoded(manifest))),native_task='t_one',native_run=1,wait=dict(worker_stop_verified=True),validation_exit=0,validation_stop_verified=True,success=True)
    policy=json.loads((ROOT/'config/publication-policy.json').read_text())
    return dict(canonical=repo,destination=tmp_path/'publication',policy=policy,assigned_branch='codex/task-fixture',review=review,host_result=host,evidence=evidence,manifest=manifest,files=files)

def test_commit_and_exact_local_push(fixture,tmp_path):
    result=m.prepare(**fixture)
    assert (Path(result['checkout'])/'calc.py').read_text()=='value = 2\n'
    assert git(fixture['canonical'],'rev-parse','HEAD').decode().strip()==result['baseline']
    remote=tmp_path/'remote.git';subprocess.run(['git','init','--bare','-q',str(remote)],check=True)
    result['remote']=str(remote)  # local transport fixture only
    subprocess.run(m.push_argv(result),check=True,capture_output=True)
    assert git(remote,'rev-parse','refs/heads/codex/task-fixture').decode().strip()==result['commit']
    assert git(remote,'show-ref').decode().count('\n')==1

@pytest.mark.parametrize('kind',['altered','failed','stop','scope','binding','baseline','branch'])
def test_refusals(fixture,kind):
    if kind=='altered':fixture['files']['changes.patch']+=b'corruption'
    if kind=='failed':fixture['evidence']['success']=False
    if kind=='stop':fixture['host_result']['host_stop_verified']=False
    if kind=='scope':
        fixture['review']['request']['allowed_paths']=['other.py']
        fixture['host_result']['review_id']=a.digest(a.encoded(fixture['review']))
    if kind=='binding':fixture['evidence']['native_task']='t_other'
    if kind=='baseline':fixture['manifest']['head_commit']='0'*40
    if kind=='branch':fixture['assigned_branch']='main'
    with pytest.raises(ValueError):m.prepare(**fixture)

def test_conflicting_remote_history_refuses_nonforced_push(fixture,tmp_path):
    result=m.prepare(**fixture);remote=tmp_path/'remote.git';subprocess.run(['git','init','--bare','-q',str(remote)],check=True)
    result['remote']=str(remote);subprocess.run(m.push_argv(result),check=True,capture_output=True)
    git(fixture['canonical'],'checkout','-qb','codex/task-fixture')
    (fixture['canonical']/'other').write_text('other');git(fixture['canonical'],'add','.');git(fixture['canonical'],'commit','-qm','divergent')
    pushed=subprocess.run(['git','-C',str(fixture['canonical']),'push',str(remote),'HEAD:refs/heads/codex/task-fixture'],capture_output=True)
    assert pushed.returncode!=0
    assert '--force' not in m.push_argv(result)

def test_new_file_content_is_hash_bound(fixture):
    import base64
    fixture['review']['request']['allowed_paths'].append('new.txt')
    fixture['host_result']['review_id']=a.digest(a.encoded(fixture['review']))
    fixture['files']['additional-artifact-0.json']=a.encoded({'new.txt':base64.b64encode(b'reviewed new content\n').decode()})
    fixture['files']['additional-artifact-1.json']=a.encoded(fixture['review']['request'])
    fixture['manifest']['files']={k:dict(sha256=a.digest(v),size_bytes=len(v)) for k,v in fixture['files'].items()}
    fixture['evidence']['export']['export_id']=a.digest(a.encoded(fixture['manifest']))
    result=m.prepare(**fixture)
    assert (Path(result['checkout'])/'new.txt').read_bytes()==b'reviewed new content\n'

def test_push_refspec_tampering_refused():
    with pytest.raises(ValueError):m.push_argv(dict(branch='codex/task-one',refspec='HEAD:refs/heads/main'))

def test_existing_publication_directory_preserved(fixture):
    fixture['destination'].mkdir();(fixture['destination']/'retained').write_text('keep')
    with pytest.raises(ValueError):m.prepare(**fixture)
    assert (fixture['destination']/'retained').read_text()=='keep'

def test_selected_dev_baseline_preserves_pr_target(fixture):
    fixture['review']['baseline_ref']='refs/remotes/origin/dev'
    fixture['host_result']['review_id']=a.digest(a.encoded(fixture['review']))
    result=m.prepare(**fixture)
    assert result['pr_base_branch']=='dev'
