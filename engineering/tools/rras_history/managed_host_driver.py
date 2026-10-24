"""Root stdlib controller for one fixed isolated managed-link acceptance."""
import grp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
spec_path=Path(__file__).with_name('managed_host_package.py')
spec=importlib.util.spec_from_file_location('managed_host_spec',spec_path)
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
STATE=p.STATE;SERVICE=p.SERVICE;CLIENT=p.CLIENT;UNKNOWN=p.UNKNOWN
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}
ROLES={'seed':0,'export':0,'init':SERVICE,'service':SERVICE,'lost-response':CLIENT,'resume':CLIENT,'replay':CLIENT,'ready':CLIENT}


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected fixture path required')


def command(role,uid=None):
    expected=ROLES.get(role)
    if role=='denial':
        if uid not in (CLIENT,UNKNOWN,996):raise ValueError('unknown denial identity')
    elif expected is None or (uid is not None and uid!=expected):raise ValueError('unknown role/identity')
    else:uid=expected
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(uid),'--regid',str(uid),'--clear-groups',
            '--pdeathsig=TERM','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
            str(PYTHON),'-I','-B',str(ROOT/'engineering/tools/rras_history/managed_host_probe.py'),role]


def write(path,raw,uid=0,gid=0,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchown(stream.fileno(),uid,gid);os.fchmod(stream.fileno(),mode)
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


def mkdir(path,uid=0,gid=0,mode=0o700):
    path.mkdir(mode=mode);os.chown(path,uid,gid);os.chmod(path,mode)


def unused():
    ids={SERVICE,CLIENT,UNKNOWN}
    if any(user.pw_uid in ids for user in pwd.getpwall()) or any(group.gr_gid in ids for group in grp.getgrall()):
        raise ValueError('fixture numeric identity already allocated')
    for path in Path('/proc').glob('[0-9]*/status'):
        try:lines=path.read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError):continue
        for line in lines:
            if line.startswith(('Uid:','Gid:','Groups:')) and set(map(int,line.split()[1:]))&ids:
                raise ValueError('fixture numeric identity already active')


class Fixture:
    def __init__(self):self.process=None;self.streams=[];self.counter=0
    def child(self,role,uid=None):
        args=command(role,uid);result=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,env=ENV,cwd=ROOT,timeout=30)
        self.counter+=1
        write(STATE/f'{self.counter:02d}-{role}-stdout.json',result.stdout)
        write(STATE/f'{self.counter:02d}-{role}-stderr.txt',result.stderr)
        if result.returncode:raise ValueError('isolated role failed; preserve private diagnostic')
        record=json.loads(result.stdout)
        expected=int(args[args.index('--reuid')+1])
        if record['boundary']['uid']!=expected:raise ValueError('fixture peer differs')
        return record['result']
    def start(self):
        if self.process is not None:raise ValueError('fixture service already running')
        self.counter+=1
        self.streams=[(STATE/f'{self.counter:02d}-service-{kind}.txt').open('xb') for kind in ('stdout','stderr')]
        self.process=subprocess.Popen(command('service'),stdin=subprocess.DEVNULL,stdout=self.streams[0],stderr=self.streams[1],
                                      cwd=ROOT,env=ENV,start_new_session=True)
        deadline=time.monotonic()+10
        while not (STATE/'runtime/service.sock').exists():
            if self.process.poll() is not None or time.monotonic()>deadline:raise ValueError('fixture service readiness failed')
            time.sleep(0.05)
        if self.child('ready')!={'ready':True}:raise ValueError('fixture readiness probe differs')
    def stop(self):
        if self.process is None:return
        proc=self.process
        try:
            if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
            try:code=proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
                raise ValueError('fixture forced stop; acceptance uncertain')
            if code or (STATE/'runtime/service.sock').exists():raise ValueError('fixture graceful stop failed')
            for stream in self.streams:stream.flush()
            record=json.loads(Path(self.streams[0].name).read_bytes())
            if record['boundary']['uid']!=SERVICE or record['result']!={'stopped':True}:raise ValueError('fixture service stop record differs')
            if Path(self.streams[1].name).stat().st_size:raise ValueError('fixture service diagnostic retained')
        finally:
            for stream in self.streams:stream.close()
            self.streams=[];self.process=None


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator fixture invocation required')
    for path in (STATE.parent,Path(__file__),PYTHON.parent,PYTHON.resolve(strict=True),Path('/usr/bin/setpriv'),
                 Path('/usr/bin/unshare'),Path('/usr/bin/setfacl')):protected(path)
    if STATE.exists() or STATE.is_symlink():raise ValueError('preserve prior fixture; no automatic retry')
    unused();os.umask(0o077);mkdir(STATE,mode=0o711)
    for name in ('source','export'):mkdir(STATE/name)
    mkdir(STATE/'history',SERVICE,SERVICE);mkdir(STATE/'runtime',SERVICE,SERVICE)
    mkdir(STATE/'client',CLIENT,CLIENT);mkdir(STATE/'client/input',CLIENT,CLIENT)
    policy={'contract':'engineering-history-access.v1','principals':[{'uid':CLIENT,'private_read':['example_library'],'write':['example_library']}]}
    write(STATE/'policy.json',p.encoded(policy),gid=SERVICE,mode=0o640)
    fixture=Fixture()
    try:
        fixture.child('seed');source=STATE/'source/workflow.sqlite3';before=hashlib.sha256(source.read_bytes()).hexdigest()
        result=fixture.child('export')
        if result!={'pages':2,'source_mutations':False,'first_after':1,'second_after':2}:raise ValueError('fixture export pages differ')
        for name in ('work','first','second'):
            raw=p.regular(STATE/'export'/(name+'.json'),128*1024)
            write(STATE/'client/input'/(name+'.json'),raw,CLIENT,CLIENT)
            if hashlib.sha256(raw).hexdigest()!=hashlib.sha256((STATE/'client/input'/(name+'.json')).read_bytes()).hexdigest():
                raise ValueError('private handoff changed bytes')
        fixture.child('init');fixture.start()
        for uid in (CLIENT,UNKNOWN,996):fixture.child('denial',uid)
        if fixture.child('lost-response')!={'pending_retained':True,'cursor_advanced':False}:raise ValueError('lost-response fixture differs')
        fixture.stop();fixture.start()
        if fixture.child('resume')!={'next_after':2,'receipts':2,'authority_granted':False}:raise ValueError('resumed delivery differs')
        fixture.stop();fixture.start()
        if fixture.child('replay')!={'history_records':3,'same_receipt_replay':True,'source_observation_not_promoted':True}:raise ValueError('replay fixture differs')
        fixture.stop()
        if hashlib.sha256(source.read_bytes()).hexdigest()!=before:raise ValueError('private source journal changed')
        result={'phase':'isolated_managed_history_handoff_verified','root':str(STATE),'service_uid':SERVICE,'client_uid':CLIENT,
                'cases':['root_readonly_allowlisted_export','private_exact_byte_distinct_uid_handoff',
                         'source_history_policy_and_unknown_worker_denials','private_network_no_groups_no_caps_no_provider_env',
                         'post_commit_lost_response_preserves_pending_cursor','service_restart_resumes_two_pages',
                         'second_restart_exact_receipt_replay_no_duplicates','observed_source_claim_remains_imported_no_authority'],
                'source_journal_unchanged':True,'fixture_service_stopped':True,'fixture_socket_removed':True,
                'permanent_accounts_created':False,'production_services_mutated':False,'production_journal_changed':False,
                'production_history_changed':False,'real_credentials_used':False,'api_calls':0,'automatic_retry':False}
        write(STATE/'complete.json',p.encoded(result));return result
    except BaseException:
        write(STATE/'failure-private.txt',traceback.format_exc().encode())
        raise
    finally:fixture.stop()


if __name__=='__main__':
    def interrupted(*_):raise RuntimeError('fixture interrupted; preserve evidence')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:print(json.dumps(run()))
    except Exception as error:
        frames=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(error.__traceback__)]
        print(json.dumps({'phase':'managed_history_host_stopped','exception_type':type(error).__name__,'frames':frames,
                          'protected_evidence':str(STATE),'automatic_retry':False}),file=sys.stderr);raise SystemExit(1)
