"""Disposable native Hermes lifecycle probe; replaces only the coding executable."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

TRANSPORT_SHA = '1bd7e181aa18e7a1417708ed8b691f3523657096d4fae51a268d8fa6d7afca57'


def alive(pid):
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
        return stat.rsplit(')', 1)[1].split()[0] != 'Z'
    except FileNotFoundError:
        return False


def owned_child(pid, root):
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        return str(root / "fake_coding_child.py").encode() in argv
    except FileNotFoundError:
        return False


def dispatch(root, source):
    sys.path.insert(0, str(source))
    from hermes_cli import kanban_db as kb, projects_db as projects
    kb.init_db()
    with projects.connect_closing() as conn:
        project = projects.create_project(conn, name='Fixture', slug='fixture', primary_path=str(root/'repo'))
    with kb.connect_closing() as conn:
        tasks = [kb.create_task(conn, title='fixture '+str(i), assignee='rras-engineering',
                 body='Replace code.txt with the fixture change. Validate locally; no publication.',
                 workspace_kind='worktree', workspace_path=str(root/'repo'), project_id=project,
                 idempotency_key='fixture:'+str(i), max_runtime_seconds=60) for i in range(2)]
        # Native spawn, environment, cwd, logs, claim and run bookkeeping remain real.
        with patch.object(kb, '_resolve_hermes_argv', return_value=[sys.executable, str(root/'fake_coding_child.py')]):
            first = kb.dispatch_once(conn, max_spawn=1, max_in_progress=1, max_in_progress_per_profile=1)
            second = kb.dispatch_once(conn, max_spawn=1, max_in_progress=1, max_in_progress_per_profile=1)
        task = kb.get_task(conn, tasks[0])
        result = {'tasks':tasks, 'first_spawned':first.spawned, 'second_spawned':second.spawned,
                  'pid':task.worker_pid, 'workspace':task.workspace_path, 'run_id':task.current_run_id}
    (root/'dispatch.json').write_text(json.dumps(result,indent=2)+'\n')


def run(source, python, hold_for_stop=False, fixture_parent=None, codex_binary=None, profile_config=None, explicit_context=False):
    source = Path(source).resolve(strict=True)
    if hashlib.sha256((source/'agent/transports/codex_app_server.py').read_bytes()).hexdigest() != TRANSPORT_SHA:
        raise ValueError('unreviewed transport source')
    root = Path(tempfile.mkdtemp(prefix='rras-native-dispatcher-', dir=fixture_parent))
    home = root/'home';profile=home/'profiles/rras-engineering'
    profile.mkdir(parents=True,mode=0o700)
    if profile_config:
        data=Path(profile_config).read_bytes()
        config=json.loads(data)
        if config['model']['provider']!='openai-api' or config['model']['api_mode']!='codex_app_server' or config['approvals']['mode']!='manual':
            raise ValueError('corrected canary profile required')
        (profile/'config.yaml').write_bytes(data)
    else:
        (profile/'config.yaml').write_text(json.dumps({'platform_toolsets':{'cli':['kanban','skills']}}))
    repo=root/'repo';repo.mkdir()
    subprocess.run(['git','init','-q',str(repo)],check=True)
    (repo/'code.txt').write_text('baseline\n')
    if codex_binary:
        (repo/'AGENTS.md').write_text('Read RRAS_TASK.md before working. Use the native Hermes CLI for task inspection and completion. Never enable MCP or publish changes.\n')
        (repo/'RRAS_TASK.md').write_text('Disposable model-free fixture: inspect the assigned task, preserve its run ID, validate the fixture edit, and complete only that task. Require both HERMES_KANBAN_TASK and HERMES_KANBAN_RUN_ID to be present.\n\n'+str(python)+' -B -m hermes_cli.main kanban show "$HERMES_KANBAN_TASK" --json\n\n'+str(python)+' -B -m hermes_cli.main kanban complete "$HERMES_KANBAN_TASK" --result "fixture validation passed"\n\nNo remotes, hooks, merge, push or deployment. This fixture is not paid execution.\n')
    subprocess.run(['git','-C',str(repo),'add','.'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline'],check=True)
    spec=importlib.util.spec_from_file_location('activity',Path(__file__).with_name('activity.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    registry=root/'registry.json';registry.write_text(json.dumps({'schema_version':1,'repositories':[{'repository_id':'fixture','path':str(repo),'enabled':True,'hermes_project':'fixture'}]}))
    admission=a.admit(root/'evidence-index',registry,'TASK-fixture','fixture','fake edit acceptance')
    preview=a.preview(root/'evidence-index','TASK-fixture')
    (root/'manual-task-preview.json').write_text(json.dumps(preview,indent=2)+'\n')
    env={'PATH':'/usr/bin:/bin','HOME':str(home),'HERMES_HOME':str(home),
         'CODEX_HOME':str(home/'codex'), 'HERMES_KANBAN_DB':str(home/'kanban/kanban.db'),
         'HERMES_KANBAN_WORKSPACES_ROOT':str(root/'workspaces'),
         'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8','RRAS_FIXTURE_ROOT':str(root)}
    # No model client is imported by this substituted child. It performs a fake edit
    # and then calls the real native completion transition on the fixture board.
    child = '''import json,os,sys,time
from pathlib import Path
root=Path(os.environ['RRAS_FIXTURE_ROOT'])
receipt={'pid':os.getpid(),'cwd':os.getcwd(),'argv':sys.argv[1:],
 'environment':{k:os.environ.get(k) for k in ['HERMES_HOME','HERMES_PROFILE','CODEX_HOME','HERMES_KANBAN_DB','HERMES_KANBAN_WORKSPACES_ROOT','HERMES_KANBAN_RUN_ID']}}
(root/'child.json').write_text(json.dumps(receipt))
Path('code.txt').write_text('fake validated change\\n')
for i in range(300):
 if (root/'release').exists():break
 time.sleep(.1)
else:raise SystemExit(2)
sys.path.insert(0,SOURCE)
from hermes_cli import kanban_db as kb
with kb.connect_closing() as conn:
 assert kb.complete_task(conn,os.environ['HERMES_KANBAN_TASK'],result='fixture fake completion',expected_run_id=int(os.environ['HERMES_KANBAN_RUN_ID']),fire_lifecycle_hook=False)
'''.replace('SOURCE',repr(str(source)))
    (root/'fake_coding_child.py').write_text(child)
    if codex_binary:
        # This mode's fake child holds the native run open. Actual CLI completion
        # is exercised below inside Codex's real coding sandbox, not in the child.
        child=child[:child.index('sys.path.insert(0,')]
        (root/'fake_coding_child.py').write_text(child)
    e={'schema_version':1,'scope':'native-dispatcher-with-fake-coding-child','root':str(root),
       'api_calls':0,'actual_coding_session_tested':False,'dedicated_uid_tested':False,
       'systemd_cgroup_tested':False,'success':False,'cases':[]};pid=None
    try:
        p=subprocess.run([str(python),'-B',str(Path(__file__).resolve()),'--dispatch','--source',str(source),'--root',str(root)],env=env,capture_output=True,text=True,timeout=30)
        (root/'dispatcher.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError('dispatcher fixture failed; inspect dispatcher.log')
        d=json.loads((root/'dispatch.json').read_text());pid=d['pid']
        for _ in range(100):
            if (root/'child.json').exists():break
            time.sleep(.05)
        c=json.loads((root/'child.json').read_text());workspace=Path(d['workspace'])
        checks={'one_native_spawn':len(d['first_spawned'])==1,'concurrency_cap':d['second_spawned']==[],
          'child_survives_dispatcher_exit':alive(pid),'profile_selected':c['environment']['HERMES_HOME']==str(profile),
          'isolated_codex_home':c['environment']['CODEX_HOME']==env['CODEX_HOME'],
          'native_worktree_cwd':c['cwd']==str(workspace) and workspace!=repo,
          'profile_toolsets': '--toolsets' in c['argv'],
          'board_and_workspace_roots':c['environment']['HERMES_KANBAN_DB']==env['HERMES_KANBAN_DB'] and c['environment']['HERMES_KANBAN_WORKSPACES_ROOT']==env['HERMES_KANBAN_WORKSPACES_ROOT']}
        if profile_config:
            checks['corrected_profile_dispatch_argv']=c['argv'][c['argv'].index('--toolsets')+1]=='kanban,skills'
            checks['corrected_profile_preserved']=(profile/'config.yaml').read_bytes()==Path(profile_config).read_bytes()
        if codex_binary:
            sys.path.insert(0,str(source))
            from agent.transports.codex_app_server import CodexAppServerClient
            codex_home=root/'home/codex';codex_home.mkdir(mode=0o700)
            (codex_home/'config.toml').write_text('sandbox_mode="workspace-write"\napproval_policy="on-request"\n[sandbox_workspace_write]\nnetwork_access=false\nexclude_slash_tmp=true\nexclude_tmpdir_env_var=true\n[analytics]\nenabled=false\n')
            coding_env=dict(env,HERMES_KANBAN_TASK=d['tasks'][0],HERMES_KANBAN_RUN_ID=str(d['run_id']))
            client=CodexAppServerClient(codex_bin=str(codex_binary),codex_home=str(codex_home),env=coding_env)
            try:
                client.initialize(client_name='rras_native_cli_fixture',client_version='1')
                if explicit_context:
                    spec=importlib.util.spec_from_file_location('native_task_cli',Path(__file__).with_name('native_task_cli.py'))
                    bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
                    context=root/'native-task-context.json';stale_context=root/'stale-task-context.json'
                    bridge.write_context(context,d['tasks'][0],d['run_id'],profile,home/'kanban/kanban.db',python)
                    bridge.write_context(stale_context,d['tasks'][0],d['run_id']+1,profile,home/'kanban/kanban.db',python)
                def cli_command(arguments,run_id):
                    if explicit_context:
                        selected=context if run_id==d['run_id'] else stale_context
                        argv=['/usr/bin/env','-i','PATH=/usr/bin:/bin','LANG=C.UTF-8',str(python),'-I','-B',str(Path(__file__).with_name('native_task_cli.py')),'--context',str(selected),arguments[0]]
                        if arguments[0]=='complete':argv+=arguments[2:]
                    else:
                        argv=['/usr/bin/env','HERMES_KANBAN_RUN_ID='+str(run_id),str(python),'-B','-m','hermes_cli.main','kanban',*arguments]
                    return client.request('command/exec',{'command':argv, 'cwd':str(workspace),'timeoutMs':15000},timeout=25)
                show=cli_command(['show',d['tasks'][0],'--json'],d['run_id'])
                (root/'native-cli-show.json').write_text(json.dumps(show,indent=2)+'\n')
                checks['sandbox_native_show']=show['exitCode']==0 and d['tasks'][0] in show.get('stdout','')
                if explicit_context:
                    checks['explicit_context_without_inherited_variables']=checks['sandbox_native_show']
                    denied=client.request('command/exec',{'command':['/bin/sh','-c','printf denied > "$1"','probe',str(context)],'cwd':str(workspace),'timeoutMs':5000},timeout=15)
                    checks['context_outside_coding_writes']=denied['exitCode']!=0 and str(context) in denied.get('stderr','') and ('Permission denied' in denied.get('stderr','') or 'Read-only file system' in denied.get('stderr','')) and bridge.read_context(context)['run_id']==d['run_id']
                stale=cli_command(['complete',d['tasks'][0],'--result','stale fixture'],d['run_id']+1)
                after_stale=cli_command(['show',d['tasks'][0],'--json'],d['run_id'])
                checks['sandbox_stale_run_refused']=stale['exitCode']!=0 and json.loads(after_stale['stdout'])['task']['status']=='running'
                checks['sandbox_task_body_available']=json.loads(show['stdout'])['task']['body']=='Replace code.txt with the fixture change. Validate locally; no publication.'
                complete=cli_command(['complete',d['tasks'][0],'--result','fixture validation passed'],d['run_id'])
                checks['sandbox_matching_run_complete']=complete['exitCode']==0
                checks['instruction_files_preserved']= (workspace/'AGENTS.md').read_bytes()==(repo/'AGENTS.md').read_bytes() and (workspace/'RRAS_TASK.md').read_bytes()==(repo/'RRAS_TASK.md').read_bytes()
                (root/'native-cli-results.json').write_text(json.dumps({'show':show,'stale':stale,'complete':complete},indent=2)+'\n')
            finally:
                process=client._proc
                client.close()
                checks['app_server_stopped']=process.poll() is not None
            e['native_cli_in_codex_sandbox_tested']=True
        if hold_for_stop:
            (root/'ready-for-stop.json').write_text(json.dumps({'pid':pid,'root':str(root),'native':d,'child':c}))
            # Administrator may stop this disposable cgroup; this is not a production lifecycle loop.
            time.sleep(60)
        (root/'release').touch()
        for _ in range(100):
            if not alive(pid):break
            time.sleep(.05)
        checks['child_exited_after_completion']=not alive(pid)
        # Inspect native terminal lifecycle in a separate clean process.
        query='import sys,json;sys.path.insert(0,'+repr(str(source))+');from hermes_cli import kanban_db as k;\nwith k.connect_closing() as c: print(json.dumps({"status":k.get_task(c,'+repr(d['tasks'][0])+').status}))'
        terminal=subprocess.check_output([str(python),'-B','-c',query],env=env,text=True,timeout=15)
        checks['native_completion']=json.loads(terminal)['status']=='done'
        checks['admission_precedes_dispatch']=admission['baseline_commit']==a.git(repo,'rev-parse','HEAD').decode().strip()
        checks['manual_preview_triage_only']=preview['execute'] is False and '--triage' in preview['argv']
        a.bind(root/'evidence-index','TASK-fixture','rras-engineering',d['tasks'][0],str(d['run_id']))
        exported=a.export(root/'evidence-index','TASK-fixture',workspace,logs=[root/'dispatcher.log'])
        a.verify_export(Path(exported['path']))
        checks['rras_patch_export']=True
        e.update({'cases':[{'name':n,'passed':v} for n,v in checks.items()],'native':d,'child':c,'export':exported,'uid':os.getuid(),'success':all(checks.values())})
    except Exception as exc:e['error']=type(exc).__name__+': '+str(exc)
    finally:
        if pid is None and (root/'child.json').exists():
            pid=json.loads((root/'child.json').read_text()).get('pid')
        if pid and alive(pid):
            # Never signal a PID based only on a retained number.
            if not owned_child(pid,root):
                e['cleanup_error']='PID identity ambiguous; no signal sent';e['success']=False
            else:
                os.kill(pid,signal.SIGTERM)
                for _ in range(100):
                    if not alive(pid):break
                    time.sleep(.02)
                if alive(pid):e['cleanup_error']='fixture still live';e['success']=False
        e['fixture_child_stopped']=not pid or not alive(pid)
        (root/'evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    return root,e


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--python',type=Path)
    p.add_argument('--dispatch',action='store_true');p.add_argument('--root',type=Path)
    p.add_argument('--hold-for-stop',action='store_true')
    p.add_argument('--fixture-parent',type=Path)
    p.add_argument('--codex-binary',type=Path)
    p.add_argument('--profile-config',type=Path)
    p.add_argument('--explicit-task-context',action='store_true')
    a=p.parse_args()
    if a.dispatch:dispatch(a.root,a.source)
    else:
        if not a.python:p.error('--python required')
        root,e=run(a.source,a.python,a.hold_for_stop,a.fixture_parent,a.codex_binary,a.profile_config,a.explicit_task_context);print(root/'evidence.json');raise SystemExit(0 if e['success'] else 1)
