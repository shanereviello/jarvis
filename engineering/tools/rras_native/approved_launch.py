"""Operator-approved one-shot launch into one fixed systemd slot; no scheduler.

Never retries, manually closes native tasks, signals PIDs, publishes or merges.
Losing the systemd client does not authorize another service while the slot exists.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import uuid

UNIT='rras-coding-task.service'
RELEASE=Path('/opt/rras-engineering/releases/native-10')


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def trusted(path):
    p=Path(path)
    for item in (p,*p.parents):
        info=item.stat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('root-protected launch input required')
    return p


def command(argv,timeout=30):
    return subprocess.run(argv,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=timeout)


def slot(check=None):
    check=check or command
    result=check(['/usr/bin/systemctl','show',UNIT,'-p','LoadState','--value'])
    if result.returncode!=0 or result.stdout.strip()!='not-found':raise ValueError('launch slot exists or cannot be verified; preserve it')
    result=check(['/usr/bin/pgrep','-u','996'])
    if result.returncode!=1:raise ValueError('engineering identity busy or process check ambiguous')


def argv(work,job,review,credential):
    return ['/usr/bin/systemd-run','--unit',UNIT,'--service-type=exec','--wait','--pipe','--collect',
        '-p','User=jarvis-codex-engineering','-p','Group=jarvis-codex-engineering',
        '-p','WorkingDirectory='+str(work),'-p','UMask=0077','-p','NoNewPrivileges=yes',
        '-p','CapabilityBoundingSet=','-p','ReadOnlyPaths=/srv/git','-p','KillMode=control-group',
        '-p','RuntimeMaxSec=400','-p','TimeoutStopSec=10','-p','MemoryMax=1G','-p','TasksMax=128','-p','CPUQuota=100%',
        '-p','LoadCredential=rras-api:'+str(credential),
        '/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+str(work),'LANG=C.UTF-8','PYTHONDONTWRITEBYTECODE=1',
        'CREDENTIALS_DIRECTORY=${CREDENTIALS_DIRECTORY}',str(RELEASE/'venv/bin/python'),'-I','-B',
        str(Path(__file__).with_name('manual_runner.py')),'--source',str(RELEASE/'hermes'),
        '--python',str(RELEASE/'venv/bin/python'),'--profile',review['profile'],'--codex-config',review['codex_config'],
        '--registry',str(job/'registry.json'),'--request',str(job/'request.json'),'--work',str(work),
        '--credential','${CREDENTIALS_DIRECTORY}/rras-api','--authorize-one-paid-task']


def worker_root(workers):
    path=Path(workers)
    if path.is_symlink() or path.resolve()!=path or path.stat().st_uid!=996 or path.stat().st_mode&0o077:
        raise ValueError('private worker root required')
    return path


def launch(state,authorization_id,jobs,workers,policy,credential):
    a=local('activity');approval=local('approval')
    state=trusted(state);jobs=trusted(jobs)
    if stat.S_IMODE(state.stat().st_mode)!=0o700:raise ValueError('private approval state required')
    # Must not read credential bytes; systemd alone delivers them into the worker.
    credential=trusted(credential);cs=credential.stat()
    if not stat.S_ISREG(cs.st_mode) or cs.st_mode&0o077:raise ValueError('private credential source required')
    if not __import__('re').fullmatch('[0-9a-f]{32}',authorization_id):raise ValueError('exact authorization required')
    record=a.load(state/(authorization_id+'.approval.json'))
    review=approval.read_review(state,record['review_id'])
    if a.digest(Path(policy).read_bytes())!=review['policy_sha256']:raise ValueError('policy changed since review')
    for field in ('profile','codex_config'):
        path=trusted(review[field])
        if a.digest(path.read_bytes())!=review[field+'_sha256']:raise ValueError('reviewed session configuration changed')
    for name,h in review['runner_files'].items():
        path=trusted(Path(__file__).with_name(name))
        if a.digest(path.read_bytes())!=h:raise ValueError('reviewed runner changed')
    trusted(Path(__file__))
    # Resolve the trusted Python symlink explicitly, retaining its approved path in argv.
    trusted((RELEASE/'venv/bin/python').resolve(strict=True));trusted(RELEASE/'hermes')
    account=pwd.getpwnam('jarvis-codex-engineering')
    if account.pw_uid!=996 or account.pw_gid!=996 or set(os.getgrouplist(account.pw_name,996))!={996}:raise ValueError('dedicated account changed')
    worker_base=worker_root(workers)
    slot()
    # Exclusive one-use approval before staging/launch. Any later ambiguity consumes it.
    review=approval.consume(state,authorization_id)
    run_id=uuid.uuid4().hex;root=worker_base/('approved-'+run_id);job=jobs/run_id
    job.mkdir(mode=0o750);os.chown(job,0,996)
    root.mkdir(mode=0o700);os.chown(root,996,996)
    repo=root/'repo';work=root/'work';work.mkdir(mode=0o700);os.chown(work,996,996)
    env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'}
    def git(*args):subprocess.run(['/usr/bin/git',*args],env=env,stdin=subprocess.DEVNULL,capture_output=True,check=True,timeout=60)
    git('-c','core.hooksPath=/dev/null','clone','--quiet','--no-hardlinks',review['canonical_repository'],str(repo))
    git('-C',str(repo),'remote','remove','origin')
    git('-C',str(repo),'-c','core.hooksPath=/dev/null','checkout','--detach',review['baseline_commit'])
    if a.git(repo,'rev-parse','HEAD').decode().strip()!=review['baseline_commit']:raise ValueError('baseline mismatch')
    for path in (repo,*repo.rglob('*')):
        os.chown(path,996,996,follow_symlinks=False)
    registry={'schema_version':1,'repositories':[{'repository_id':review['request']['repository_id'],'path':str(repo),'enabled':True,'hermes_project':review['hermes_project']}]}
    for name,data in [('registry.json',registry),('request.json',review['request'])]:
        a.absent(job/name,a.encoded(data));os.chown(job/name,0,996);(job/name).chmod(0o440)
    link={'authorization_id':authorization_id,'review_id':record['review_id'],'submission_id':review['submission_id'],
          'run_id':run_id,'unit':UNIT,'work':str(work),'job':str(job),'publication_authorized':False}
    if review.get('review_branch'):link['review_branch']=review['review_branch']
    a.absent(state/(authorization_id+'.launch.json'),a.encoded(link))
    # systemd enforces fixed-name exclusivity even if concurrent operators both passed slot().
    result=command(argv(work,job,review,credential),timeout=430)
    a.absent(state/(authorization_id+'.service-output.txt'),(result.stdout+result.stderr).encode())
    outcome=command(['/usr/bin/systemctl','show',UNIT,'-p','LoadState','--value'])
    peers=command(['/usr/bin/pgrep','-u','996'])
    stopped=outcome.returncode==0 and outcome.stdout.strip()=='not-found' and peers.returncode==1
    answer=dict(link,service_exit=result.returncode,host_stop_verified=stopped)
    a.absent(state/(authorization_id+'.result.json'),a.encoded(answer))
    return answer

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('state','authorization-id','jobs','workers','policy','credential'):p.add_argument('--'+name,required=True)
    args=p.parse_args()
    if os.geteuid()!=0:p.error('operator administrator invocation required')
    result=launch(args.state,args.authorization_id,args.jobs,args.workers,args.policy,args.credential)
    print(json.dumps(result));raise SystemExit(0 if result['service_exit']==0 and result['host_stop_verified'] else 1)
