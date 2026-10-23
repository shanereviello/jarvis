"""Fixed isolated systemd fixture for the production history unit and ACL entry.

Root orchestrator imports only pinned stdlib tooling. All narrative/runtime code
runs as numeric unprivileged principals. No production service/account is installed.
"""
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
STATE=Path('/var/lib/rras-history-unit-acceptance-20261022')
NAME='rras-history-unit-acceptance-20261022'
UNIT=NAME+'.service'
UNIT_FILE=Path('/run/systemd/system')/UNIT
RUNTIME=Path('/run')/NAME
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}
SERVICE=61081


def local(name):
    path=Path(__file__).with_name(name+'.py')
    spec=importlib.util.spec_from_file_location('unit_acceptance_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def fixture_unit(original,release):
    """Only fixture identities/paths/conditions change; hardening stays identical."""
    text=original.decode()
    text=text.replace('User=rras-history\n','User=61081\n').replace('Group=rras-history\n','Group=61081\nSupplementaryGroups=\n')
    text=text.replace('/var/lib/rras-engineering-history',str(STATE/'private'))
    text=text.replace('/etc/rras-engineering-history/access-policy.json',str(STATE/'policy.json'))
    text=text.replace('/run/rras-engineering-history',str(RUNTIME))
    text=text.replace('RuntimeDirectory=rras-engineering-history\n','RuntimeDirectory='+NAME+'\n')
    # The protected fixture release contains exactly the pinned runtime subset.
    original_release=json.loads((Path(release)/'runtime-manifest.json').read_bytes())['release']
    text=text.replace(original_release,str(release))
    entry=str(Path(release)/'engineering/tools/rras_history/production_entry.py')
    start=f'ExecStart={PYTHON} -I -B {entry} serve'
    arguments=f' --account {SERVICE} --store {STATE}/private --socket {RUNTIME}/service.sock --policy {STATE}/policy.json'
    if text.count(start+'\n')!=1:raise ValueError('exact fixture command binding required')
    text=text.replace(start+'\n',start+arguments+'\nExecStartPost='+str(PYTHON)+' -I -B '+str(Path(release)/'engineering/tools/rras_history/unit_acceptance_probe.py')+' unit-check\n')
    text=text.replace('TimeoutStopSec=15s\n','TimeoutStopSec=15s\nTimeoutStartSec=25s\nRuntimeMaxSec=180s\n')
    text=text.split('\n[Install]\n',1)[0]+'\n'
    return text.encode()


def write(path,raw,mode=0o600,gid=0):
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),0,gid)
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


def encode(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def control(action):
    if action not in ('start','stop'):raise ValueError('fixed fixture action required')
    return ['/usr/bin/systemctl',action,UNIT]


def child_command(role,uid):
    if uid not in (61081,61082,61083,61084,61085,996,997,1000):raise ValueError('unknown fixture UID')
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(uid),'--regid',str(uid),
            '--clear-groups','--pdeathsig=TERM','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
            str(PYTHON),'-I','-B',str(ROOT/'engineering/tools/rras_history/unit_acceptance_probe.py'),role]


class Fixture:
    def __init__(self):self.counter=0;self.installed=False;self.unit_sha=None;self.probe_errors=[]

    def log(self,tag,result):
        self.counter+=1
        write(STATE/f'{self.counter:03d}-{tag}-stdout.txt',result.stdout)
        write(STATE/f'{self.counter:03d}-{tag}-stderr.txt',result.stderr)

    def child(self,role,uid=61082,message=None):
        result=subprocess.run(child_command(role,uid),input=b'' if message is None else encode(message),
                              capture_output=True,env=ENV,cwd=ROOT,timeout=20)
        self.log('child-'+role,result)
        if result.returncode:raise ValueError('isolated unit probe failed')
        record=json.loads(result.stdout)
        if record['contract']!='history-unit-probe.v1' or record['identity']['uid']!=uid:raise ValueError('fixture probe association differs')
        return record['result']

    def rpc(self,message,uid=61082,accepted=True):
        value=self.child('rpc',uid,message)
        if value['accepted'] is not accepted:raise ValueError('fixture access decision differs')
        return value.get('value')

    def systemctl(self,action):
        result=subprocess.run(control(action),stdin=subprocess.DEVNULL,capture_output=True,env=ENV,timeout=45)
        self.log('systemctl-'+action,result)
        if result.returncode:raise ValueError('fixture unit action failed')

    def show(self):
        result=subprocess.run(['/usr/bin/systemctl','show',UNIT,'--property=ActiveState,SubState,MainPID,ExecMainCode,ExecMainStatus,LoadState'],
                              capture_output=True,env=ENV,check=True,timeout=10)
        return dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)

    def start(self):
        self.systemctl('start')
        value=self.show()
        if value.get('ActiveState')!='active' or int(value['MainPID'])<1:raise ValueError('fixture unit not active')
        pid=int(value['MainPID']);fields=dict(line.split(':',1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
        if set(fields['Uid'].split())!={str(SERVICE)} or set(fields['Gid'].split())!={str(SERVICE)} or not set(fields['Groups'].split())<={str(SERVICE)}:
            raise ValueError('fixture service identity/group differs')
        if fields['NoNewPrivs'].strip()!='1' or any(int(fields[k].strip(),16) for k in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')):
            raise ValueError('fixture service privilege differs')
        if os.readlink(f'/proc/{pid}/ns/net')==os.readlink('/proc/self/ns/net'):raise ValueError('unit network namespace not private')
        # ExecStartPost has already verified RO mounts, writable store, AF_INET
        # refusal and restricted /proc inside the actual hardened unit.
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            result=self.child('rpc',1000,dict(method='history',repository_id='example',offset=0,limit=1))
            if result['accepted']:return
            time.sleep(0.1)
        raise ValueError('fixture socket not ready')

    def stop(self):
        self.systemctl('stop')
        value=self.show()
        if int(value.get('MainPID','0'))!=0 or value.get('ActiveState') not in ('inactive','failed'):
            raise ValueError('fixture unit stop uncertain')
        if (RUNTIME/'service.sock').exists():raise ValueError('fixture socket retained after normal stop')

    def journal(self):
        result=subprocess.run(['/usr/bin/journalctl','--unit',UNIT,'--no-pager','--output=json','-n','40'],
                              capture_output=True,env=ENV,timeout=15)
        self.log('private-unit-journal',result)
        for line in result.stdout.splitlines():
            try:
                message=json.loads(json.loads(line).get('MESSAGE',''))
                if message.get('contract')!='history-unit-probe-error.v1':continue
                frames=[dict(file=Path(f['file']).name[:96],function=f['function'][:96],line=int(f['line'])) for f in message['frames'][:8]]
                self.probe_errors.append(dict(exception_type=message['exception_type'][:64],frames=frames))
            except (ValueError,TypeError,KeyError,AttributeError):continue

    def cleanup_unit(self):
        if not self.installed:return
        self.stop()
        if hashlib.sha256(UNIT_FILE.read_bytes()).hexdigest()!=self.unit_sha:raise ValueError('fixture runtime unit changed')
        UNIT_FILE.unlink()
        subprocess.run(['/usr/bin/systemctl','daemon-reload'],stdin=subprocess.DEVNULL,capture_output=True,env=ENV,check=True,timeout=20)
        self.installed=False


def policy(revoked=False):
    peers=[dict(uid=1000,private_read=['example'],write=['example']),dict(uid=61083,private_read=['other'],write=['other']),
           dict(uid=61085,private_read=['example'],write=[])]
    if not revoked:peers.append(dict(uid=61082,private_read=['example'],write=['example']))
    return dict(contract='engineering-history-access.v1',principals=peers)


def history(repo):return dict(method='history',repository_id=repo,offset=0,limit=100)


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('reviewed administrator invocation required')
    old=local('host_acceptance');package=local('production_package')
    for path in (STATE.parent,UNIT_FILE.parent,RUNTIME.parent,Path(__file__),PYTHON.parent,PYTHON.resolve(strict=True)):
        old.protected(path)
    for name in ('/usr/bin/systemctl','/usr/bin/journalctl','/usr/bin/setfacl','/usr/bin/getfacl','/usr/bin/unshare','/usr/bin/setpriv'):
        old.protected(Path(name))
    for path in (STATE,RUNTIME,UNIT_FILE):
        if path.exists() or path.is_symlink():raise ValueError('preserve existing fixture; no automatic retry')
    old.ids_unused()
    import grp
    if any(g.gr_gid in range(61081,61086) for g in grp.getgrall()):raise ValueError('fixture primary GID already allocated')
    existing=subprocess.run(['/usr/bin/systemctl','show',UNIT,'--property=LoadState','--value'],capture_output=True,env=ENV,timeout=10)
    if existing.stdout.strip() not in (b'not-found',b''):raise ValueError('fixture unit already exists')
    runtime_manifest=(ROOT/'runtime-manifest.json').read_bytes()
    manifest,_=package.verify(ROOT,hashlib.sha256(runtime_manifest).hexdigest())
    os.umask(0o077);old.mkdir(STATE)
    old.mkdir(STATE/'private',0o700,SERVICE,SERVICE)
    for uid in (61082,1000):old.mkdir(STATE/('client-'+str(uid)),0o700,uid,uid)
    old.mkdir(STATE/'root-private',0o700);write(STATE/'root-private/sentinel',b'synthetic root fixture\n')
    write(STATE/'outside-write-probe',b'synthetic read-only mount probe\n',0o666)
    write(STATE/'policy.json',encode(policy()),0o640,SERVICE)
    fixture=Fixture();cases=[]
    try:
        # Initialization uses the unchanged production entry under the service UID.
        command=child_command('unused',SERVICE)
        command=command[:command.index(str(PYTHON))]+[str(PYTHON),'-I','-B',str(ROOT/'engineering/tools/rras_history/production_entry.py'),
                 'initialize-empty','--account',str(SERVICE),'--store',str(STATE/'private')]
        result=subprocess.run(command,capture_output=True,env=ENV,cwd=ROOT,timeout=20);fixture.log('initialize-empty',result)
        if result.returncode or not json.loads(result.stdout)['empty_store_initialized']:raise ValueError('fixture initialization failed')
        offline=fixture.child('client',61082,old.work('example',1))
        assert offline['status']['recording_state']=='pending'
        unit=fixture_unit((ROOT/'deployment/rras-engineering-history.service').read_bytes(),ROOT)
        write(STATE/'fixture.service',unit,0o644)
        verify=subprocess.run(['/usr/bin/systemd-analyze','verify','--man=no','--generators=no',str(STATE/'fixture.service')],capture_output=True,env=ENV,timeout=20)
        fixture.log('unit-verify',verify)
        if verify.returncode:raise ValueError('fixture unit verification failed')
        write(UNIT_FILE,unit,0o644);fixture.installed=True;fixture.unit_sha=hashlib.sha256(unit).hexdigest()
        subprocess.run(['/usr/bin/systemctl','daemon-reload'],stdin=subprocess.DEVNULL,capture_output=True,check=True,env=ENV,timeout=20)
        fixture.start()
        assert fixture.child('flush',61082)['delivered_now']==2
        records=fixture.rpc(history('example'))['records'];first=records[0]['receipt']
        assert first['writer_uid']==SERVICE and first['peer_uid']==61082
        assert len(fixture.rpc(history('example'),1000)['records'])==2
        cases.extend(['actual_hardened_systemd_unit_and_numeric_private_groups','unit_mount_proc_socket_and_privilege_boundaries',
                      'per_uid_acl_access_without_shared_group_and_uid1000','offline_spool_recovered_via_production_entry'])
        fixture.rpc(dict(method='submit',request=old.work('other',2)),61083)
        fixture.rpc(history('other'),61082,False);fixture.rpc(history('example'),61083,False)
        for uid in (61084,996,997):fixture.rpc(history('example'),uid,False)
        fixture.rpc(dict(method='submit',request=old.work('example',3)),61085,False)
        for uid in (61082,61083,61084,61085,996,997,1000):assert all(fixture.child('denial',uid).values())
        cases.append('cross_repository_unknown_worker_reader_and_private_file_denials')

        template=(ROOT/'engineering/docs/engineering-history-phase1/templates/review.md').read_text()
        injected={'work_item_id','work_revision','document_id','document_version','repository_id','created_at_or_unknown'}
        fields={name:'synthetic hardened-unit fixture' for name in set(re.findall(r'\{\{([a-z][a-z0-9_]*)\}\}',template))-injected}
        fields['title']='Synthetic hardened-unit review'
        original=records[0]['submission']
        document=dict(contract='engineering-history.v1',operation='document.render',client_event_key='unit-document',
                      expected_head=first['work_revision_sha256'],source=original['source'],occurred_at=None,
                      body=dict(work_item_id=original['body']['work_item_id'],work_revision_sha256=first['work_revision_sha256'],
                                document_id='doc_'+'7'*32,document_version=1,document_type='review',
                                supersedes_document_sha256=None,fields=fields,references=[]))
        receipt=fixture.rpc(dict(method='submit',request=document))['receipt']
        read=dict(method='document',document_id=document['body']['document_id'],version=1)
        fetched=fixture.rpc(read,61085)
        assert hashlib.sha256(fetched['markdown'].encode()).hexdigest()==receipt['document_manifest']['markdown_sha256']
        fixture.rpc(read,61083,False);fixture.rpc(dict(method='execute'),1000,False)
        cases.append('actual_unit_immutable_document_and_no_action_route')

        fixture.stop();fixture.start()
        duplicate=fixture.rpc(dict(method='submit',request=records[0]['submission']))
        assert duplicate==dict(inserted=False,receipt=first)
        cases.append('actual_unit_restart_preserves_exact_receipt')
        fixture.stop()
        write(STATE/'policy-before-revocation.json',(STATE/'policy.json').read_bytes())
        write(STATE/'policy.next',encode(policy(revoked=True)),0o640,SERVICE)
        os.replace(STATE/'policy.next',STATE/'policy.json')
        fixture.start()
        fixture.rpc(dict(method='submit',request=records[0]['submission']),61082,False)
        for path in (RUNTIME,RUNTIME/'service.sock'):
            text=subprocess.check_output(['/usr/bin/getfacl','--numeric','--omit-header',str(path)],env=ENV,text=True)
            assert 'user:61082:' not in text and 'default:' not in text
        assert len(fixture.rpc(history('example'),1000)['records'])==3
        cases.append('restart_revocation_removes_acl_and_blocks_replay')
        assert (STATE/'outside-write-probe').read_bytes()==b'synthetic read-only mount probe\n'
        fixture.journal();fixture.cleanup_unit()
        answer=dict(phase='isolated_history_hardened_unit_verified',root=str(STATE),unit=UNIT,service_uid=SERVICE,
                    client_uids=[61082,61083,1000],cases=cases,api_calls=0,real_credentials_used=False,permanent_accounts_created=False,
                    production_configuration_changed=False,production_services_mutated=False,production_journal_changed=False,
                    fixture_unit_stopped=True,fixture_runtime_unit_removed=True,fixture_socket_removed=True,automatic_retry=False,
                    runtime_payload_sha256=manifest['payload_sha256'])
        write(STATE/'result.json',encode(answer));return answer
    except BaseException as exc:
        write(STATE/'failure-private.txt',traceback.format_exc().encode())
        try:fixture.journal()
        except Exception:pass
        try:
            if fixture.installed:fixture.stop()
        except Exception:write(STATE/'stop-failure-private.txt',traceback.format_exc().encode())
        # Error metadata only, never journal messages or narrative/config values.
        frames=[dict(file=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(exc.__traceback__)]
        print(json.dumps(dict(phase='history_unit_acceptance_stopped',exception_type=type(exc).__name__,frames=frames,
                              protected_evidence=str(STATE),probe_errors=fixture.probe_errors[-4:],automatic_retry=False)),file=sys.stderr)
        raise ValueError('fixture stopped; preserve evidence') from None


if __name__=='__main__':
    try:
        def interrupted(*_):raise RuntimeError('fixture interrupted')
        signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
        print(json.dumps(run(),indent=2))
    except Exception:
        raise SystemExit(1)
