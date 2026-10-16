"""Disposable root custody-to-local-Git publication acceptance; no network/model."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def probe():
    if os.geteuid()!=0:raise ValueError('administrator acceptance required')
    a=local('activity');launch=local('approved_launch');launch.slot()
    run_id=uuid.uuid4().hex;root=Path('/var/lib')/('rras-publication-workflow-'+run_id)
    launch.trusted(root.parent);root.mkdir(mode=0o700)
    print('RETAIN RUN_ID='+run_id+' WORK='+str(root),flush=True)
    result={'scope':'publication-custody-to-local-git-model-free','run_id':run_id,'success':False,
            'api_calls':0,'real_credentials_used':False,'worker_launched':False,
            'github_tested':False,'network_used':False,'installed_services_modified':False,'cases':[]}
    try:
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'}
        def command(argv):return subprocess.run(argv,env=env,stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
        def git(repo,*args):
            r=command(['/usr/bin/git','-c','core.hooksPath=/dev/null','-C',str(repo),*args])
            if r.returncode:raise ValueError('fixture Git command failed')
            return r.stdout
        repo=root/'canonical';repo.mkdir();git(repo,'init','-q')
        (repo/'calc.py').write_text('value = 1\n');git(repo,'add','calc.py')
        git(repo,'-c','user.name=Fixture','-c','user.email=fixture@localhost','commit','-qm','fixture baseline')
        baseline=git(repo,'rev-parse','HEAD').decode().strip()
        (repo/'calc.py').write_text('value = 2\n');patch=git(repo,'diff','--binary');git(repo,'checkout','--','calc.py')
        request=dict(schema_version=1,task_id='TASK-publication-fixture',repository_id='jarvis',objective='fixture change',allowed_paths=['calc.py'],validation_argv=['/usr/bin/true'],worker_timeout_seconds=30,validation_timeout_seconds=10,commit_policy='leave_uncommitted')
        review=dict(request=request,baseline_commit=baseline,canonical_repository=str(repo),submission_id='fixture-only')
        review_id=a.digest(a.encoded(review));auth=uuid.uuid4().hex
        state=root/'control';state.mkdir(mode=0o700)
        work=root/'worker/work';work.mkdir(parents=True,mode=0o700)
        workspace=str(root/'worker/repo/.worktrees/t_fixture')
        files={'changes.patch':patch,'additional-artifact-0.json':b'{}','additional-artifact-1.json':a.encoded(request)}
        manifest=dict(worktree=workspace,task=dict(task_id=request['task_id'],repository_id='jarvis',baseline_commit=baseline),head_commit=baseline,
                      binding=dict(hermes_task='t_fixture',hermes_run='1'),files={k:dict(sha256=a.digest(v),size_bytes=len(v)) for k,v in files.items()})
        export_id=a.digest(a.encoded(manifest));export=work/'index'/request['task_id']/'exports'/export_id
        export.mkdir(parents=True,mode=0o700)
        evidence=dict(workspace=workspace,export=dict(export_id=export_id,path=str(export)),native_task='t_fixture',native_run=1,
                      wait=dict(worker_stop_verified=True),validation_exit=0,validation_stop_verified=True,success=True)
        for name,data in files.items():a.absent(export/name,data)
        a.absent(export/'manifest.json',a.encoded(manifest));a.absent(work/'evidence.json',a.encoded(evidence))
        for p in [root/'worker',*(root/'worker').rglob('*')]:os.chown(p,996,996,follow_symlinks=False)
        link=dict(authorization_id=auth,review_id=review_id,submission_id='fixture-only',run_id=run_id,work=str(work))
        for name,obj in [(review_id+'.review.json',review),(auth+'.launch.json',link),(auth+'.result.json',{**link,'service_exit':0,'host_stop_verified':True})]:a.absent(state/name,a.encoded(obj))
        custody=root/'custody';local('publication_capture').capture(state,auth,custody)
        result['cases'].append('protected_capture')
        remote=root/'local-remote.git';git(root,'init','--bare','-q',str(remote))
        # Fixture-only policy: all transport destinations stay in this new root.
        policy={'schema_version':1,'review_branch_publication':'standing-authorized','branch_prefix':'codex/',
                'repositories':{'jarvis':{'remote':str(remote),'default_branch':'main'}}}
        policy_path=root/'fixture-policy.json';a.absent(policy_path,a.encoded(policy))
        prepared=local('publication_custody').prepare(custody,policy_path,root/'publication')
        assert (root/'publication/calc.py').read_text()=='value = 2\n'
        result['cases'].append('custody_verified_review_commit')
        transport=local('publication_transport');receipt=root/'publication-receipt.json'
        published=transport.publish(prepared,policy,receipt,command)
        assert published['status']=='published' and transport.remote_commit(prepared,command)==prepared['commit']
        assert git(remote,'show-ref').decode().count('\n')==1
        assert git(repo,'rev-parse','HEAD').decode().strip()==baseline
        result['cases'].extend(['exact_local_branch_published','durable_publication_receipt','canonical_unchanged'])
        try:transport.publish(prepared,policy,receipt,command)
        except ValueError:result['cases'].append('replay_refused')
        else:raise AssertionError('replay accepted')
        assert published['merge_authorized'] is False and published['deploy_authorized'] is False
        result['cases'].append('merge_and_deploy_remain_unapproved')
        result['success']=True
    except Exception as e:result['error_type']=type(e).__name__
    finally:a.absent(root/'acceptance.json',a.encoded(result))
    print(json.dumps(result));return result

if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(0 if probe()['success'] else 1)
