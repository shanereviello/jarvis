"""Operator-side Git transport for a trusted prepared review commit.

Internal API only: prepared records/policy/receipt location are trusted operator
inputs, never model tool arguments. No key loading, worker launch, PR merge, or
credential provisioning. A started receipt is never automatically retried.
"""
import importlib.util
import os
from pathlib import Path
import subprocess


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def command(argv):
    # Operator SSH identity/agent, not the coding worker's API environment.
    env={'PATH':'/usr/bin:/bin','HOME':__import__('pwd').getpwuid(os.getuid()).pw_dir,
         'LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
         'GIT_TERMINAL_PROMPT':'0','GIT_SSH_COMMAND':'/usr/bin/ssh -oBatchMode=yes'}
    if os.environ.get('SSH_AUTH_SOCK'):env['SSH_AUTH_SOCK']=os.environ['SSH_AUTH_SOCK']
    return subprocess.run(argv,env=env,stdin=subprocess.DEVNULL,capture_output=True,timeout=60)


def verify(prepared,policy,run=None):
    run=run or command
    planner=local('publication_policy')
    expected=planner.plan(policy,prepared['repository_id'],prepared['branch'],prepared['branch'],
        worker_stop_verified=True,host_stop_verified=True,scope_verified=True,task_success=True,validation_exit=0)
    if any(prepared.get(k)!=v for k,v in expected.items()):raise ValueError('publication policy changed')
    base=['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-C',prepared['checkout']]
    def git(*args):
        result=run(base+list(args))
        if result.returncode!=0:raise ValueError('publication checkout verification failed')
        return result.stdout
    if git('rev-parse','HEAD').decode().strip()!=prepared['commit']:raise ValueError('review commit changed')
    if git('symbolic-ref','--short','HEAD').decode().strip()!=prepared['branch']:raise ValueError('review branch changed')
    if git('status','--porcelain','--untracked-files=all'):raise ValueError('review checkout changed')
    if git('rev-list','--parents','-n','1','HEAD').decode().split()!=[prepared['commit'],prepared['baseline']]:
        raise ValueError('single reviewed baseline parent required')
    return base


def remote_commit(prepared,run):
    ref='refs/heads/'+prepared['branch']
    result=run(['/usr/bin/git','ls-remote','--refs','--',prepared['remote'],ref])
    if result.returncode!=0:raise ValueError('remote verification failed')
    rows=result.stdout.decode().splitlines()
    if not rows:return None
    if len(rows)!=1:raise ValueError('ambiguous remote branch')
    fields=rows[0].split()
    if len(fields)!=2 or fields[1]!=ref or not __import__('re').fullmatch('[0-9a-f]{40}',fields[0]):raise ValueError('invalid remote branch response')
    return fields[0]


def publish(prepared,policy,receipt,run=None):
    """One attempt; retain started + outcome records, including lost responses.

    Caller must have verified prepared provenance/custody before entering. This
    API does not turn caller-supplied dictionaries into authenticated evidence.
    """
    run=run or command;a=local('activity');publication=local('publication')
    verify(prepared,policy,run)
    receipt=Path(receipt)
    if receipt.exists() or receipt.is_symlink() or Path(str(receipt)+'.started').exists():raise ValueError('publication attempt already exists; inspect it')
    identity={k:prepared[k] for k in ('repository_id','remote','branch','refspec','commit','baseline','export_id')}
    identity.update(schema_version=1,merge_authorized=False,deploy_authorized=False)
    a.absent(Path(str(receipt)+'.started'),a.encoded(identity))
    result=dict(identity,status='unknown',remote_write_attempted=False)
    try:
        if remote_commit(prepared,run) is not None:raise ValueError('assigned remote branch already exists; preserve it')
        verify(prepared,policy,run)
        result['remote_write_attempted']=True
        pushed=run(publication.push_argv(prepared))
        if pushed.returncode!=0:raise ValueError('push did not report success; inspect remote without retry')
        if remote_commit(prepared,run)!=prepared['commit']:raise ValueError('remote commit not verified')
        result['status']='published'
    except Exception as e:
        # No stdout/stderr or credential-bearing exception text in the receipt.
        result['error_type']=type(e).__name__
    a.absent(receipt,a.encoded(result))
    return result
