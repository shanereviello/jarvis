"""One fresh native task + bounded waiter + validation/export. Fake coding only."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import signal
import time
import sys
from unittest.mock import patch


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def run(source,python,profile,root,case,dedicated,fixture_token=None,codex_config=None,paid=False):
    root=Path(root).resolve(strict=True)
    if root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o077:
        raise ValueError('private work required')
    allowed={'PATH','HOME','LANG','LC_CTYPE','PYTHONDONTWRITEBYTECODE'}
    if set(os.environ)-allowed:raise ValueError('empty launch environment required')
    if case=='paid' and not paid:
        raise ValueError('paid case must explicitly select paid execution')
    if paid and (os.getuid()!=996 or not dedicated or case!='paid' or not fixture_token or not codex_config):
        raise ValueError('paid execution requires dedicated identity/cgroup and delivered credential')
    a=local('activity');w=local('wait_worker')
    home=root/'home';p=home/'profiles/rras-engineering';p.mkdir(parents=True,mode=0o700)
    p.joinpath('config.yaml').write_bytes(Path(profile).read_bytes())
    os.environ.update(HOME=str(home),HERMES_HOME=str(home),CODEX_HOME=str(home/'codex'),
                      HERMES_KANBAN_DB=str(home/'kanban/kanban.db'),HERMES_KANBAN_WORKSPACES_ROOT=str(root/'workspaces'))
    if fixture_token is not None:
        if not paid and fixture_token!='RRAS-NONSECRET-OFFLINE-FIXTURE':
            raise ValueError('only the harmless sentinel is accepted')
        os.environ.update(OPENAI_API_KEY=fixture_token,RRAS_OPENAI_API_KEY=fixture_token)
    if codex_config:
        (home/'codex').mkdir(mode=0o700)
        (home/'codex/config.toml').write_bytes(Path(codex_config).read_bytes())
    if paid:
        release=Path(python).parent.parent
        os.environ['PATH']=str(release/'bin')+':'+str(Path(source).parent/'runtime/bin')+':/usr/bin:/bin'
    repo=root/'repo';repo.mkdir()
    def git(*args):return subprocess.run(['git','-C',str(repo),'-c','core.hooksPath=/dev/null',*args],check=True,capture_output=True)
    git('init','-q');(repo/'calc.py').write_text('def add(a,b):\n    return a-b\n')
    (repo/'test_calc.py').write_text('import unittest\nfrom calc import add\nclass AddTest(unittest.TestCase):\n def test_add(self):\n  self.assertEqual(add(2,3),5)\n')
    (repo/'AGENTS.md').write_text('Read RRAS_TASK.md. Work only in this worktree. Use native Hermes CLI, preserve task/run identity, no publication or MCP.\n')
    import shlex
    context=root/'native-task-context.json'
    bridge=Path(__file__).with_name('native_task_cli.py').resolve()
    cli=shlex.join([str(python),'-I','-B',str(bridge),'--context',str(context)])
    (repo/'RRAS_TASK.md').write_text('Fix add(a,b). Run python -B -m unittest -v. Native CLI uses the explicit assigned context, not inherited shell variables. If the context is not present yet, wait up to 10 seconds for atomic publication; stop if still missing. Inspect: '+cli+' show\nAfter passing tests: '+cli+' complete --result "tests passed"\nUse only this assigned context. No push/merge/deployment.\n')
    if paid:
        git('config','user.name','RRAS Canary');git('config','user.email','rras-canary@example.invalid')
        with (repo/'RRAS_TASK.md').open('a') as f:
            f.write('Change only calc.py. Preserve tests and instruction files. Do not inspect/print credentials or run environment dumps. Do not run git add or git commit: Git metadata is protected by the coding sandbox. After passing tests complete the native task; the trusted runner validates and commits calc.py after verified worker termination. This is one attempt; no automatic retries.\n')
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','canary baseline')
    registry=root/'registry.json';registry.write_text(json.dumps({'schema_version':1,'repositories':[{'repository_id':'canary','path':str(repo),'enabled':True,'hermes_project':'canary'}]}))
    a.admit(root/'index',registry,'TASK-canary','canary','Fix add(a,b) and validate locally')
    sys.path.insert(0,str(Path(source).resolve(strict=True)))
    from hermes_cli import kanban_db as k,projects_db as projects
    k.init_db()
    with projects.connect_closing() as c:project=projects.create_project(c,name='Canary fixture',slug='canary',primary_path=str(repo))
    # Only the coding executable is fake; spawn/claim/environment/logs are native.
    child=root/'fake.py'
    body='import os,time,subprocess,sys\nfrom pathlib import Path\ntime.sleep(.25)\n'
    if fixture_token is not None and not paid:
        body+='import json\nfrom tools.environments.local import hermes_subprocess_env\ne=hermes_subprocess_env(inherit_credentials=True)\nchecks={"same_sentinel":os.environ.get("OPENAI_API_KEY")==os.environ.get("RRAS_OPENAI_API_KEY")=="RRAS-NONSECRET-OFFLINE-FIXTURE", "private_codex_config":Path(os.environ["CODEX_HOME"],"config.toml").is_file(), "app_server_env_preserves_sentinel":e.get("OPENAI_API_KEY")==e.get("RRAS_OPENAI_API_KEY")=="RRAS-NONSECRET-OFFLINE-FIXTURE"}\nPath("credential-handoff.json").write_text(json.dumps(checks))\nassert all(checks.values())\n'
    if case=='success':
        body+='Path("calc.py").write_text("def add(a,b):\\n    return a+b\\n")\nsubprocess.run([sys.executable,"-B","-m","unittest","-v"],check=True)\nsubprocess.run([sys.executable,"-B","-m","hermes_cli.main","kanban","complete",os.environ["HERMES_KANBAN_TASK"],"--result","fixture tests passed"],check=True)\ntime.sleep(.25)\n'
    elif case=='crash':body+='raise SystemExit(7)\n'
    else:body+='time.sleep(30)\n'
    if not paid:child.write_text(body)
    result={'scope':'native-manual-paid-canary' if paid else 'native-integrated-runner-fake-coding','uid':os.getuid(),'case':case,'api_calls':None if paid else 0,'success':False,'dedicated_cgroup':dedicated,'real_credential_accessed':paid}
    handle=None
    try:
        with k.connect_closing() as c:
            task=k.create_task(c,title='Fix add',body='Read RRAS_TASK.md; fix add and validate.',assignee='rras-engineering',workspace_kind='worktree',workspace_path=str(repo),project_id=project,max_runtime_seconds=300 if paid else 60,max_retries=0)
            if paid:
                spawned=k.dispatch_once(c,max_spawn=1,max_in_progress=1,max_in_progress_per_profile=1)
            else:
                with patch.object(k,'_resolve_hermes_argv',return_value=[str(python),str(child)]):
                    spawned=k.dispatch_once(c,max_spawn=1,max_in_progress=1,max_in_progress_per_profile=1)
            t=k.get_task(c,task)
            if len(spawned.spawned)!=1:raise RuntimeError('exactly one native spawn required')
            handle=w.NativeChild(t.worker_pid)
            run_id=t.current_run_id;workspace=Path(t.workspace_path)
            local('native_task_cli').write_context(context,task,run_id,p,home/'kanban/kanban.db',python)
            a.bind(root/'index','TASK-canary','fixture',task,str(run_id))
            def status():
                current=k.get_task(c,task)
                latest=k.latest_run(c,task)
                if latest is None or latest.id!=run_id or current.current_run_id not in (None,run_id):
                    raise RuntimeError('native run changed; retain ownership')
                return current.status
            peers=w.cgroup_peers if dedicated else lambda:[handle.pid] if handle.poll() is None else []
            waited=w.wait_worker(handle,status,peers,300 if paid else (5 if case!='timeout' else .5))
            result.update(native_task=task,native_run=run_id,workspace=str(workspace),wait=waited)
            if waited['worker_stop_verified']:
                validation=subprocess.run([str(python),'-B','-m','unittest','-v'],cwd=workspace,capture_output=True,text=True,timeout=15)
                (root/'validation.log').write_text(validation.stdout+validation.stderr)
                result['validation_exit']=validation.returncode
                if fixture_token is not None and not paid:
                    handoff=json.loads((workspace/'credential-handoff.json').read_text())
                    if not all(handoff.values()):raise ValueError('native credential handoff failed')
                    result['sentinel_handoff']=handoff
                if paid:
                    for name in ('AGENTS.md','RRAS_TASK.md','test_calc.py'):
                        if (workspace/name).read_bytes()!=(repo/name).read_bytes():raise ValueError('canary control file changed')
                    for path in (root/'validation.log',k.worker_log_path(task)):
                        if fixture_token.encode() in path.read_bytes():raise ValueError('credential appeared in private log; export refused')
                    snapshot=a.snapshot(a.task(root/'index','TASK-canary'),workspace)
                    if fixture_token.encode() in snapshot[1]:raise ValueError('credential appeared in patch; export refused')
                    if waited['success'] and validation.returncode==0:
                        commit_validated_change(workspace,python,a)
                exported=a.export(root/'index','TASK-canary',workspace,logs=[root/'validation.log',k.worker_log_path(task)])
                a.verify_export(Path(exported['path']));result['export']=exported
                if paid:
                    result['native_session_id']=k.get_task(c,task).session_id
                    result['codex_session_files']=[str(p.relative_to(home/'codex')) for p in (home/'codex/sessions').rglob('*.jsonl')]
            expected={'success':'completed','crash':'failed','timeout':'timeout','paid':'completed'}[case]
            result['success']=waited['outcome']==expected and (case not in ('success','paid') or result.get('validation_exit')==0)
            result['lifecycle_mutated_by_runner']=False
    finally:
        with (root/'evidence.json').open('x') as f:json.dump(result,f,indent=2)
        if not paid and handle is not None and handle.poll() is None:
            current=w.identity(handle.pid)
            stopped=False
            if current and current['ppid']==os.getpid() and current['start_ticks']==handle.start_ticks:
                # Fixture-only cleanup, after refusal evidence; native run is retained.
                os.kill(handle.pid,signal.SIGTERM)
                deadline=time.monotonic()+3
                while handle.poll() is None and time.monotonic()<deadline:time.sleep(.05)
                stopped=handle.poll() is not None
            with (root/'fixture-cleanup.json').open('x') as f:
                json.dump({'owned_fake_child_stopped':stopped,'native_lifecycle_mutated':False},f)
            if not stopped:raise RuntimeError('fixture identity/termination ambiguous; retain unit')
    return result


def commit_validated_change(workspace,python,activity):
    """Caller has verified termination and tests; admit only one regular file."""
    workspace=Path(workspace)
    if (workspace/'calc.py').is_symlink():raise ValueError('canary file symlink refused')
    status=activity.git(workspace,'status','--porcelain').decode().splitlines()
    if status!=[' M calc.py']:raise ValueError('unexpected canary changes; no commit')
    env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'}
    base=['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','user.name=RRAS Canary','-c','user.email=rras-canary@example.invalid','-C',str(workspace)]
    subprocess.run([*base,'add','--','calc.py'],env=env,capture_output=True,check=True,timeout=10)
    subprocess.run([*base,'-c','commit.gpgsign=false','commit','-m','Fix canary addition'],env=env,capture_output=True,check=True,timeout=10)
    if activity.git(workspace,'status','--porcelain').strip():raise ValueError('canary commit left dirty worktree')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','python','profile','work'):p.add_argument('--'+n,required=True)
    p.add_argument('--case',choices=['success','crash','timeout'],required=True);p.add_argument('--dedicated-cgroup',action='store_true')
    x=p.parse_args();r=run(x.source,x.python,x.profile,x.work,x.case,x.dedicated_cgroup)
    print(json.dumps(r));sys.exit(0 if r['success'] else 1)
