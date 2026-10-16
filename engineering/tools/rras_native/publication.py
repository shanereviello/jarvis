"""Trusted, credential-free review commit preparation from captured export bytes.

Caller must capture inputs after host stop into operator-owned custody. Never run
this against the mutable worker checkout. Remote credentials belong only to the
separate operator publication process. No merge, force push, or lifecycle edits.
"""
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def prepare(canonical, destination, policy, assigned_branch, review, host_result, evidence, manifest, files):
    a=local('activity');planner=local('publication_policy')
    request=local('task_contract').validate_request(review['request']);baseline=review['baseline_commit']
    if str(Path(canonical))!=review['canonical_repository'] or str(Path(evidence['workspace']).parent.parent)!=str(Path(host_result['work']).parent/'repo'):
        raise ValueError('canonical or launch workspace mismatch')
    if host_result['review_id']!=a.digest(a.encoded(review)) or host_result['service_exit']!=0:
        raise ValueError('launch review/result mismatch')
    if evidence['workspace']!=manifest['worktree'] or evidence['export']['export_id']!=a.digest(a.encoded(manifest)):
        raise ValueError('export binding mismatch')
    if manifest['task']['task_id']!=request['task_id'] or manifest['task']['repository_id']!=request['repository_id'] or manifest['task']['baseline_commit']!=baseline or manifest['head_commit']!=baseline:
        raise ValueError('task baseline mismatch')
    if (manifest['binding']['hermes_task']!=evidence['native_task'] or str(manifest['binding']['hermes_run'])!=str(evidence['native_run'])):
        raise ValueError('native task mismatch')
    if set(files)!=set(manifest['files']):raise ValueError('artifact set mismatch')
    for name,data in files.items():
        row=manifest['files'][name]
        if len(data)!=row['size_bytes'] or a.digest(data)!=row['sha256']:raise ValueError('artifact changed')
    if json.loads(files['additional-artifact-1.json'])!=request:raise ValueError('request changed')
    plan=planner.plan(policy,request['repository_id'],assigned_branch,assigned_branch,
        worker_stop_verified=evidence['wait']['worker_stop_verified'],host_stop_verified=host_result['host_stop_verified'],
        validation_exit=evidence['validation_exit'],scope_verified=evidence.get('validation_stop_verified') is True,
        task_success=evidence['success'])
    destination=Path(destination)
    if destination.exists() or destination.is_symlink():raise ValueError('fresh publication directory required')
    env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1',
         'GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'}
    def git(*args,input=None):
        return subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',*args],
            env=env,input=input,capture_output=True,check=True,timeout=60).stdout
    with tempfile.TemporaryDirectory(prefix='.publication-source-',dir=destination.parent) as temporary:
        bundle=Path(temporary)/'source.bundle'
        git('-c','safe.directory='+str(Path(canonical).resolve()),'-C',str(canonical),'bundle','create',str(bundle),'--all')
        git('clone','--quiet','--no-hardlinks','--no-checkout',str(bundle),str(destination))
    def run(*args,input=None):return git('-C',str(destination),*args,input=input)
    run('remote','remove','origin');run('checkout','--quiet','--detach',baseline)
    run('checkout','--quiet','-b',assigned_branch)
    if files['changes.patch']:run('apply','--index','--binary','-',input=files['changes.patch'])
    extras=json.loads(files['additional-artifact-0.json'])
    allowed=set(request['allowed_paths'])
    for name,content in extras.items():
        p=Path(name)
        if name not in allowed or p.is_absolute() or '..' in p.parts or '.git' in p.parts:raise ValueError('new file outside scope')
        target=destination/p
        for parent in (target,*target.parents):
            if parent==destination:break
            if parent.is_symlink():raise ValueError('symlink refused')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(base64.b64decode(content,validate=True))
        run('add','--',name)
    changed=run('diff','--cached','--name-only','-z').decode().rstrip('\0').split('\0')
    if not changed or any(name not in allowed for name in changed):raise ValueError('commit outside admitted scope')
    # Refuse symlinks/submodules, including binary patches that introduce them.
    for line in run('ls-files','--stage','-z').split(b'\0'):
        if line and line.split(b' ',1)[0] not in (b'100644',b'100755'):raise ValueError('non-regular tracked entry refused')
    run('-c','user.name=RRAS reviewed worker','-c','user.email=rras-worker@localhost','commit','--quiet','-m',request['task_id']+': reviewed task changes')
    if run('status','--porcelain'):raise ValueError('publication checkout not clean')
    ref=review.get('baseline_ref','HEAD')
    pr_base=ref.removeprefix('refs/heads/').removeprefix('refs/remotes/origin/') if ref!='HEAD' else policy['repositories'][request['repository_id']]['default_branch']
    return dict(plan,pr_base_branch=pr_base,commit=run('rev-parse','HEAD').decode().strip(),baseline=baseline,
                export_id=evidence['export']['export_id'],checkout=str(destination),
                task_id=request['task_id'],native_task=evidence['native_task'],native_run=evidence['native_run'],
                validation_exit=evidence['validation_exit'],worker_stop_verified=True,host_stop_verified=True)


def push_argv(prepared):
    # Recheck the entire narrow destination syntax immediately before transport.
    import re
    branch=prepared['branch']
    if not re.fullmatch(r'codex/[A-Za-z0-9][A-Za-z0-9_-]{0,120}',branch) or prepared['refspec']!='HEAD:refs/heads/'+branch:
        raise ValueError('invalid publication refspec')
    return ['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',prepared['checkout'],
            'push','--porcelain','--',prepared['remote'],prepared['refspec']]
