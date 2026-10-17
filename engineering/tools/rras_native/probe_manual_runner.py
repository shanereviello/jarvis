"""Disposable, credential-free manual runner acceptance using native jobs and fake coding."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run(source,python,profile,codex_config,parent,dedicated=False):
    root=Path(tempfile.mkdtemp(prefix='rras-manual-runner-',dir=parent));root.chmod(0o700)
    s=importlib.util.spec_from_file_location('manual',Path(__file__).with_name('manual_runner.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    cases=[]
    for case in ('success','validation_failure','unexpected_changes','crash','timeout','validation_timeout','delete_absent_controls','alter_repository_instructions','alter_session_config'):
        base=root/case;base.mkdir(mode=0o700);repo=base/'repo';repo.mkdir();work=base/'work';work.mkdir(mode=0o700)
        def git(*args):subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
        git('init','-q');(repo/'maths.py').write_text('def total(a,b):\n return a-b\n')
        (repo/'test_maths.py').write_text('import unittest\nfrom maths import total\nclass Tests(unittest.TestCase):\n def test_total(self): self.assertEqual(total(2,3),5)\n')
        git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
        if case=='alter_repository_instructions':
            (repo/'AGENTS.md').write_text('Repository instructions\n');git('add','AGENTS.md');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','instructions')
        registry=base/'registry.json';registry.write_text(json.dumps({'schema_version':1,'repositories':[{'repository_id':'fixture','path':str(repo),'enabled':True,'hermes_project':'fixture'}]}))
        spec={'schema_version':1,'task_id':'TASK-'+case,'repository_id':'fixture','objective':'Fix total and create notes.txt; preserve tests','allowed_paths':['maths.py','notes.txt'],
              'validation_argv':[str(python),'-B','-m','unittest','-v'],'worker_timeout_seconds':1 if case=='timeout' else 30,'validation_timeout_seconds':10,'commit_policy':'leave_uncommitted'}
        if case=='validation_timeout':
            spec['validation_argv']=[str(python),'-I','-B','-c','import time; time.sleep(5)'];spec['validation_timeout_seconds']=1
        request=base/'request.json';request.write_text(json.dumps(spec))
        child=base/'fake.py'
        code='import subprocess,time\nfrom pathlib import Path\n'
        if case=='timeout':code+='time.sleep(30)\n'
        elif case=='crash':code+='raise SystemExit(7)\n'
        else:
            if case!='validation_failure':code+='Path("maths.py").write_text("def total(a,b):\\n return a+b\\n")\n'
            code+='Path("notes.txt").write_text("fixture result\\n")\n'
            if case=='delete_absent_controls':code+='Path("AGENTS.md").unlink(missing_ok=True);Path("RRAS_TASK.md").unlink(missing_ok=True)\n'
            if case=='alter_repository_instructions':code+='Path("AGENTS.md").unlink()\n'
            if case=='alter_session_config':code+='Path('+repr(str(work/'home/codex/config.toml'))+').write_text("altered")\n'
            if case=='unexpected_changes':code+='Path("unexpected.txt").write_text("refuse this change\\n")\n'
            code+='subprocess.run('+repr([str(python),'-I','-B',str(Path(__file__).with_name('native_task_cli.py').resolve()),'--context',str(work/'native-task-context.json'),'complete','--result','fixture completed'])+',check=True)\n'
        child.write_text(code);children=[];births={}
        def spawn(task,workspace,board=None):
            from hermes_cli import kanban_db as k
            log=k.worker_log_path(task.id);log.parent.mkdir(parents=True,exist_ok=True)
            with log.open('wb') as f:p=subprocess.Popen([str(python),'-I','-B',str(child)],cwd=workspace,env={'PATH':'/usr/bin:/bin'},stdout=f,stderr=subprocess.STDOUT)
            children.append(p);births[p.pid]=m.local('wait_worker').identity(p.pid);return p.pid
        # Empty environment is the actual runner launch contract, including no key.
        original=dict(os.environ)
        try:
            os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME=str(work),LANG='C.UTF-8')
            result=m.run(source,python,profile,codex_config,registry,request,work,dedicated=dedicated,spawn_delegate=spawn)
        finally:os.environ.clear();os.environ.update(original)
        if case in ('success','delete_absent_controls'):
            passed=result['success'] and result['wait']['worker_stop_verified'] and result['validation_exit']==0 and result['new_files']['count']==1
            capture=json.loads(Path(result['new_files']['path']).read_text());passed=passed and 'notes.txt' in capture
        elif case=='alter_repository_instructions':passed=not result['success'] and result['error_code']=='outside_admitted_paths' and 'export' not in result
        elif case=='alter_session_config':passed=not result['success'] and result['error_code']=='session_configuration_changed' and 'export' not in result
        elif case=='validation_failure':passed=not result['success'] and result['validation_exit']!=0 and 'export' in result
        elif case=='unexpected_changes':passed=not result['success'] and result['error_code']=='outside_admitted_paths' and 'export' not in result
        elif case=='validation_timeout':passed=not result['success'] and result['validation_timeout'] and not result['validation_stop_verified'] and 'export' not in result
        elif case=='crash':passed=not result['success'] and result['wait']['exit_code']==7 and result['wait']['worker_stop_verified']
        else:passed=not result['success'] and result['wait']['outcome']=='timeout' and not result['wait']['worker_stop_verified'] and 'validation_exit' not in result
        # Fixture-only stop of an exact owned live child; never a production cancellation path.
        cleaned=True
        for p in children:
            identity=m.local('wait_worker').identity(p.pid)
            if identity:
                if identity['ppid']!=os.getpid() or identity!=births[p.pid]:cleaned=False;continue
                p.terminate();p.wait(timeout=5)
        cases.append({'name':case,'passed':passed and cleaned,'evidence':str(work/'evidence.json'),'owned_fixture_cleanup':cleaned})
    evidence={'scope':'manual-admitted-runner-fake-coding','api_calls':0,'uid':os.getuid(),'actual_coding_session_tested':False,'dedicated_cgroup_tested':dedicated,
              'success':all(c['passed'] for c in cases),'cases':cases,'root':str(root)}
    (root/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence));return evidence

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','python','profile','codex-config','parent'):p.add_argument('--'+name,required=True)
    p.add_argument('--dedicated-cgroup',action='store_true')
    a=p.parse_args();e=run(a.source,a.python,a.profile,a.codex_config,a.parent,a.dedicated_cgroup);raise SystemExit(0 if e['success'] else 1)
