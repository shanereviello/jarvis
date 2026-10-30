"""Isolated writer unit acceptance. Synthetic paths and numeric UID only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import grp
import subprocess
import sys
import traceback
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
STATE=Path('/var/lib/rras-curated-writer-acceptance-20261029')
UID=61141
UNIT='rras-curated-writer-acceptance-20261029.service'
PYTHON='/opt/rras-engineering/releases/native-10/venv/bin/python'
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def local(name):
    spec=importlib.util.spec_from_file_location('writer_driver_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def unit_command(role,timeout=False):
    if role not in ('publish','timeout'):raise ValueError('unknown fixture unit role')
    plan=local('curated_publication_launch')
    argv=plan.command('/opt/rras-engineering/releases/curated-history-'+'a'*12,'b'*64)
    changes={'User=rras-history':'User='+str(UID),'Group=rras-history':'Group='+str(UID),
        'ReadWritePaths='+plan.CATALOG:'ReadWritePaths='+str(STATE/'private/catalog'),
        'WorkingDirectory=/opt/rras-engineering/releases/curated-history-'+'a'*12:'WorkingDirectory='+str(ROOT),
        '--unit=rras-curated-publication.service':'--unit='+UNIT}
    argv=[changes.get(item,item) for item in argv]
    for index,item in enumerate(argv):
        if item.startswith('InaccessiblePaths='):
            argv[index]=item+' '+str(STATE/'private/same-uid-private')+' '+str(STATE/'root-private')
        if timeout and item=='RuntimeMaxSec=60s':argv[index]='RuntimeMaxSec=2s'
    argv=argv[:argv.index('--')+1]
    argv+=['/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
           PYTHON,'-I','-B',str(ROOT/'engineering/tools/rras_history/curated_writer_probe.py'),role]
    return argv


def command(argv,raw=None,timeout=30):
    return subprocess.run(argv,input=raw,capture_output=True,env=ENV,timeout=timeout)


def inactive():
    result=command(['/usr/bin/systemctl','show',UNIT,'--property=ActiveState,MainPID'])
    fields=dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)
    return fields.get('ActiveState') in ('inactive','failed') and fields.get('MainPID')=='0'


def settled():
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if inactive():
            state=command(['/usr/bin/systemctl','show',UNIT,'--property=LoadState']).stdout.strip()
            if state==b'LoadState=not-found':return
        time.sleep(0.1)
    raise ValueError('fixture unit did not settle; no retry')


def mkdir(path,uid=0,mode=0o700):path.mkdir(mode=mode);os.chown(path,uid,uid);os.chmod(path,mode)


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo fixture invocation required')
    launch=local('curated_publication_launch')
    for path in (STATE.parent,ROOT,Path(PYTHON).parent,Path(PYTHON).resolve(strict=True),Path('/usr/bin/systemd-run'),Path('/usr/bin/setpriv')):launch.protected(path)
    for lookup in (pwd.getpwuid,grp.getgrgid):
        try:lookup(UID)
        except KeyError:pass
        else:raise ValueError('fixture numeric identity already allocated')
    for proc in Path('/proc').iterdir():
        if proc.name.isdecimal():
            try:raw=(proc/'status').read_text()
            except (OSError,UnicodeError):continue
            if any(line.startswith(('Uid:','Gid:')) and str(UID) in line.split()[1:] for line in raw.splitlines()):raise ValueError('fixture identity already active')
    state=command(['/usr/bin/systemctl','show',UNIT,'--property=LoadState']).stdout.strip()
    if state!=b'LoadState=not-found':raise ValueError('fixture unit exists; preserve evidence')
    if STATE.exists() or STATE.is_symlink():raise ValueError('fixture exists; no retry')
    os.umask(0o077);mkdir(STATE,mode=0o711);mkdir(STATE/'private',UID);mkdir(STATE/'outside',UID)
    (STATE/'root-private').write_bytes(b'SYNTHETIC ROOT PRIVATE\n')
    probe=str(ROOT/'engineering/tools/rras_history/curated_writer_probe.py')
    try:
        seed=command(['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(UID),'--regid',str(UID),'--clear-groups',
                      '--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',PYTHON,'-I','-B',probe,'seed'])
        if seed.returncode or json.loads(seed.stdout)!={'seeded':True}:raise ValueError('fixture seed failed')
        preview={'contract':'engineering-curated-preview.v1','audience':'jarvis_candidate','visibility':'operator_private',
                 'publication_authorized':False,'authority_granted':False,'source_freshness':'not_polled','entries':[]}
        c=local('contract');packet={'contract':'engineering-curated-publication-request.v1','operation':'publish','approved':True,
            'client_key':'fixture','expected_head':None,'preview':preview,'reviewed_preview_sha256':c.digest(c.encoded(preview))}
        private=STATE/'private/same-uid-private';before=hashlib.sha256(private.read_bytes()).hexdigest()
        results=[]
        for index in range(2):
            result=command(unit_command('publish'),c.encoded(packet))
            (STATE/f'publish-{index}-stdout').write_bytes(result.stdout);(STATE/f'publish-{index}-stderr').write_bytes(result.stderr)
            if result.returncode:raise ValueError('actual writer unit failed')
            value=json.loads(result.stdout)
            if value.get('replayed')!=(index==1) or value.get('catalog_readback') is not True:raise ValueError('fixture receipt differs')
            results.append(value);settled()
        if results[0]['generation_sha256']!=results[1]['generation_sha256']:raise ValueError('replay created new generation')
        timed=command(unit_command('timeout',True),b'',timeout=20)
        (STATE/'timeout-stderr').write_bytes(timed.stderr)
        if timed.returncode==0 or not inactive():raise ValueError('runtime stop not established')
        if hashlib.sha256(private.read_bytes()).hexdigest()!=before or (STATE/'outside/write-attempt').exists():raise ValueError('private fixture changed')
        result={'phase':'isolated_curated_writer_unit_verified','root':str(STATE),'unit':UNIT,'service_uid':UID,
            'cases':['actual_numeric_uid_hardened_writer_unit','catalog_only_persistent_write','same_uid_private_mount_denial',
                     'private_history_paths_denied','private_network_no_groups_caps_provider_environment',
                     'exact_publication_and_catalog_readback','restart_exact_receipt_replay','runtime_limit_host_stop'],
            'api_calls':0,'real_credentials_used':False,'production_services_mutated':False,'production_history_changed':False,
            'production_journal_changed':False,'permanent_accounts_created':False,'fixture_unit_stopped':True,'automatic_retry':False,
            'production_launcher_invoked':False,'production_cli_identity_tested':False}
        (STATE/'complete.json').write_text(json.dumps(result));return result
    except BaseException:
        (STATE/'failure-private.txt').write_text(traceback.format_exc());raise
    finally:
        # Stop only this fixed synthetic unit; never touch the production slot.
        command(['/usr/bin/systemctl','stop',UNIT])


if __name__=='__main__':
    try:print(json.dumps(run()))
    except Exception:
        sys.stderr.write('Curated writer fixture stopped; preserve protected evidence. No automatic retry.\n');raise SystemExit(1)
