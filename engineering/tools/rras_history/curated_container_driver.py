"""Actual hardened reader plus pinned-image MCP rehearsal; synthetic state only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import grp
import subprocess
import sys
import time
import traceback
import stat
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
STATE=Path('/var/lib/rras-curated-container-acceptance-attempt03-20261030')
RUNTIME=Path('/run/rras-curated-container-acceptance-attempt03-20261030')
UNIT='rras-curated-container-acceptance-attempt03-20261030.service'
ACCOUNT='rras-curated-reader-fixture-02'
SERVICE=61154
CLIENT=61155
CONTAINER='rras-curated-container-acceptance-attempt03-20261030-client'
LABEL='rras.fixture=curated-container-acceptance-20261029'
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
PYTHON='/opt/rras-engineering/releases/native-10/venv/bin/python'
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def local(name):
    spec=importlib.util.spec_from_file_location('container_fixture_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def command(argv,raw=None,timeout=30):return subprocess.run(argv,input=raw,capture_output=True,env=ENV,timeout=timeout)


def reader_command():
    text=local('curated_service_plan').service_unit('/opt/rras-engineering/releases/curated-history-'+'a'*12).decode()
    properties=text.split('[Service]\n',1)[1].split('[Install]',1)[0].splitlines()
    values={'User':ACCOUNT,'Group':ACCOUNT,'WorkingDirectory':str(ROOT),'RuntimeDirectory':RUNTIME.name,
            'ReadOnlyPaths':str(STATE/'private/catalog'),'ReadWritePaths':str(RUNTIME)}
    argv=['/usr/bin/systemd-run','--system','--quiet','--collect','--unit='+UNIT,'--service-type=exec']
    for line in properties:
        if not line or '=' not in line:continue
        key,value=line.split('=',1)
        if key in ('Type','ExecStart'):continue
        if key in values:value=values[key]
        if key=='InaccessiblePaths':value+=' '+str(STATE/'private/history')+' '+str(STATE/'source')
        argv+=['--property',key+'='+value]
    argv+=['--property','StandardOutput=append:'+str(STATE/'reader-stdout'),
           '--property','StandardError=append:'+str(STATE/'reader-stderr'),
           '--','/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',PYTHON,'-I','-B',
           str(ROOT/'engineering/tools/rras_history/curated_service_entry.py'),'--account',str(SERVICE),
           '--catalog',str(STATE/'private/catalog'),'--socket',str(RUNTIME/'read.sock'),'--policy',str(STATE/'policy.json')]
    return argv


def container_command(role,uid=CLIENT):
    if role not in ('read','withdrawn','revoked','denied') or uid not in (CLIENT,61156,996,1000,SERVICE,0):raise ValueError('fixed container role required')
    if role!='denied' and uid!=CLIENT:raise ValueError('fixed MCP reader required')
    return ['/usr/bin/docker','run','--rm','--name',CONTAINER,'--label',LABEL,'--stop-timeout','5','-i','--pull=never','--network','none','--read-only',
        '--cap-drop','ALL','--cap-add','SETUID','--cap-add','SETGID','--cap-add','SETPCAP','--security-opt','no-new-privileges:true',
        '--mount','type=bind,source='+str(ROOT)+',target=/opt/curated-fixture,readonly',
        '--mount','type=bind,source='+str(RUNTIME)+',target=/run/curated-fixture,readonly',
        '--entrypoint','/usr/bin/setpriv',IMAGE,'--reuid',str(uid),'--regid',str(uid),'--clear-groups',
        '--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','--no-new-privs',
        '/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8','/opt/hermes/.venv/bin/python','-I','-B',
        '/opt/curated-fixture/engineering/tools/rras_history/curated_container_probe.py',role,str(uid)]


def owner_command(role):
    if role not in ('seed','withdraw'):raise ValueError('fixed synthetic owner role required')
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(SERVICE),'--regid',str(SERVICE),
        '--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',PYTHON,'-I','-B',
        str(ROOT/'engineering/tools/rras_history/curated_reader_probe.py'),role]


def policy(granted=True):return {'contract':'engineering-curated-read-access.v1','principals':[{'uid':CLIENT,'repositories':['example_library']}] if granted else []}


def status():
    result=command(['/usr/bin/systemctl','show',UNIT,'--property=LoadState,ActiveState,MainPID'])
    return dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)


def start():
    result=command(reader_command())
    (STATE/'start-stderr').write_bytes(result.stderr)
    if result.returncode:raise ValueError('reader unit start failed')
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        info=status()
        if info.get('ActiveState')=='active' and (RUNTIME/'read.sock').exists():
            verify_reader(int(info['MainPID']));return
        if info.get('ActiveState') in ('failed','inactive'):break
        time.sleep(0.1)
    raise ValueError('reader did not become active with socket')


def verify_catalog_read_only(proc,catalog):
    # /proc/PID/root traverses the target mount namespace, including an inherited
    # read-only ancestor; a separate bind mount at this exact path is optional.
    target=proc/'root'/str(catalog).lstrip('/')
    if not os.statvfs(target).f_flag & os.ST_RDONLY:raise ValueError('reader catalog filesystem not read-only')


def verify_reader(pid):
    proc=Path('/proc')/str(pid)
    info=dict(line.split(':',1) for line in (proc/'status').read_text().splitlines() if ':' in line)
    if set(info['Uid'].split())!={str(SERVICE)} or set(info['Gid'].split())!={str(SERVICE)} or not set(info['Groups'].split())<={str(SERVICE)}:
        raise ValueError('actual reader identity differs')
    if info['NoNewPrivs'].strip()!='1' or any(int(info[key].strip(),16) for key in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')):
        raise ValueError('actual reader privileges retained')
    if os.readlink(proc/'ns/net')==os.readlink('/proc/self/ns/net'):raise ValueError('reader uses host network namespace')
    verify_catalog_read_only(proc,STATE/'private/catalog')
    for path in (STATE/'private/history',STATE/'source',Path('/var/lib/rras-engineering-history')):
        masked=proc/'root'/str(path).lstrip('/')
        if stat.S_IMODE(masked.stat().st_mode)!=0:raise ValueError('reader private path not masked')


def stop():
    result=command(['/usr/bin/systemctl','stop',UNIT])
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        info=status()
        if info.get('LoadState')=='not-found' and info.get('ActiveState')=='inactive' and info.get('MainPID')=='0':
            if (RUNTIME/'read.sock').exists():raise ValueError('reader socket retained after stop')
            return
        time.sleep(0.1)
    raise ValueError('reader host stop not established')


def container_absent(result):
    message=result.stderr.lower()
    return result.returncode!=0 and (b'no such object:' in message or b'no such container:' in message)


def cleanup_container():
    info=command(['/usr/bin/docker','inspect',CONTAINER])
    if info.returncode:
        if container_absent(info):return
        raise ValueError('cannot establish fixture container state')
    rows=json.loads(info.stdout)
    if len(rows)!=1:raise ValueError('unexpected fixture container identity')
    row=rows[0]
    if (row['Image']!=IMAGE or row['Config'].get('Labels',{}).get('rras.fixture')!=LABEL.split('=',1)[1] or
            {mount['Source'] for mount in row['Mounts']}!={str(ROOT),str(RUNTIME)}):raise ValueError('fixture container fingerprint differs')
    stopped=command(['/usr/bin/docker','stop','--time','5',CONTAINER])
    if stopped.returncode:raise ValueError('fixture container stop failed')
    info=command(['/usr/bin/docker','inspect',CONTAINER])
    if not container_absent(info):
        raise ValueError('fixture container removal not established')


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo rehearsal required')
    launch=local('curated_publication_launch')
    for path in (STATE.parent,RUNTIME.parent,ROOT,Path(PYTHON).parent,Path(PYTHON).resolve(strict=True),
                 Path('/usr/bin/docker'),Path('/usr/bin/systemd-run'),Path('/usr/bin/setpriv'),Path('/usr/bin/setfacl'),
                 Path('/usr/sbin/useradd'),Path('/usr/sbin/userdel'),Path('/usr/sbin/groupadd'),Path('/usr/sbin/groupdel')):launch.protected(path)
    for path in (STATE,RUNTIME):
        if path.exists() or path.is_symlink():raise ValueError('preserve prior fixture state')
    if status().get('LoadState')!='not-found':raise ValueError('fixture unit exists')
    for uid in (SERVICE,CLIENT,61156):
        for lookup in (pwd.getpwuid,grp.getgrgid):
            try:lookup(uid)
            except KeyError:continue
            raise ValueError('fixture identity allocated')
    for lookup in (pwd.getpwnam,grp.getgrnam):
        try:lookup(ACCOUNT)
        except KeyError:continue
        raise ValueError('fixture identity name allocated')
    for path in Path('/proc').glob('[0-9]*/status'):
        try:lines=path.read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError):continue
        if any(line.startswith(('Uid:','Gid:')) and set(line.split()[1:])&{str(SERVICE),str(CLIENT),'61156'} for line in lines):raise ValueError('fixture identity active')
    image=command(['/usr/bin/docker','image','inspect','--format','{{.Id}}',IMAGE])
    if image.returncode or image.stdout.decode().strip()!=IMAGE:raise ValueError('pinned image unavailable')
    container=command(['/usr/bin/docker','inspect',CONTAINER])
    if not container_absent(container):raise ValueError('fixture container name not absent')
    os.umask(0o077);STATE.mkdir(mode=0o711);os.chmod(STATE,0o711)
    engine=local('curated_writer_driver');engine.STATE=STATE;engine.UID=SERVICE;engine.ACCOUNT=ACCOUNT
    counter=[0]
    def checked(argv,raw=None):
        counter[0]+=1;result=command(argv,raw,timeout=60)
        (STATE/f'child-{counter[0]:02d}-stdout').write_bytes(result.stdout);(STATE/f'child-{counter[0]:02d}-stderr').write_bytes(result.stderr)
        if result.returncode:raise ValueError('synthetic child failed')
        return json.loads(result.stdout)
    try:
        engine.create_identity()
        for name in ('private','private/history'):
            path=STATE/name;path.mkdir(mode=0o700);os.chown(path,SERVICE,SERVICE)
        (STATE/'source').mkdir(mode=0o700);(STATE/'source/private.fixture').write_bytes(b'SYNTHETIC ROOT PRIVATE SOURCE\n')
        if checked(owner_command('seed')).get('synthetic_catalog_created') is not True:raise ValueError('seed differs')
        private=STATE/'private/history/history.sqlite3';before=hashlib.sha256(private.read_bytes()).hexdigest()
        def write_policy(granted):
            path=STATE/'policy.json';path.write_text(json.dumps(policy(granted)));os.chown(path,0,SERVICE);os.chmod(path,0o640)
        write_policy(True);start()
        first=checked(container_command('read'),b'{}')
        if first.get('exact_mcp_read') is not True:raise ValueError('actual MCP read differs')
        for uid in (61156,996,1000,SERVICE,0):
            if checked(container_command('denied',uid),b'{}').get('ungranted_peer_denied') is not True:raise ValueError('ungranted peer accessed catalog')
        stop()
        if checked(owner_command('withdraw')).get('withdrawn') is not True:raise ValueError('withdrawal differs')
        context=json.dumps(first['context']).encode();start()
        if checked(container_command('withdrawn'),context).get('withdrawn_and_stale_refused') is not True:raise ValueError('withdrawn MCP read differs')
        stop();start()
        if checked(container_command('withdrawn'),context).get('withdrawn_and_stale_refused') is not True:raise ValueError('restart withdrawal differs')
        stop();write_policy(False);start()
        if checked(container_command('revoked'),b'{}').get('revoked') is not True:raise ValueError('revoked MCP client accessed data')
        stop()
        if hashlib.sha256(private.read_bytes()).hexdigest()!=before:raise ValueError('synthetic private history changed')
        os.chown(RUNTIME,0,0);os.chmod(RUNTIME,0o700)
        engine.remove_identity()
        result={'phase':'isolated_curated_reader_container_verified','root':str(STATE),'unit':UNIT,'image':IMAGE,
            'service_uid':SERVICE,'reader_uid':CLIENT,'cases':['actual_hardened_reader_unit_and_exact_reader_acl',
            'pinned_image_mcp_two_tools_successful_host_peer_read','container_drop_uid_groups_caps_and_provider_environment',
            'ungranted_unknown_worker_operator_owner_root_peers_denied','repository_private_action_routes_denied',
            'private_prose_excluded','withdrawal_and_stale_mcp_results_refused','restart_preserves_withdrawal',
            'restart_revocation_removes_reader_acl'], 'temporary_account_removed':True,'fixture_unit_stopped':True,
            'fixture_socket_removed':True,'production_services_mutated':False,'production_history_changed':False,
            'production_journal_changed':False,'hermes_configuration_changed':False,'real_credentials_used':False,
            'api_calls':0,'automatic_retry':False}
        (STATE/'complete.json').write_text(json.dumps(result));return result
    except BaseException:
        (STATE/'failure-private.txt').write_text(traceback.format_exc())
        log=command(['/usr/bin/journalctl','-u',UNIT,'--no-pager','-n','80','-o','short-iso'])
        (STATE/'unit-journal-private.txt').write_bytes(log.stdout);raise
    finally:
        try:cleanup_container()
        finally:command(['/usr/bin/systemctl','stop',UNIT])


if __name__=='__main__':
    try:print(json.dumps(run()))
    except Exception as error:
        frames=[{'file':Path(frame.filename).name,'function':frame.name,'line':frame.lineno} for frame in traceback.extract_tb(error.__traceback__)]
        print(json.dumps({'phase':'curated_container_host_stopped','exception_type':type(error).__name__,'frames':frames,
                          'protected_evidence':str(STATE),'automatic_retry':False}),file=sys.stderr)
        sys.stderr.write('Curated reader/container acceptance stopped; preserve protected evidence. No automatic retry.\n');raise SystemExit(1)
