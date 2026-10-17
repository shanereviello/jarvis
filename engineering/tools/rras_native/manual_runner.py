"""Operator-selected admitted task using native Hermes dispatch and retained evidence."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib


def local(name):
    s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def request(path):
    return validate_request(local('activity').load(path))


def validate_request(r):
    return local('task_contract').validate_request(r)


def changed_paths(a, workspace, baseline):
    names=a.git(workspace,'diff','--no-renames','--name-only','-z',baseline,'--').split(b'\0')
    names+=a.git(workspace,'ls-files','--others','--exclude-standard','-z').split(b'\0')
    return sorted({x.decode() for x in names if x})


def scope(a, workspace, record, r):
    if a.git(workspace,'rev-parse','HEAD').decode().strip()!=record['baseline_commit']:
        raise HandoffError('unexpected_worker_commit')
    names=changed_paths(a,workspace,record['baseline_commit'])
    if not set(names)<=set(r['allowed_paths']):raise HandoffError('outside_admitted_paths')
    for name in names:
        p=workspace/name
        for part in (p,*p.parents):
            if part==workspace:break
            if part.is_symlink():raise HandoffError('changed_symlink')
        if p.exists() and not p.is_file():raise HandoffError('nonregular_changed_file')
    return names


class HandoffError(ValueError):
    """Safe, fixed diagnostic code; never expose exception payloads."""
    def __init__(self, code):
        self.code=code
        super().__init__(code)


def configure_instructions(root, r, python, config):
    # Native Codex developer instructions, outside the editable worktree. The
    # root-owned approved job remains authoritative, not this worker-owned copy.
    config=Path(config)
    raw=config.read_text(encoding='utf-8');settings=tomllib.loads(raw)
    cli=shlex.join([str(python),'-I','-B',str(Path(__file__).with_name('native_task_cli.py').resolve()),'--context',str(root/'native-task-context.json')])
    text=('RRAS assigned task: '+r['task_id']+'\n'+r['objective']+'\nAllowed change paths: '+json.dumps(r['allowed_paths'])+
          '\nValidation: '+shlex.join(r['validation_argv'])+'\nInspect: '+cli+' show\nAfter passing validation: '+cli+' complete --result "validation passed"\n'
          'Leave repository instruction files unchanged. No git add/commit/push, merge or deployment. Do not inspect credentials or dump environment variables. Use the explicit assigned context, not inherited task variables.\n'
          'Complete every requested deliverable; passing mechanical validation alone does not establish factual correctness or human acceptance. Report unresolved requirements honestly.\n')
    # Prefix the root key before any tables, retaining every other setting.
    # Remove only a pre-existing root key through a native TOML roundtrip is
    # deliberately unsupported; refuse rather than use a brittle text rewrite.
    if 'developer_instructions' in settings:raise HandoffError('existing_session_instructions')
    content=('developer_instructions = '+json.dumps(text,ensure_ascii=False)+'\n'+raw).encode()
    tomllib.loads(content.decode())
    config.write_bytes(content);config.chmod(0o600)
    evidence={'mode':'native-codex-developer-instructions','sha256':local('activity').digest(content),'workspace_files_injected':False}
    local('activity').absent(root/'instruction-handoff.json',local('activity').encoded(evidence))
    return content


def _typed_equal(left, right):
    # Python considers False == 0; TOML policy comparison must not.
    if type(left) is not type(right):return False
    if isinstance(left,dict):return left.keys()==right.keys() and all(_typed_equal(left[k],right[k]) for k in left)
    if isinstance(left,list):return len(left)==len(right) and all(_typed_equal(a,b) for a,b in zip(left,right))
    return left==right


def verify_instructions(config, expected, workspace=None, repository=None):
    config=Path(config)
    if config.is_symlink() or not config.is_file() or config.stat().st_size>1048576:
        raise HandoffError('session_configuration_changed')
    current=config.read_bytes()
    if current==expected:return {'mode':'byte-identical','project_records_added':0}
    try:before=tomllib.loads(expected.decode());after=tomllib.loads(current.decode())
    except (ValueError,UnicodeError):raise HandoffError('session_configuration_changed') from None
    if _typed_equal(before,after):return {'mode':'semantic-identical','project_records_added':0}
    old_projects=before.pop('projects',{});new_projects=after.pop('projects',{})
    if not _typed_equal(before,after):raise HandoffError('session_configuration_changed')
    if not isinstance(old_projects,dict) or not isinstance(new_projects,dict):raise HandoffError('unapproved_project_trust')
    if any(k not in new_projects or not _typed_equal(v,new_projects[k]) for k,v in old_projects.items()):
        raise HandoffError('unapproved_project_trust')
    roots={}
    for label,value in (('workspace',workspace),('repository',repository)):
        if value is not None:
            p=Path(value)
            if not p.is_absolute() or str(p)!=str(p.resolve(strict=True)):
                raise HandoffError('unapproved_project_trust')
            roots[str(p)]=label
    added=set(new_projects)-set(old_projects)
    if not added or not added<=roots.keys():raise HandoffError('unapproved_project_trust')
    for name in added:
        row=new_projects[name]
        if not isinstance(row,dict) or set(row)!={'trust_level'} or row['trust_level'] not in ('trusted','untrusted'):
            raise HandoffError('unapproved_project_trust')
    # Trust may enable project-local config/hooks/rules. Do not silently admit
    # those layers in this narrow compatibility exception.
    for name in roots:
        p=Path(name)/'.codex'
        if p.exists() or p.is_symlink():raise HandoffError('project_scoped_configuration_requires_review')
    return {'mode':'assigned-project-trust','project_records_added':len(added),
            'project_roles':sorted(roots[k] for k in added)}


def _run(source, python, profile, codex_config, registry, task_request, root, *, dedicated=True, token=None, spawn_delegate=None):
    a=local('activity');w=local('wait_worker');bridge=local('native_task_cli')
    root=Path(root).resolve(strict=True);a.private_dir(root)
    if any(root.iterdir()):raise ValueError('fresh empty run directory required')
    if set(os.environ)-{'PATH','HOME','LANG','LC_CTYPE','PYTHONDONTWRITEBYTECODE'}:raise ValueError('empty launch environment required')
    if spawn_delegate is None and (os.getuid()!=996 or not dedicated or not token):raise ValueError('authorized dedicated execution required')
    r=request(task_request);row=a.registration(registry,r['repository_id']);repo=Path(row['path'])
    # Native worktrees live under the repo; ignore only that native workspace directory.
    dirty=[x for x in a.git(repo,'status','--porcelain','--untracked-files=all').decode().splitlines() if not x.startswith('?? .worktrees/')]
    if dirty:raise ValueError('registered repository must have a clean baseline')
    record=a.admit(root/'index',registry,r['task_id'],r['repository_id'],r['objective'])
    a.absent(root/'request.json',a.encoded(r))
    home=root/'home';profile_home=home/'profiles/rras-engineering';profile_home.mkdir(parents=True,mode=0o700)
    (profile_home/'config.yaml').write_bytes(Path(profile).read_bytes());(home/'codex').mkdir(mode=0o700)
    (home/'codex/config.toml').write_bytes(Path(codex_config).read_bytes())
    os.environ.update(HOME=str(home),HERMES_HOME=str(home),CODEX_HOME=str(home/'codex'),HERMES_KANBAN_DB=str(home/'kanban/kanban.db'),HERMES_KANBAN_WORKSPACES_ROOT=str(root/'workspaces'))
    if token:os.environ.update(OPENAI_API_KEY=token,RRAS_OPENAI_API_KEY=token)
    os.environ['PATH']=str(Path(python).parent)+':'+str(Path(source).parent/'runtime/bin')+':/usr/bin:/bin'
    sys.path.insert(0,str(source))
    from hermes_cli import kanban_db as k,projects_db as projects
    result={'scope':'native-manual-admitted-task','success':False,'uid':os.getuid(),'api_calls':None if token else 0,
            'model_backed':spawn_delegate is None,'commit_policy':r['commit_policy'],'lifecycle_mutated_by_runner':False,'phase':'native_setup',
            'deliverable_review':'pending-human-review','mechanical_validation':'not-run','validation_eligible':False,'retained_work':str(root)}
    try:
        k.init_db()
        with projects.connect_closing() as c:project=projects.create_project(c,name=r['repository_id'],slug=row['hermes_project'],primary_path=str(repo))
        with k.connect_closing() as c:
            task=k.create_task(c,title=r['task_id'],body=r['objective'],assignee='rras-engineering',workspace_kind='worktree',workspace_path=str(repo),project_id=project,max_runtime_seconds=r['worker_timeout_seconds'],max_retries=0)
            handoff={}
            def spawn(claimed,workspace,board=None):
                workspace=Path(workspace);a.worktree(record,workspace)
                if a.git(workspace,'rev-parse','HEAD').decode().strip()!=record['baseline_commit']:raise ValueError('baseline changed before launch')
                bridge.write_context(root/'native-task-context.json',claimed.id,claimed.current_run_id,profile_home,home/'kanban/kanban.db',python)
                handoff['expected']=configure_instructions(root,r,python,home/'codex/config.toml')
                result['instruction_delivery']={'mode':'native-codex-developer-instructions','workspace_files_injected':False}
                result['phase']='worker_launch'
                a.bind(root/'index',r['task_id'],'default',claimed.id,str(claimed.current_run_id))
                return (spawn_delegate or k._default_spawn)(claimed,str(workspace),board=board)
            dispatched=k.dispatch_once(c,spawn_fn=spawn,max_spawn=1,max_in_progress=1,max_in_progress_per_profile=1,reconcile_orphans=False)
            t=k.get_task(c,task);result.update(native_task=task,native_run=t.current_run_id,workspace=t.workspace_path)
            if len(dispatched.spawned)!=1:raise RuntimeError('native launch failed; retain records')
            child=w.NativeChild(t.worker_pid);workspace=Path(t.workspace_path);run_id=t.current_run_id
            def status():
                current=k.get_task(c,task);latest=k.latest_run(c,task)
                if not latest or latest.id!=run_id or current.current_run_id not in (None,run_id):raise RuntimeError('native run changed')
                return current.status
            peers=w.cgroup_peers if dedicated else lambda:[child.pid] if child.poll() is None else []
            result['phase']='worker_wait'
            result['wait']=w.wait_worker(child,status,peers,r['worker_timeout_seconds'])
            if result['wait']['worker_stop_verified']:
                result['phase']='instruction_verification'
                result['instruction_integrity']=verify_instructions(home/'codex/config.toml',handoff['expected'],workspace,repo)
                result['phase']='scope_check'
                names=scope(a,workspace,record,r);result['changed_paths']=names
                result['validation_eligible']=True
                result['phase']='validation'
                env={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
                try:
                    v=subprocess.run(r['validation_argv'],cwd=workspace,env=env,stdin=subprocess.DEVNULL,capture_output=True,timeout=r['validation_timeout_seconds'])
                    output=v.stdout+v.stderr;result['validation_exit']=v.returncode
                except subprocess.TimeoutExpired:
                    # Descendant stop cannot be attested after a validation timeout. Retain unit/worktree.
                    result['validation_timeout']=True;result['validation_stop_verified']=False;raise HandoffError('validation_timeout')
                if len(output)>4*1024*1024:raise ValueError('validation output too large')
                a.absent(root/'validation.log',output)
                if dedicated and w.cgroup_peers():
                    result['validation_stop_verified']=False;raise HandoffError('validation_descendants_remain')
                result['validation_stop_verified']=True
                result['mechanical_validation']='passed' if v.returncode==0 else 'failed'
                result['phase']='post_validation_scope'
                scope(a,workspace,record,r)  # Validation must not expand the admitted change set.
                result['phase']='export'
                extras={}
                for name in a.git(workspace,'ls-files','--others','--exclude-standard','-z').split(b'\0'):
                    if name:
                        p=workspace/name.decode()
                        if p.stat().st_size>1024*1024:raise ValueError('new file too large')
                        data=p.read_bytes()
                        if token and token.encode() in data:raise ValueError('credential in new file')
                        if len(data)>1024*1024:raise ValueError('new file too large')
                        extras[name.decode()]=base64.b64encode(data).decode()
                data=a.encoded(extras)
                if len(data)>4*1024*1024:raise ValueError('new-file evidence too large')
                a.absent(root/'new-files.json',data)
                logs=[root/'validation.log',k.worker_log_path(task)]
                if token:
                    for p in logs+[root/'new-files.json',root/'request.json']:
                        if token.encode() in p.read_bytes():raise ValueError('credential in evidence; export refused')
                    if token.encode() in a.snapshot(record,workspace)[1]:raise ValueError('credential in patch')
                result['export']=a.export(root/'index',r['task_id'],workspace,logs=logs,artifacts=[root/'new-files.json',root/'request.json'])
                a.verify_export(Path(result['export']['path']))
                result['new_files']={'path':str(Path(result['export']['path'])/'additional-artifact-0.json'),'sha256':a.digest(data),'count':len(extras)}
                result['success']=result['wait']['success'] and v.returncode==0
                if not result['success']:
                    result['error_code']='validation_failed' if v.returncode else 'native_completion_failed'
                result['phase']='finished'
            else:
                result['error_code']='worker_stop_unverified'
    except Exception as e:
        result['error_type']=type(e).__name__
        result['error_code']=e.code if isinstance(e,HandoffError) else result['phase']+'_failed'
    finally:a.absent(root/'evidence.json',a.encoded(result))
    return result

def run(source, python, profile, codex_config, registry, task_request, root, **options):
    a=local('activity');root=Path(root).resolve(strict=True);a.private_dir(root)
    if any(root.iterdir()):raise ValueError('fresh empty run directory required; preserve existing records')
    try:
        return _run(source,python,profile,codex_config,registry,task_request,root,**options)
    except Exception as e:
        result={'scope':'native-manual-admitted-task','success':False,'phase':'preflight',
                'error_type':type(e).__name__,'error_code':'preflight_failed','worker_started':False,'lifecycle_mutated_by_runner':False}
        if not (root/'evidence.json').exists():a.absent(root/'evidence.json',a.encoded(result))
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','python','profile','codex-config','registry','request','work','credential'):p.add_argument('--'+name,required=True)
    p.add_argument('--authorize-one-paid-task',action='store_true');args=p.parse_args()
    if not args.authorize_one_paid_task or os.getuid()!=996:p.error('explicit authorization and UID996 required')
    token=local('credentials').delivered_key(args.credential);os.environ.pop('CREDENTIALS_DIRECTORY',None)
    e=run(args.source,args.python,args.profile,args.codex_config,args.registry,args.request,args.work,token=token)
    print(json.dumps(e));raise SystemExit(0 if e['success'] else 1)
