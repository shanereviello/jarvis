"""Synthetic managed-link fixture roles; fixed scope and sanitized environment."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def local(name,native=False):
    path=ROOT/'engineering/tools'/('rras_native' if native else 'rras_history')/(name+'.py')
    spec=importlib.util.spec_from_file_location('managed_probe_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


spec=local('managed_host_package');STATE=spec.STATE;SERVICE=spec.SERVICE;CLIENT=spec.CLIENT;UNKNOWN=spec.UNKNOWN


def boundary():
    fields=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if os.getuid()!=os.geteuid() or os.getgroups() or fields['NoNewPrivs'].strip()!='1':raise ValueError('probe identity boundary differs')
    if any(int(fields[name].strip(),16) for name in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')):raise ValueError('probe capabilities differ')
    if [name for _,name in socket.if_nameindex()]!=['lo']:raise ValueError('probe network differs')
    if any(key in os.environ for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','GH_TOKEN','GITHUB_TOKEN')):raise ValueError('provider environment refused')
    return {'uid':os.getuid(),'gid':os.getgid(),'no_capabilities':True,'private_network':True,'supplementary_groups':[]}


def write(path,value):
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(),0o600);stream.write(spec.encoded(value));stream.flush();os.fsync(stream.fileno())


def seed():
    if os.getuid()!=0:raise ValueError('root synthetic fixture owner required')
    journal=local('workflow_journal',True).Journal(STATE/'source',create=True)
    rows=json.loads((ROOT/'engineering/contracts/examples/library-managed.json').read_text());journal.append(rows)
    event=copy.deepcopy(rows[-1]);raw=b'SYNTHETIC-PRIVATE-ARTIFACT-DO-NOT-EXPORT';sha=hashlib.sha256(raw).hexdigest()
    event.update(event_id='evt_'+'e'*32,sequence=2,previous_event_sha256=local('workflow_records',True).record_digest(rows[-1]),
                 event_type='validation.finished',outcome='succeeded',summary='SYNTHETIC-PRIVATE-SUMMARY-DO-NOT-EXPORT')
    event['provenance']=copy.deepcopy(event['provenance']);event['provenance']['kind']='observed'
    event['artifacts']=[{'artifact_id':'art_'+'e'*32,'sha256':sha,'media_type':'text/plain','visibility':'operator_only','purpose':'validation'}]
    journal.append([event],{sha:raw})
    work=rows[1];write(STATE/'source/work-sha.json',{'sha256':local('workflow_records',True).record_digest(work)})
    return {'records':5,'work_sha256':local('workflow_records',True).record_digest(work),'private_artifact':True}


def exported():
    if os.getuid()!=0:raise ValueError('root synthetic fixture reader required')
    sha=json.loads((STATE/'source/work-sha.json').read_bytes())['sha256'];exporter=local('engineering_export',True)
    first=exporter.export(STATE/'source','synthetic-managed-host',sha,limit=1)
    second=exporter.export(STATE/'source','synthetic-managed-host',sha,after=first['next_after'])
    for name,packet in (('first',first),('second',second)):
        raw=spec.encoded(packet)
        if b'SYNTHETIC-PRIVATE-' in raw:raise ValueError('private source content exported')
        write(STATE/'export'/(name+'.json'),packet)
    w=first['work']
    work={'contract':'engineering-history.v1','operation':'work.create','client_event_key':'synthetic-managed-host-work','expected_head':None,
          'source':{'kind':'imported','namespace':'synthetic_managed_host','id':None},'occurred_at':None,
          'body':{'work_item_id':w['work_item_id'],'repository_id':w['repository_id'],'revision':1,'title':'Synthetic managed link acceptance',
                  'objective':'Verify only the isolated fixture','rationale':'Prove protected export and distinct-UID receipt delivery',
                  'acceptance_criteria':[{'id':'AC1','description':'No authority promotion or duplicate events'}],
                  'allowed_paths':w['requested_paths'],'baseline':w['baseline']}}
    write(STATE/'export/work.json',work)
    return {'pages':2,'source_mutations':False,'first_after':first['next_after'],'second_after':second['next_after']}


def call(message):return local('unix').call(STATE/'runtime/service.sock',SERVICE,message)


def client(role):
    if os.getuid()!=CLIENT:raise ValueError('dedicated importer UID required')
    delivery=local('link_delivery');inputs=STATE/'client/input'
    work=delivery.read(inputs/'work.json');first=delivery.read(inputs/'first.json');second=delivery.read(inputs/'second.json')
    one=STATE/'client/page-one';two=STATE/'client/page-two'
    if role=='lost-response':
        call({'method':'submit','request':work});delivery.prepare(one,work,first)
        def lost(request):
            call({'method':'submit','request':request});raise OSError('synthetic post-commit response loss')
        try:delivery.deliver(one,lost,writer_uid=SERVICE,peer_uid=CLIENT)
        except OSError:pass
        else:raise ValueError('synthetic lost response was not exercised')
        if (one/'complete.json').exists():raise ValueError('incomplete import advanced cursor')
        return {'pending_retained':True,'cursor_advanced':False}
    submit=lambda request:call({'method':'submit','request':request})
    if role=='resume':
        completed=delivery.deliver(one,submit,writer_uid=SERVICE,peer_uid=CLIENT)
        delivery.prepare(two,work,second,previous=one)
        completed=delivery.deliver(two,submit,writer_uid=SERVICE,peer_uid=CLIENT)
        return {'next_after':completed['next_after'],'receipts':2,'authority_granted':False}
    if role=='replay':
        delivery.deliver(two,lambda _:(_ for _ in ()).throw(ValueError('saved receipt unexpectedly redelivered')),writer_uid=SERVICE,peer_uid=CLIENT)
        plan=delivery.read(two/'plan.json')['plan'];answer=submit(plan['requests'][0])
        if answer['inserted']:raise ValueError('replay inserted duplicate')
        history=call({'method':'history','repository_id':'example_library','offset':0,'limit':100})
        if len(history['records'])!=3:raise ValueError('fixture history count differs')
        for row in history['records'][1:]:
            receipt=row['receipt']
            if receipt['provenance']!='imported' or receipt['authority_granted'] is not False or receipt['writer_uid']!=SERVICE or receipt['peer_uid']!=CLIENT:
                raise ValueError('imported receipt association differs')
        return {'history_records':3,'same_receipt_replay':True,'source_observation_not_promoted':True}
    raise ValueError('unknown importer role')


def denied(path):
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except PermissionError:return
    else:os.close(fd);raise ValueError('private fixture path unexpectedly readable')


def main(role):
    limits=boundary();uid=os.getuid()
    if role=='seed':result=seed()
    elif role=='export':result=exported()
    elif role=='init':
        if uid!=SERVICE:raise ValueError('service owner required')
        local('store').Store(STATE/'history',create=True);result={'empty_history_created':True}
    elif role=='service':
        if uid!=SERVICE:raise ValueError('service owner required')
        stopped=[False]
        def stop(*_):stopped[0]=True
        signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
        local('production_entry').serve(STATE/'history',STATE/'runtime/service.sock',STATE/'policy.json',lambda:stopped[0])
        result={'stopped':True}
    elif role=='ready':
        if uid!=CLIENT:raise ValueError('importer readiness identity required')
        deadline=time.monotonic()+5
        while True:
            try:
                call({'method':'history','repository_id':'example_library','offset':0,'limit':1});break
            except (ValueError,OSError):
                if time.monotonic()>deadline:raise
                time.sleep(0.05)
        result={'ready':True}
    elif role in ('lost-response','resume','replay'):result=client(role)
    elif role=='denial':
        if uid not in (CLIENT,UNKNOWN,996):raise ValueError('unknown denial principal')
        for path in (STATE/'source/workflow.sqlite3',STATE/'history/history.sqlite3',STATE/'policy.json'):denied(path)
        if uid!=CLIENT:
            denied(STATE/'client/input/first.json')
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                connection.settimeout(3)
                try:connection.connect(str(STATE/'runtime/service.sock'))
                except PermissionError:pass
                else:raise ValueError('unknown/worker socket access unexpectedly allowed')
        result={'private_paths_denied':True,'socket_denied':uid!=CLIENT}
    else:raise ValueError('unknown probe role')
    return {'boundary':limits,'result':result}


if __name__=='__main__':
    try:print(json.dumps(main(sys.argv[1])))
    except Exception:
        import traceback
        traceback.print_exc();raise SystemExit(1)
