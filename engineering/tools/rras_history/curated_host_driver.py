"""Fixed isolated curated-reader cross-UID controller; no production services."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import traceback

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def local(name):
    spec=importlib.util.spec_from_file_location('curated_driver_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


p=local('curated_host_package');STATE=p.STATE;SERVICE=p.SERVICE;CLIENT=p.CLIENT;UNKNOWN=p.UNKNOWN
engine=local('managed_host_driver')
ROLES={'seed':SERVICE,'service':SERVICE,'ready':SERVICE,'read':CLIENT,'withdraw':SERVICE,
       'after-withdraw':CLIENT,'revoked':CLIENT}


def command(role,uid=None):
    if role=='denial':
        if uid not in (CLIENT,UNKNOWN,996):raise ValueError('unknown denial identity')
    elif role not in ROLES or uid is not None and uid!=ROLES[role]:raise ValueError('unknown fixture role/identity')
    else:uid=ROLES[role]
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(uid),'--regid',str(uid),
        '--clear-groups','--pdeathsig=TERM','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
        str(engine.PYTHON),'-I','-B',str(ROOT/'engineering/tools/rras_history/curated_host_probe.py'),role]


def policy(reader=True):
    principals=[{'uid':SERVICE,'repositories':['example_library']}]
    if reader:principals.append({'uid':CLIENT,'repositories':['example_library']})
    return {'contract':'engineering-curated-read-access.v1','principals':principals}


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator acceptance required')
    for path in (STATE.parent,Path(__file__),engine.PYTHON.parent,engine.PYTHON.resolve(strict=True),
                 Path('/usr/bin/unshare'),Path('/usr/bin/setpriv'),Path('/usr/bin/setfacl')):engine.protected(path)
    if STATE.exists() or STATE.is_symlink():raise ValueError('preserve prior fixture; no retry')
    engine.STATE=STATE;engine.SERVICE=SERVICE;engine.CLIENT=CLIENT;engine.UNKNOWN=UNKNOWN;engine.command=command
    engine.unused();os.umask(0o077);engine.mkdir(STATE,mode=0o711)
    engine.mkdir(STATE/'source');engine.write(STATE/'source/private.fixture',b'SYNTHETIC ROOT PRIVATE SOURCE\n')
    engine.mkdir(STATE/'private',SERVICE,SERVICE);engine.mkdir(STATE/'private/history',SERVICE,SERVICE)
    engine.mkdir(STATE/'runtime',SERVICE,SERVICE);engine.mkdir(STATE/'client',CLIENT,CLIENT)
    engine.write(STATE/'policy.json',p.encoded(policy()),gid=SERVICE,mode=0o640)
    fixture=engine.Fixture()
    try:
        seed=fixture.child('seed')
        if seed!={'synthetic_catalog_created':True,'root_source_denied':True,'private_prose_excluded':True}:raise ValueError('seed differs')
        source=STATE/'source/private.fixture';history=STATE/'private/history/history.sqlite3'
        before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (source,history)}
        fixture.start()
        for uid in (CLIENT,UNKNOWN,996):fixture.child('denial',uid)
        if fixture.child('read')!={'exact_curated_read':True,'other_repository_denied':True,'private_and_action_routes_denied':True}:raise ValueError('read differs')
        if fixture.child('withdraw')!={'withdrawn':True}:raise ValueError('withdraw differs')
        expected={'withdrawal_retained':True,'stale_cursor_and_read_denied':True}
        if fixture.child('after-withdraw')!=expected:raise ValueError('withdrawal read differs')
        fixture.stop();fixture.start()
        if fixture.child('after-withdraw')!=expected:raise ValueError('restart withdrawal differs')
        fixture.stop()
        # Exact protected fixture-policy revision; no production grant is touched.
        raw=p.encoded(policy(False));path=STATE/'policy.json'
        fd=os.open(path,os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        fixture.start()
        if fixture.child('revoked')!={'private_files_denied':True,'reader_revoked':True}:raise ValueError('reader revocation differs')
        fixture.stop()
        if any(hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha for path,sha in before.items()):raise ValueError('private source changed')
        result={'phase':'isolated_curated_read_host_verified','root':str(STATE),'service_uid':SERVICE,'client_uid':CLIENT,
            'cases':['distinct_uid_exact_curated_search_read','other_repository_and_private_action_routes_denied',
                'reader_unknown_worker_private_files_denied','service_root_source_denied','private_prose_excluded',
                'private_network_no_groups_caps_provider_environment','withdrawal_stale_cursor_read_refused',
                'restart_preserves_withdrawal','restart_revocation_removes_reader_access'],
            'source_files_unchanged':True,'fixture_service_stopped':True,'fixture_socket_removed':True,
            'permanent_accounts_created':False,'production_services_mutated':False,'production_journal_changed':False,
            'production_history_changed':False,'real_credentials_used':False,'api_calls':0,'automatic_retry':False}
        engine.write(STATE/'complete.json',p.encoded(result));return result
    except BaseException:
        engine.write(STATE/'failure-private.txt',traceback.format_exc().encode());raise
    finally:fixture.stop()


if __name__=='__main__':
    def interrupted(*_):raise RuntimeError('fixture interrupted; preserve evidence')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:print(json.dumps(run()))
    except Exception as error:
        frames=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(error.__traceback__)]
        print(json.dumps({'phase':'curated_read_host_stopped','exception_type':type(error).__name__,'frames':frames,
                          'protected_evidence':str(STATE),'automatic_retry':False}),file=sys.stderr);raise SystemExit(1)
