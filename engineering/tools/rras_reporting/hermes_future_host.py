"""Protected one-pass supervisor for future-session Hermes capture.

This source is not an installed unit. Provisioning must explicitly create its
root-controlled config, reader credential and private cursor directory first.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import uuid

NATIVE_RELEASE = '/opt/rras-engineering/releases/standardized-history-4b8578d5ddd1'
NATIVE_ROOT = '/srv/hermes/data'
STATE = '/var/lib/rras-hermes-future-capture'
CONFIG = '/etc/rras-engineering/codex-runtime/hermes-future-capture.json'
ENTRY_HASHES = {
    'hermes_readonly.py':'5f05ed058459ff3648392b85f9cddb7ef24f66f8a71f86f32f1a47fcfcfefd22',
    'capture_collectors.py':'b8970ee5bb08282179fcbd3b2de230cef6de70970ad9ca5657924650894a4abd',
    'capture_intake.py':'2b5c8fe9f64f2766ad154d09910d4f391ccde0b4e9b2a4d30d9e077b74337db0',
}


def local(name):
    spec=importlib.util.spec_from_file_location('future_host_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def installed_file(path, expected=None):
    path=Path(path);info=path.lstat()
    if (not path.is_absolute() or path.resolve()!=path or not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or
            info.st_nlink!=1 or info.st_mode&0o022):
        raise ValueError('root-controlled installed file required')
    for parent in (path.parent,*path.parent.parents):
        item=parent.lstat()
        if not stat.S_ISDIR(item.st_mode) or item.st_uid!=0 or item.st_mode&0o022:
            raise ValueError('root-controlled installed ancestry required')
    data=path.read_bytes()
    if expected is not None and hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError('installed file digest differs')
    return data


def inspect_container():
    result=subprocess.run(['/usr/bin/docker','inspect','hermes'],capture_output=True,timeout=15,check=True)
    rows=json.loads(result.stdout)
    if type(rows) is not list or len(rows)!=1:raise ValueError('exact Hermes container required')
    row=rows[0]
    if row['Image']!=local('hermes_future_transport').IMAGE or row['State']['Running'] is not True:
        raise ValueError('pinned running Hermes container required')
    mounts={m['Destination']:m for m in row['Mounts']}
    if (mounts.get('/opt/data',{}).get('Source')!=NATIVE_ROOT or
            mounts.get('/opt/rras-engineering-reporting',{}).get('Source')!=NATIVE_RELEASE or
            mounts.get('/opt/rras-engineering-reporting',{}).get('RW') is not False):
        raise ValueError('pinned native and read-only reporting mounts required')
    for name,digest in ENTRY_HASHES.items():
        installed_file(Path(NATIVE_RELEASE)/'engineering/tools/rras_reporting'/name,digest)


def main():
    if os.geteuid()!=0:raise ValueError('root-controlled supervisor required')
    protected=local('protected_config');config=protected.decode(CONFIG,maximum=65536)
    fields={'contract','organization_id','cutoff','reader_url','reader_token_file','authorization_reference','mappings','entry_sha256'}
    if type(config) is not dict or set(config)!=fields or config['contract']!='hermes-future-host.v1':
        raise ValueError('exact protected future capture configuration required')
    selector=local('hermes_capture_selection');selector.identifier(config['organization_id']);selector.timestamp(config['cutoff'])
    state=local('capture_intake').private(STATE,True)
    locked=state/'supervisor.lock';fd=os.open(locked,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        local('capture_intake').private(locked);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        policy_hash=hashlib.sha256(local('capture_intake').local('contract').encoded(config)).hexdigest()
        binding=state/'policy.sha256'
        local('capture_intake').private(binding)
        if binding.read_text()!=policy_hash:raise ValueError('capture policy differs from its fixed rollout binding')
        cursor_path=state/'hermes-future-cursor.json'
        if cursor_path.exists() or cursor_path.is_symlink():
            local('capture_intake').private(cursor_path)
            cursor=local('capture_intake').local('contract').decode(cursor_path.read_bytes())
        else:cursor=dict(after_time=config['cutoff'],after_id=str(uuid.UUID(int=0)))
        inspect_container()
        entry=installed_file(Path(__file__).with_name('hermes_future_native_entry.py'),config['entry_sha256'])
        token=protected.read(config['reader_token_file'],maximum=257,require_root=True).strip()
        transport=local('hermes_future_transport');reader=transport.reader(config['reader_url'],token)
        worker=transport.existing_hermes_worker(organization_id=config['organization_id'],cutoff=config['cutoff'],
            mappings=config['mappings'],authorization_reference=config['authorization_reference'],entry_source=entry)
        release=Path(__file__).resolve().parents[3]
        python=release/'venv/bin/python';flush=Path(__file__).with_name('hermes_future_flush.py')
        installed_file(flush)
        def deliver():
            result=subprocess.run(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--clear-groups',
                '--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
                str(python),'-I',str(flush)],capture_output=True,timeout=120,check=True)
            if len(result.stdout)>65536:raise ValueError('bounded history delivery result required')
            return local('capture_intake').local('contract').decode(result.stdout,max_bytes=65536)
        coordinator=local('hermes_future_coordinator')
        result=coordinator.run_once(organization_id=config['organization_id'],cutoff=config['cutoff'],
            cursor=cursor,query=reader,worker=worker,flush=deliver)
        coordinator.save_cursor(state,result['cursor'])
        print(json.dumps(result,allow_nan=False))
    finally:os.close(fd)


if __name__=='__main__':
    try:main()
    except Exception:
        raise SystemExit('Future Hermes capture pass refused; retained source, cursor and queued evidence remain available.')
