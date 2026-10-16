"""Administrator model-free acceptance using a synthetic worker and sentinel.

Run only from a root-owned review whose manual_runner.py is the reviewed fake
below. Never use this probe with the real coding runner or a provider credential.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

SENTINEL='RRAS-APPROVAL-OFFLINE-FIXTURE'
FAKE_WORKER='''import argparse,json,os,time
from pathlib import Path
import importlib.util
p=argparse.ArgumentParser()
for name in ('source','python','profile','codex-config','registry','request','work','credential'):p.add_argument('--'+name,required=True)
p.add_argument('--authorize-one-paid-task',action='store_true');a=p.parse_args()
spec=importlib.util.spec_from_file_location('credentials',Path(__file__).with_name('credentials.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert os.getuid()==996 and m.delivered_key(a.credential)=='RRAS-APPROVAL-OFFLINE-FIXTURE'
work=Path(a.work);(work/'fake-ready.json').write_text(json.dumps({'scope':'approval-fake-worker','uid':996,'api_calls':0}))
time.sleep(3)
(work/'evidence.json').write_text(json.dumps({'scope':'approval-fake-worker','success':True,'api_calls':0,'uid':996}))
print(json.dumps({'scope':'approval-fake-worker','success':True,'api_calls':0}))
'''


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def run(control,jobs,workers):
    if os.geteuid()!=0:raise ValueError('administrator acceptance required')
    here=Path(__file__).parent
    if (here/'manual_runner.py').read_text()!=FAKE_WORKER:raise ValueError('synthetic worker required; do not run real tasks')
    launch=local('approved_launch');approval=local('approval');a=local('activity')
    launch.trusted(here);launch.slot()
    control,jobs,workers=Path(control),Path(jobs),Path(workers)
    for p in (control,jobs,workers):
        if p.exists() or p.is_symlink():raise ValueError('fresh acceptance roots required')
    control.mkdir(mode=0o700);jobs.mkdir(mode=0o755);workers.mkdir(mode=0o700);os.chown(workers,996,996)
    repo=control/'canonical';repo.mkdir()
    def git(*args):subprocess.run(['/usr/bin/git','-C',str(repo),*args],check=True,capture_output=True)
    git('init','-q');(repo/'value.py').write_text('value=0\n');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','fixture')
    policy=control/'policy.json';request={'schema_version':1,'task_id':'TASK-approval-fixture','repository_id':'fixture','objective':'Fixture only; no model execution','allowed_paths':['value.py'],'validation_argv':['/usr/bin/true'],'worker_timeout_seconds':30,'validation_timeout_seconds':10,'commit_policy':'leave_uncommitted'}
    policy.write_text(json.dumps({'schema_version':1,'identities':{'hermes':['fixture']},'repositories':{'fixture':{'enabled':True,'allowed_paths':['value.py'],'validations':{'fixture':['/usr/bin/true']},'worker_timeout_seconds':30,'validation_timeout_seconds':10}}}))
    proposals=control/'proposals';proposals.mkdir();receipt={'schema_version':1,'authenticated_identity':'hermes','policy_sha256':a.digest(policy.read_bytes()),'request':request,'execution_authorized':False,'publication_authorized':False}
    submission=a.digest(a.encoded(receipt));(proposals/(submission+'.json')).write_bytes(a.encoded(receipt))
    registry=control/'registry.json';registry.write_text(json.dumps({'schema_version':1,'repositories':[{'repository_id':'fixture','path':str(repo),'enabled':True,'hermes_project':'fixture'}]}))
    profile=here/'profile.json';codex=here/'codex-config.toml'
    result=approval.capture(proposals,submission,policy,registry,control/'approvals',profile,codex)
    first=approval.approve(control/'approvals',result['review_id']);second=approval.approve(control/'approvals',result['review_id'])
    key=control/'sentinel';key.write_text(SENTINEL);key.chmod(0o600)
    def invoke(authorization):return launch.launch(control/'approvals',authorization,jobs,workers,policy,key)
    busy_refused=False
    with ThreadPoolExecutor(max_workers=1) as executor:
        future=executor.submit(invoke,first['authorization_id']);deadline=time.monotonic()+30
        ready=False
        while time.monotonic()<deadline and not future.done():
            ready=bool(list(workers.glob('approved-*/work/fake-ready.json')))
            if ready:break
            time.sleep(.05)
        if ready:
            try:invoke(second['authorization_id'])
            except ValueError as error:busy_refused='launch slot' in str(error) or 'identity busy' in str(error)
        finished=future.result(timeout=430)
    if not ready or not busy_refused or not finished['host_stop_verified'] or finished['service_exit']!=0:raise ValueError('slot or stop acceptance failed; retain all records')
    if (control/'approvals'/(second['authorization_id']+'.consumed.json')).exists():raise ValueError('busy check consumed second approval')
    replay_refused=False
    try:invoke(first['authorization_id'])
    except FileExistsError:replay_refused=True
    if not replay_refused:raise ValueError('approval replay accepted')
    status={'scope':'approved-launch-installed-systemd-fake-worker','success':True,'api_calls':0,
            'real_credentials_used':False,'coding_session_tested':False,'worker_uid':996,
            'submission_id':submission,'review_id':result['review_id'],'run':finished,
            'cases':['root_capture','exact_review','one_use_approval','fresh_clone','systemd_sentinel_delivery','fixed_slot_exclusion','busy_approval_preserved','verified_host_stop','replay_refused'],
            'control':str(control),'jobs':str(jobs),'workers':str(workers)}
    a.absent(control/'evidence.json',a.encoded(status));return status

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('control','jobs','workers'):p.add_argument('--'+n,required=True)
    args=p.parse_args();print(json.dumps(run(args.control,args.jobs,args.workers)))
