"""Root stdlib controller for fixed isolated historical-review handoff acceptance."""
import grp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import signal
import sys
import traceback

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def local(name):
    s=importlib.util.spec_from_file_location('review_driver_'+name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


p=local('review_handoff_package');STATE=p.STATE;SERVICE=p.SERVICE;UNKNOWN=p.UNKNOWN;CLIENT=1000
engine=local('managed_host_driver')
ROLES={'seed':0,'export':0,'init':SERVICE,'service':SERVICE,'ready':CLIENT,'lost-response':CLIENT,'resume':CLIENT,'replay':CLIENT}


def command(role,uid=None):
    if role=='denial':
        if uid not in (CLIENT,UNKNOWN,996):raise ValueError('unknown denial identity')
    elif role not in ROLES or uid is not None and uid!=ROLES[role]:raise ValueError('unknown fixture role/identity')
    else:uid=ROLES[role]
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(uid),'--regid',str(uid),
        '--clear-groups','--pdeathsig=TERM','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
        str(engine.PYTHON),'-I','-B',str(ROOT/'engineering/tools/rras_history/review_handoff_probe.py'),role]


def unused():
    ids={SERVICE,UNKNOWN}
    if any(user.pw_uid in ids for user in pwd.getpwall()) or any(group.gr_gid in ids for group in grp.getgrall()):
        raise ValueError('reserved numeric fixture identity allocated')
    for path in Path('/proc').glob('[0-9]*/status'):
        try:lines=path.read_text().splitlines()
        except (FileNotFoundError,ProcessLookupError):continue
        for line in lines:
            if line.startswith(('Uid:','Gid:','Groups:')) and ids&set(map(int,line.split()[1:])):
                raise ValueError('reserved numeric fixture identity active')


def source_hashes():
    return {str(path.relative_to(STATE/'source')):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (STATE/'source').rglob('*') if path.is_file()}


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit root fixture invocation required')
    for path in (STATE.parent,Path(__file__),engine.PYTHON.resolve(strict=True),Path('/usr/bin/setpriv'),Path('/usr/bin/unshare')):engine.protected(path)
    if STATE.exists() or STATE.is_symlink():raise ValueError('preserve prior fixture; no automatic retry')
    unused();os.umask(0o077);engine.mkdir(STATE,mode=0o711)
    for name in ('source','export'):engine.mkdir(STATE/name)
    engine.mkdir(STATE/'client',CLIENT,CLIENT);engine.mkdir(STATE/'history',SERVICE,SERVICE);engine.mkdir(STATE/'runtime',SERVICE,SERVICE)
    policy={'contract':'engineering-history-access.v1','principals':[{'uid':CLIENT,'private_read':['example_library'],'write':['example_library']}]}
    engine.write(STATE/'policy.json',p.encoded(policy),gid=SERVICE,mode=0o640)
    # Reuse only the existing bounded process/stop machinery, with this fixture's
    # fixed scope and role map. No production paths or service manager are used.
    engine.STATE=STATE;engine.SERVICE=SERVICE;engine.CLIENT=CLIENT;engine.UNKNOWN=UNKNOWN;engine.command=command
    fixture=engine.Fixture()
    try:
        if fixture.child('seed')!={'protected_document_created':True,'live_execution_revoked':True,'approvals_created':0}:raise ValueError('seed differs')
        before=source_hashes()
        if fixture.child('export')!={'historical_packet_verified':True,'authority_granted':False}:raise ValueError('export differs')
        packet=local('contract').decode((STATE/'export/packet.json').read_bytes(),max_bytes=512*1024)
        local('review_document_export').handoff('8'*32,packet,approve_private_export=True,
            journal_parent=STATE/'journals',handoff_parent=STATE/'handoffs')
        handed=STATE/'handoffs'/('document-'+'8'*32)/'packet.json'
        if handed.read_bytes()!=(STATE/'export/packet.json').read_bytes():raise ValueError('handoff byte mismatch')
        fixture.child('init');fixture.start()
        for uid in (CLIENT,UNKNOWN,996):fixture.child('denial',uid)
        if fixture.child('lost-response')!={'pending_preserved':True}:raise ValueError('lost response differs')
        fixture.stop();fixture.start()
        if fixture.child('resume')!={'exact_readback':True,'authority_granted':False}:raise ValueError('resume differs')
        fixture.stop();fixture.start()
        if fixture.child('replay')!={'history_records':2,'same_receipt_replay':True,'authority_granted':False}:raise ValueError('replay differs')
        fixture.stop()
        if source_hashes()!=before:raise ValueError('historical source files changed')
        result={'phase':'isolated_review_document_handoff_verified','root':str(STATE),'service_uid':SERVICE,'client_uid':CLIENT,
            'cases':['protected_capture_and_immutable_document_without_approval','live_execution_revocation_retained',
                     'historical_source_version_and_document_verified','exact_private_root_to_operator_handoff',
                     'source_history_policy_unknown_and_worker_denials','private_network_no_groups_no_caps_no_provider_env',
                     'lost_response_keeps_document_pending','service_restart_exact_document_readback',
                     'second_restart_original_receipt_and_no_duplicate_document','private_imported_document_grants_no_authority'],
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
        print(json.dumps({'phase':'review_handoff_host_stopped','exception_type':type(error).__name__,'frames':frames,
                          'protected_evidence':str(STATE),'automatic_retry':False}),file=sys.stderr);raise SystemExit(1)
