"""Model-free Git worktree commit boundary reproduction and correction."""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile


def metadata_denied(reply):
    """Require an explicit index/lock write denial, never just a failed commit."""
    error=reply.get('stderr','')
    return reply.get('exitCode',0)!=0 and bool(re.search(
        r"(?:index\.lock|Unable to create[^\n]*\.lock)[^\n]*(?:Read-only file system|Permission denied)",
        error, re.I))


def sibling_denied(reply, target, read_passed):
    error=reply.get('stderr','')
    return (read_passed and reply.get('exitCode',0)!=0 and not target.exists()
            and str(target) in error
            and ('Read-only file system' in error or 'Permission denied' in error))


def process_limits():
    result={}
    for line in Path('/proc/self/cgroup').read_text().splitlines():
        if line.startswith('0::'):
            root=Path('/sys/fs/cgroup')/line[3:].lstrip('/')
            for name in ('pids.max','pids.peak','pids.events'):
                try: result[name]=(root/name).read_text().strip()
                except OSError: pass
    return result


def run(source,python,parent):
    root=Path(tempfile.mkdtemp(prefix='rras-git-boundary-',dir=parent))
    repo=root/'repo';repo.mkdir();workspace=repo/'.worktrees/task'
    def git(*args):return subprocess.run(['git','-C',str(repo),'-c','core.hooksPath=/dev/null',*args],check=True,capture_output=True)
    git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    (repo/'calc.py').write_text('def add(a,b):\n    return a-b\n');git('add','.');git('commit','-qm','baseline');git('worktree','add','-qb','fixture',str(workspace))
    board=root/'board';board.mkdir(mode=0o700)
    admission=root/'admission.json';admission.write_text(json.dumps({'repository_path':str(repo)}))
    sys.path.insert(0,str(source))
    from agent.transports.codex_app_server import CodexAppServerClient
    original=Path.cwd();os.chdir(workspace)
    cases=[]
    try:
        for name,binary in [('board_only','/opt/rras-engineering/releases/native-10/runtime/bin/codex')]:
            home=root/name;home.mkdir(mode=0o700)
            (home/'config.toml').write_text('sandbox_mode="workspace-write"\n[sandbox_workspace_write]\nexclude_slash_tmp=true\nexclude_tmpdir_env_var=true\nnetwork_access=false\n[analytics]\nenabled=false\n')
            env={'PATH':'/usr/bin:/bin','HOME':str(home),'CODEX_HOME':str(home),'HERMES_KANBAN_TASK':'fixture','HERMES_KANBAN_RUN_ID':'1','HERMES_KANBAN_DB':str(board/'kanban.db'),'RRAS_ADMISSION_RECORD':str(admission),'LANG':'C.UTF-8'}
            client=CodexAppServerClient(codex_bin=binary,codex_home=str(home),env=env)
            try:
                client.initialize(client_name='rras_git_boundary',client_version='1')
                (workspace/'calc.py').write_text('def add(a,b):\n    return a+b\n')
                read=client.request('command/exec',{'command':['git','rev-parse','HEAD'],'cwd':str(workspace),'timeoutMs':10000},timeout=20)
                expected=git('rev-parse','HEAD').stdout.decode().strip()
                read_passed=read['exitCode']==0 and read.get('stdout','').strip()==expected
                cases.append({'name':'sandbox_git_read_control','passed':read_passed,'exit_code':read['exitCode'],'stderr':read.get('stderr','')[:4096]})
                reply=client.request('command/exec',{'command':['git','-c','core.hooksPath=/dev/null','commit','-am','fixture fix'],'cwd':str(workspace),'timeoutMs':10000},timeout=20)
                passed=metadata_denied(reply) and cases[-1]['passed']
                cases.append({'name':name,'passed':passed,'exit_code':reply['exitCode'],'readonly_error':'Read-only file system' in reply.get('stderr',''),'stdout':reply.get('stdout','')[:4096],'stderr':reply.get('stderr','')[:4096]})
                if name=='board_only':
                    denied=client.request('command/exec',{'command':['/bin/sh','-c','printf denied > "$1"','probe',str(repo/'outside.txt')],'cwd':str(workspace),'timeoutMs':5000},timeout=15)
                    cases.append({'name':'repository_code_outside_worktree_denied','passed':sibling_denied(denied,repo/'outside.txt',read_passed),'exit_code':denied['exitCode'],'stderr':denied.get('stderr','')[:4096]})
            finally:
                process=client._proc;client.close();cases.append({'name':name+'_server_stopped','passed':process.poll() is not None})
    finally:os.chdir(original)
    import importlib.util
    def load(name):
        spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    a=load('activity');m=load('probe_integrated_runner')
    validated=subprocess.run([python,'-I','-B','-c',"import runpy;d=runpy.run_path('calc.py');assert d['add'](2,3)==5"],cwd=workspace,capture_output=True,timeout=10)
    if validated.returncode:raise ValueError('fixture validation failed')
    m.commit_validated_change(workspace,python,a)
    cases.append({'name':'trusted_parent_validates_and_commits_after_server_stop','passed':not a.git(workspace,'status','--porcelain').strip()})
    e={'scope':'git-metadata-model-free','api_calls':0,'success':all(c['passed'] for c in cases),'cases':cases,'root':str(root),'process_limits':process_limits()}
    (root/'evidence.json').write_text(json.dumps(e,indent=2)+'\n');print(json.dumps(e));return e


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','python','parent'):p.add_argument('--'+n,required=True)
    a=p.parse_args();e=run(a.source,a.python,a.parent);sys.exit(0 if e['success'] else 1)
