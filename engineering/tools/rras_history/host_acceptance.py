"""Root orchestrator for a fresh synthetic fixture; never a production installer.

Execute only from a hash-pinned, root-owned release. No third-party code imports
in this privileged process; all history/dependency imports occur after UID drop.
"""
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import sys
import time
import traceback

SERVICE=61081; SHARED=61080; CLIENT_A=61082; CLIENT_B=61083; UNKNOWN=61084; READER=61085
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
RELEASE=Path(__file__).resolve().parents[3]
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def protected(path):
    for p in (path,*path.parents):
        info=p.lstat()
        if p.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('root-custodied acceptance code required')


def fixture_path(path):
    path=Path(path)
    if (path.parent!=Path('/var/lib') or not re.fullmatch('rras-history-acceptance-[a-z0-9-]{1,64}',path.name) or
            path.resolve(strict=False)!=path):raise ValueError('fixed isolated fixture required')
    return path


def ids_unused():
    uids={SERVICE,CLIENT_A,CLIENT_B,UNKNOWN,READER}; gids={SERVICE,SHARED}
    if any(p.pw_uid in uids for p in pwd.getpwall()) or any(g.gr_gid in gids for g in grp.getgrall()):
        raise ValueError('numeric fixture identity already allocated')
    for status in Path('/proc').glob('[0-9]*/status'):
        try: lines=status.read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError):continue
        for line in lines:
            if line.startswith('Uid:') and set(map(int,line.split()[1:]))&uids:
                raise ValueError('numeric fixture UID already active')
            if line.startswith(('Gid:','Groups:')) and set(map(int,line.split()[1:]))&gids:
                raise ValueError('numeric fixture GID already active')


def mkdir(path,mode=0o755,uid=0,gid=0):
    path.mkdir(mode=mode);os.chown(path,uid,gid);os.chmod(path,mode)


def write(path,raw,mode=0o600,gid=0):
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),0,gid)
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def command(role,state,uid):
    gid=SERVICE if uid==SERVICE else SHARED
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(uid),'--regid',str(gid),
            '--groups',str(SHARED),'--pdeathsig=TERM','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
            str(PYTHON),'-I','-B',str(RELEASE/'engineering/tools/rras_history/host_probe.py'),role,str(state)]


class Fixture:
    def __init__(self,state):self.state=state;self.counter=0;self.process=None;self.handles=[]

    def child(self,role,uid=CLIENT_A,message=None):
        result=subprocess.run(command(role,self.state,uid),input=b'' if message is None else encoded(message),
                              capture_output=True,env=ENV,cwd=RELEASE,timeout=25)
        self.counter+=1
        write(self.state/f'child-{self.counter:02d}-stdout.json',result.stdout)
        write(self.state/f'child-{self.counter:02d}-stderr.txt',result.stderr)
        if result.returncode!=0:raise ValueError('isolated child failed')
        record=json.loads(result.stdout)
        if record['boundary']['uid']!=uid:raise ValueError('child identity differs')
        return record['result']

    def start(self):
        if self.process is not None:raise ValueError('fixture service already started')
        self.counter+=1
        stdout=(self.state/f'service-{self.counter:02d}-stdout.json').open('xb')
        stderr=(self.state/f'service-{self.counter:02d}-stderr.txt').open('xb')
        self.handles=[stdout,stderr]
        self.process=subprocess.Popen(command('service',self.state,SERVICE),stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                                      env=ENV,cwd=RELEASE,start_new_session=True)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if self.process.poll() is not None:raise ValueError('fixture service stopped during startup')
            if (self.state/'runtime/service.sock').exists():return
            time.sleep(0.05)
        raise ValueError('fixture service startup timeout')

    def stop(self):
        if self.process is None:return
        p=self.process
        try:
            if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
            try:code=p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
                raise ValueError('fixture forced stop; acceptance uncertain')
            if code!=0:raise ValueError('fixture service exit differs')
            if (self.state/'runtime/service.sock').exists():raise ValueError('fixture socket retained after graceful stop')
            self.handles[0].flush()
            record=json.loads(Path(self.handles[0].name).read_text())
            if record['boundary']['uid']!=SERVICE:raise ValueError('service identity differs')
            if Path(self.handles[1].name).stat().st_size:raise ValueError('fixture service diagnostic retained')
        finally:
            for stream in self.handles:stream.close()
            self.handles=[];self.process=None

    def rpc(self,message,uid=CLIENT_A,accepted=True):
        result=self.child('rpc',uid,message)
        if result['accepted'] is not accepted:raise ValueError('fixture access decision differs')
        return result.get('value')


def work(repo,number):
    return dict(contract='engineering-history.v1',operation='work.create',client_event_key='synthetic-work',expected_head=None,
                source=dict(kind='agent_reported',namespace='host_fixture',id=None),occurred_at=None,
                body=dict(work_item_id='wrk_'+str(number)*32,revision=1,repository_id=repo,title='Synthetic acceptance',
                          objective='Verify fixture isolation',rationale='Exercise local history boundary only',
                          acceptance_criteria=[dict(id='AC1',description='No authority inferred')],
                          allowed_paths=['docs/synthetic.md'],baseline=None))


def history(repo):return dict(method='history',repository_id=repo,offset=0,limit=100)


def run(state):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('reviewed administrator invocation required')
    state=fixture_path(state);protected(state.parent);protected(Path(__file__));protected(PYTHON.parent)
    protected(PYTHON.resolve(strict=True))
    for tool in ('/usr/bin/unshare','/usr/bin/setpriv'):protected(Path(tool))
    if state.exists() or state.is_symlink():raise ValueError('preserve prior fixture; no automatic retry')
    ids_unused();os.umask(0o077)
    mkdir(state);mkdir(state/'private',0o700,SERVICE,SERVICE)
    mkdir(state/'runtime',0o2750,SERVICE,SHARED)
    mkdir(state/'client-a',0o700,CLIENT_A,SHARED);mkdir(state/'client-b',0o700,CLIENT_B,SHARED)
    mkdir(state/'root-private',0o700);write(state/'root-private/sentinel',b'synthetic private fixture\n')
    policy=dict(contract='engineering-history-access.v1',principals=[
        dict(uid=CLIENT_A,private_read=['example'],write=['example']),
        dict(uid=CLIENT_B,private_read=['other'],write=['other']),
        dict(uid=READER,private_read=['example'],write=[])])
    write(state/'policy.json',encoded(policy),0o640,SERVICE)
    write(state/'started.json',encoded(dict(scope='isolated-cross-uid-acceptance-only',permanent_accounts_created=False)))
    fixture=Fixture(state);cases=[]
    try:
        assert fixture.child('init',SERVICE)['initialized']
        # Durably queue while no service exists, then recover after startup.
        pending=fixture.child('client',CLIENT_A,dict(kind='start',key='synthetic-start',payload=work('example',1)))
        assert pending['delivered_now']==0 and pending['status']['recording_state']=='pending'
        cases.append('offline_client_queue_preserved')
        fixture.start()
        delivered=fixture.child('flush',CLIENT_A)
        assert delivered['delivered_now']==2 and delivered['status']['context_recorded']
        cases.extend(['actual_distinct_service_and_client_uids','private_network_no_routes_no_caps_no_provider_env'])
        records=fixture.rpc(history('example'))['records']
        assert len(records)==2
        first=records[0]['receipt']
        assert first['writer_uid']==SERVICE and first['peer_uid']==CLIENT_A and first['authority_granted'] is False
        fixture.stop();fixture.start()
        assert fixture.child('flush',CLIENT_A)['delivered_now']==0
        # Re-send the actual committed request to emulate client uncertainty.
        duplicate=fixture.rpc(dict(method='submit',request=records[0]['submission']))
        assert duplicate==dict(inserted=False,receipt=first)
        cases.append('service_restart_and_exact_replay_receipt')
        fixture.rpc(dict(method='submit',request=work('other',2)),CLIENT_B)
        assert len(fixture.rpc(history('other'),CLIENT_B)['records'])==1
        fixture.rpc(history('other'),CLIENT_A,False);fixture.rpc(history('example'),CLIENT_B,False)
        fixture.rpc(dict(method='submit',request=work('other',3)),CLIENT_A,False)
        assert len(fixture.rpc(history('example'))['records'])==2
        cases.append('cross_repository_reads_and_writes_denied')
        for uid in (UNKNOWN,996,997):fixture.rpc(history('example'),uid,False)
        fixture.rpc(dict(method='submit',request=work('example',3)),READER,False)
        assert len(fixture.rpc(history('example'),READER)['records'])==2
        cases.append('unknown_worker_control_denied_read_only_role_enforced')
        for uid in (CLIENT_A,CLIENT_B,UNKNOWN,READER,996,997,1000):
            assert all(fixture.child('denial',uid).values())
        cases.append('actual_private_database_policy_root_fixture_and_source_denial')
        # Render a synthetic review using pinned template fields, not inferred history.
        template=(RELEASE/'engineering/docs/engineering-history-phase1/templates/review.md').read_text()
        injected={'work_item_id','work_revision','document_id','document_version','repository_id','created_at_or_unknown'}
        fields={name:'synthetic fixture only' for name in set(re.findall(r'\{\{([a-z][a-z0-9_]*)\}\}',template))-injected}
        fields['title']='Synthetic cross-UID review'
        doc=dict(contract='engineering-history.v1',operation='document.render',client_event_key='synthetic-document',
                 expected_head=first['work_revision_sha256'],source=dict(kind='agent_reported',namespace='host_fixture',id=None),occurred_at=None,
                 body=dict(work_item_id=records[0]['submission']['body']['work_item_id'],work_revision_sha256=first['work_revision_sha256'],
                           document_id='doc_'+'4'*32,document_version=1,document_type='review',supersedes_document_sha256=None,
                           fields=fields,references=[]))
        rendered=fixture.rpc(dict(method='submit',request=doc))
        read=dict(method='document',document_id=doc['body']['document_id'],version=1)
        fetched=fixture.rpc(read,READER)
        assert hashlib.sha256(fetched['markdown'].encode()).hexdigest()==rendered['receipt']['document_manifest']['markdown_sha256']
        fixture.rpc(read,CLIENT_B,False);fixture.rpc(dict(method='execute'),CLIENT_A,False)
        cases.append('immutable_private_document_bytes_and_no_action_route')
        assert fixture.child('frame')['oversize_refused']
        assert fixture.child('deadline')['incomplete_frame_stopped']
        assert len(fixture.rpc(history('example'))['records'])==3
        cases.append('frame_bounds_deadline_and_service_recovery')
        fixture.stop()
        answer=dict(phase='isolated_history_cross_uid_verified',root=str(state),service_uid=SERVICE,client_uids=[CLIENT_A,CLIENT_B],
                    cases=cases,api_calls=0,real_credentials_used=False,production_configuration_changed=False,
                    production_journal_changed=False,production_services_mutated=False,permanent_accounts_created=False,
                    fixture_service_stopped=True,fixture_socket_removed=True,automatic_retry=False)
        write(state/'result.json',encoded(answer));return answer
    except BaseException:
        write(state/'failure-private.txt',traceback.format_exc().encode())
        try:fixture.stop()
        except BaseException:write(state/'stop-failure-private.txt',traceback.format_exc().encode())
        raise ValueError('acceptance stopped; preserve protected fixture evidence') from None


if __name__=='__main__':
    try:
        if len(sys.argv)!=2:raise ValueError('fixed fixture argument required')
        def interrupted(*_):raise RuntimeError('acceptance interrupted')
        signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
        print(json.dumps(run(sys.argv[1]),indent=2))
    except Exception:
        sys.stderr.write('History host acceptance stopped; preserve protected evidence. No automatic retry.\n')
        raise SystemExit(1)
