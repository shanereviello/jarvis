"""Accept root broker and journal-owner cutover together in an offline container."""
import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
BASE = Path('/tmp/rras-cutover-integrated');PEER = 61183
uid = lambda n:str(uuid.UUID(int=n))
AUTH = dict(authorized=True,grant_id='fixture',reference='Synthetic fixture',policy_sha256='e'*64)


def local(name):
    spec = importlib.util.spec_from_file_location('integrated_probe_'+name,Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def drop():
    os.setgroups([]);os.setgid(PEER);os.setuid(PEER)


def setup():
    if os.getuid() != PEER:raise ValueError('fixture journal identity required')
    runtime = local('codex_runtime');draft = local('onboarding_drafts');issue = uid(11);plan_id = 'PLAN-01'
    old = dict(contract='codex-runtime-policy.v2',organization_id=uid(1),app_user_id=uid(2),execution_authorized=True,
        execution_authority_reference='Synthetic fixture',binary=str(BASE/'binary'),cwd=str(BASE),sandbox='read-only',
        issues={uid(3):dict(project_id='prj_'+'1'*32,work_id='wrk_'+'2'*32,plan_id='OLD',work_revision_sha256='3'*64,
            architecture_version=1,architecture_sha256='4'*64)},workspaces={uid(3):str(BASE/'old')},
        native_sockets={uid(3):str(BASE/('coding-'+uid(3)+'.sock'))})
    request = dict(issue_id=issue,organization_id=uid(1),linear_project_id=uid(10),team_id=uid(12),
        scope={'kind':'repository','id':'jarvis'},project_id=draft.identity('prj_',uid(1),uid(10)),
        work_id=draft.work_identity('wrk_',uid(1),uid(10),plan_id),plan_id=plan_id,work_revision_sha256='a'*64,
        assignment_sha256='b'*64,architecture_version=1,architecture_sha256='c'*64,decision_receipt_sha256='d'*64,
        workspace=str(BASE/'new'),native_socket=str(BASE/('coding-'+issue+'.sock')),baseline_commit='e'*40)
    root = BASE/'journals'/'state';instance = runtime.Runtime(root,old,create=True,issue_client_factory=lambda *_:None);instance.close()
    migration = local('codex_issue_admission_migration');verify = lambda _:True;authority = lambda _:AUTH
    plan = migration.plan(root,request,verify,authority)
    with local('codex_policy_migration').locked(root) as db:
        value, before, after = migration.snapshot(db,request,verify,authority)
    return dict(request=request,plan=plan,transition={'plan':value,'old':before,'new':after})


def peer():
    if os.getuid() != PEER:raise ValueError('fixture journal identity required')
    value = json.loads((BASE/'fixture.json').read_text());files = local('codex_cutover_broker_client').Files(str(BASE/'socket'/'broker.sock'))
    verify = lambda _:files.verify()
    @contextmanager
    def host_lock():
        files.verify();yield
    adapter = local('codex_cutover_journal_adapter').Adapter(BASE/'journals'/'state',value['request'],verify,lambda _:AUTH,files,host_lock)
    result = local('codex_issue_cutover').execute(adapter,expected_plan_sha256=value['plan']['expected_sha256'])
    print(json.dumps(result,sort_keys=True))


def inside():
    if not Path('/.dockerenv').exists() or os.getuid() != 0:raise ValueError('isolated root container required')
    devices = {line.split(':',1)[0].strip() for line in Path('/proc/self/net/dev').read_text().splitlines() if ':' in line}
    if devices != {'lo'}:raise ValueError('network-isolated fixture required')
    BASE.mkdir(mode=0o755);audit=BASE/'audit';audit.mkdir(mode=0o700)
    journals=BASE/'journals';journals.mkdir(mode=0o700);os.chown(journals,PEER,PEER)
    sockdir=BASE/'socket';sockdir.mkdir(mode=0o750);os.chown(sockdir,0,PEER)
    env=dict(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8')
    command=[sys.executable,'-I','-B',str(Path(__file__))]
    initial=subprocess.run(command+['--setup'],preexec_fn=drop,env=env,capture_output=True,text=True,timeout=20)
    if initial.returncode:raise ValueError('fixture journal setup failed: '+initial.stderr[-1000:])
    value=json.loads(initial.stdout);fixture=BASE/'fixture.json';fixture.write_text(json.dumps(value));fixture.chmod(0o644)
    runtime=local('codex_runtime');policy=BASE/'policy.json';policy.write_bytes(runtime.encoded(value['transition']['old']));os.chown(policy,0,PEER);policy.chmod(0o640)
    files=local('codex_cutover_root_files').Files(policy,audit)
    journal=local('codex_cutover_journal_reader').Reader(BASE/'journals'/'state',PEER)
    broker=local('codex_cutover_fixed_broker').Broker(peer_uid=PEER,transition=value['transition'],files=files,
        verify_stopped=lambda:True,verify_journal=journal,verify_evidence=lambda _:True)
    server=local('codex_cutover_broker_server')
    with server.listener(BASE/'socket'/'broker.sock',PEER) as listener:
        worker=subprocess.Popen(command+['--peer'],preexec_fn=drop,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+60
            while broker.stage!='complete' and worker.poll() is None and time.monotonic()<deadline:
                server.serve_once(listener,broker)
            out,err=worker.communicate(timeout=10)
            if worker.returncode or broker.stage!='complete':raise ValueError('fixture cutover failed: '+err[-1200:])
            result=json.loads(out)
            if not result['cutover_complete'] or not journal(broker.new,broker.plan_sha) or files.digest()!=broker.new:
                raise ValueError('fixture cutover outcome differs')
        finally:
            if worker.poll() is None:worker.kill();worker.wait()
    print(json.dumps(dict(root_and_journal_owner_cutover_verified=True,distinct_numeric_uids=True,
        policy_and_journal_match=True,network_isolated=True,models_started=0,production_changed=False),sort_keys=True))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('inside','setup','peer','isolated-containers'):parser.add_argument('--'+flag,action='store_true')
    args=parser.parse_args()
    if args.setup:print(json.dumps(setup()));return
    if args.peer:peer();return
    if args.inside:inside();return
    if not args.isolated_containers:parser.error('explicit isolated fixture required')
    name='rras-cutover-integrated-'+uuid.uuid4().hex[:10]
    command=['docker','run','--rm','--name',name,'--pull=never','--network','none','--read-only','--cap-drop','ALL',
        '--cap-add','SETUID','--cap-add','SETGID','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE',
        '--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,nodev,size=64m,mode=1777',
        '--mount','type=bind,source='+str(ROOT)+',target=/fixture/engineering,readonly','--user','0:0',
        '--entrypoint','/usr/bin/env',IMAGE,'-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
        '/opt/hermes/.venv/bin/python','-I','-B','/fixture/engineering/tools/rras_reporting/probe_cutover_integrated_cross_uid.py','--inside']
    try:
        result=subprocess.run(command,capture_output=True,text=True,timeout=90)
        if result.returncode:raise ValueError('isolated cutover fixture failed: '+result.stderr[-2500:])
        print(result.stdout.strip())
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)


if __name__=='__main__':main()
