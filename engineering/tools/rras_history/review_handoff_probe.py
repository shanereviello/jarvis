"""Fixed isolated review-document export/intake roles; no real task execution."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def local(name,native=False):
    path=ROOT/'engineering/tools'/('rras_native' if native else 'rras_history')/(name+'.py')
    s=importlib.util.spec_from_file_location('review_probe_'+name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


p=local('review_handoff_package');STATE=p.STATE;SERVICE=p.SERVICE;CLIENT=1000;UNKNOWN=p.UNKNOWN


def write(path,value):
    with path.open('xb') as f:
        os.fchmod(f.fileno(),0o600);f.write(local('contract').encoded(value));f.flush();os.fsync(f.fileno())


def seed():
    if os.getuid()!=0:raise ValueError('root fixture seed required')
    a=local('activity',True);op=local('operator_control',True);doc=local('document_approval',True)
    source=STATE/'source';control=source/'control';control.mkdir(mode=0o700);repo=source/'repo';repo.mkdir(mode=0o700)
    def git(*args):return subprocess.check_output(['/usr/bin/git','--no-replace-objects','-c','core.hooksPath=/dev/null','-C',str(repo),*args],
        stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8',
        'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'}).decode().strip()
    git('init','-q','-b','main');(repo/'value.py').write_text('value=0\n');git('add','.')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','fixture')
    registration,work=local('probe_workflow_host',True).fixture_records(ROOT/'engineering/tools/rras_native',repo,git('rev-parse','HEAD'),'example_library')
    for name,value in (('registration.json',registration),('work.json',work)):a.absent(source/name,a.encoded(value))
    config=source/'operator.json'
    a.absent(config,a.encoded({'schema_version':1,'registration':registration,'hermes_project':'offline-review',
        'profile':str(ROOT/'engineering/tools/rras_native/profile.json'),'codex_config':str(ROOT/'engineering/tools/rras_native/codex-config.toml')}))
    prepared=local('repository_admission',True).prepare(source/'registration.json',source/'work.json','offline-review',source/'proposals')
    captured=op.capture(config,source/'proposals',prepared['candidate_id'],control,'codex/offline-review')
    engineering={'contract':'engineering-history.v1','operation':'work.create','client_event_key':'offline-review-work',
        'expected_head':None,'source':{'kind':'agent_reported','namespace':'offline-fixture','id':None},'occurred_at':None,
        'body':{'work_item_id':work['work_item_id'],'repository_id':work['repository_id'],'revision':1,'title':'Synthetic review handoff',
            'objective':work['objective'],'rationale':'Verify private historical document handoff without paid work',
            'acceptance_criteria':[{'id':'AC1','description':'Exact immutable document survives handoff/restart/replay'}],
            'allowed_paths':work['requested_paths'],'baseline':work['baseline']}}
    narrative={key:'unknown; isolated fixture only' for key in doc.local('managed_review','rras_history').NARRATIVE}
    doc.prepare(control,captured['review_id'],config,engineering,narrative,'doc_'+'7'*32)
    write(source/'identity.json',{'review_id':captured['review_id']})
    # Revoke live admission AFTER capture. Historical export must remain passive,
    # while the unchanged execution validator must refuse this old capture.
    config.write_bytes(config.read_bytes()+b' ')
    try:doc.load(control,captured['review_id'])
    except ValueError:pass
    else:raise ValueError('execution loader did not reject changed live configuration')
    if list(control.glob('*.approval.json')):raise ValueError('fixture created execution authorization')
    return {'protected_document_created':True,'live_execution_revoked':True,'approvals_created':0}


def exported():
    identity=json.loads((STATE/'source/identity.json').read_bytes())
    sha=hashlib.sha256((ROOT/'release-manifest.json').read_bytes()).hexdigest()
    packet=local('review_document_export').snapshot(STATE/'source/control',identity['review_id'],ROOT,sha,approve_private_export=True)
    write(STATE/'export/packet.json',packet)
    return {'historical_packet_verified':True,'authority_granted':False}


def call(message):return local('unix').call(STATE/'runtime/service.sock',SERVICE,message)


def client(role):
    if os.getuid()!=CLIENT:raise ValueError('operator receiver identity required')
    d=local('link_delivery');link=local('review_document_link')
    handoff=STATE/'handoffs'/('document-'+'8'*32);packet=d.read(handoff/'packet.json');manifest=d.read(handoff/'handoff.json')
    review=link.inspect(packet)
    if review['packet_sha256']!=manifest['packet_sha256']:raise ValueError('private handoff digest differs')
    receiver=STATE/'client/receiver'
    if role=='lost-response':
        call({'method':'submit','request':packet['work_request']})  # Explicit fixture work intake, outside receiver.
        link.prepare(receiver,packet,review['packet_sha256'])
        def lost(message):
            result=call(message)
            if message['method']=='submit':raise OSError('synthetic lost post-commit response')
            return result
        try:link.deliver(receiver,lost,writer_uid=SERVICE,peer_uid=CLIENT)
        except OSError:pass
        else:raise ValueError('lost-response case not exercised')
        if (receiver/'complete.json').exists():raise ValueError('lost response falsely completed')
        return {'pending_preserved':True}
    if role=='resume':
        result=link.deliver(receiver,call,writer_uid=SERVICE,peer_uid=CLIENT)
        return {'exact_readback':result['markdown_sha256']==packet['binding']['markdown_sha256'],'authority_granted':False}
    if role=='replay':
        def no_submit(message):
            if message['method']=='submit':raise ValueError('saved receipt unexpectedly submitted again')
            return call(message)
        link.deliver(receiver,no_submit,writer_uid=SERVICE,peer_uid=CLIENT)
        duplicate=call({'method':'submit','request':packet['document_request']})
        if duplicate['inserted'] or duplicate['receipt']!=d.read(receiver/'receipt.json'):raise ValueError('document replay receipt differs')
        rows=call({'method':'history','repository_id':'example_library','offset':0,'limit':100})['records']
        if len(rows)!=2 or rows[-1]['receipt']['provenance']!='imported' or rows[-1]['receipt']['authority_granted'] is not False:
            raise ValueError('passive document intake association differs')
        return {'history_records':2,'same_receipt_replay':True,'authority_granted':False}
    raise ValueError('unknown client role')


def main(role):
    boundary=local('managed_host_probe').boundary();uid=os.getuid()
    if role=='seed':result=seed()
    elif role=='export':result=exported()
    elif role in ('lost-response','resume','replay'):result=client(role)
    elif role=='denial':
        if uid not in (CLIENT,UNKNOWN,996):raise ValueError('unknown denial identity')
        deny=local('managed_host_probe').denied
        identity=STATE/'source/identity.json'
        for path in (identity,STATE/'history/history.sqlite3',STATE/'policy.json'):deny(path)
        if uid!=CLIENT:
            deny(STATE/'handoffs'/('document-'+'8'*32)/'packet.json')
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                try:sock.connect(str(STATE/'runtime/service.sock'))
                except PermissionError:pass
                else:raise ValueError('unknown/worker socket access allowed')
        result={'private_paths_denied':True,'socket_denied':uid!=CLIENT}
    elif role=='init':
        if uid!=SERVICE:raise ValueError('service identity required')
        local('managed_host_probe').denied(STATE/'source/identity.json')
        local('store').Store(STATE/'history',create=True);result={'empty_history_created':True}
    elif role=='service':
        if uid!=SERVICE:raise ValueError('service identity required')
        stop=[False]
        def stopping(*_):stop[0]=True
        signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
        local('production_entry').serve(STATE/'history',STATE/'runtime/service.sock',STATE/'policy.json',lambda:stop[0])
        result={'stopped':True}
    elif role=='ready':
        deadline=time.monotonic()+5
        while True:
            try:call({'method':'history','repository_id':'example_library','offset':0,'limit':1});break
            except (ValueError,OSError):
                if time.monotonic()>deadline:raise
                time.sleep(0.05)
        result={'ready':True}
    else:raise ValueError('unknown fixture role')
    return {'boundary':boundary,'result':result}


if __name__=='__main__':
    try:print(json.dumps(main(sys.argv[1])))
    except Exception:
        import traceback
        traceback.print_exc();raise SystemExit(1)
