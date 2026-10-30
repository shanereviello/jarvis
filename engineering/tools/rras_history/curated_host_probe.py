"""Synthetic curated-reader fixture roles; fixed paths, no production resources."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def local(name):
    spec=importlib.util.spec_from_file_location('curated_probe_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


p=local('curated_host_package');STATE=p.STATE;SERVICE=p.SERVICE;CLIENT=p.CLIENT;UNKNOWN=p.UNKNOWN
CATALOG=STATE/'private/catalog'
SOCKET=STATE/'runtime/service.sock'


def call(message):return local('curated_read_unix').call(SOCKET,SERVICE,message)
def query(repo='example_library',generation=None):
    return {'method':'search','repository_id':repo,'query':'','generation_sha256':generation,'offset':0,'limit':20}


def denied(path):
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except PermissionError:return
    else:os.close(fd);raise ValueError('private fixture path unexpectedly readable')


def seed():
    denied(STATE/'source/private.fixture')
    c=local('contract');store=local('store').Store(STATE/'private/history',create=True)
    for repo,number in (('example_library','1'),('other_repo','2')):
        request={'contract':'engineering-history.v1','operation':'work.create','client_event_key':'fixture-'+repo,
            'expected_head':None,'source':{'kind':'agent_reported','namespace':'isolated-curated-fixture','id':None},
            'occurred_at':None,'body':{'work_item_id':'wrk_'+number*32,'repository_id':repo,'revision':1,
                'title':'SYNTHETIC PRIVATE TITLE','objective':'SYNTHETIC PRIVATE OBJECTIVE','rationale':'SYNTHETIC PRIVATE RATIONALE',
                'acceptance_criteria':[{'id':'AC1','description':'Fixture only'}],'allowed_paths':['docs/example.md'],'baseline':None}}
        store.submit(request,peer_uid=SERVICE)
    rows=store.history()['records']
    selections=[{'source_request_sha256':c.digest(c.encoded(row['submission'])),'summary':'Curated '+row['submission']['body']['repository_id'],
        'rationale':'Explicit synthetic selection','limitations':'No human authentication, execution or deployment evidence'} for row in rows]
    preview=local('curated_preview').build(rows,selections)
    if b'SYNTHETIC PRIVATE' in c.encoded(preview):raise ValueError('private prose copied')
    catalog=local('curated_publication');catalog.initialize(CATALOG,['example_library','other_repo'])
    catalog.publish(CATALOG,preview,c.digest(c.encoded(preview)),None,'seed',approve_publication=True)
    return {'synthetic_catalog_created':True,'root_source_denied':True,'private_prose_excluded':True}


def serve():
    transport=local('unix');policy=transport.load_policy(STATE/'policy.json')
    access=local('curated_read_access').Access(CATALOG,policy);prod=local('production_entry')
    def bound(path):
        readers=[uid for uid,repos in access.grants.items() if repos and uid!=SERVICE]
        prod.set_acl(path.parent,readers,directory=True);prod.set_acl(path,readers,directory=False)
    stopped=[False]
    def stop(*_):stopped[0]=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    with local('curated_read_unix').Server(SOCKET,CATALOG,policy,on_bound=bound) as server:
        while not stopped[0]:server.serve_once()
    return {'stopped':True}


def read():
    result=call(query());entries=result['entries']
    if len(entries)!=1 or entries[0]['summary']!='Curated example_library':raise ValueError('repository filter differs')
    entry=entries[0];generation=result['generation_sha256']
    answer=call({'method':'read','repository_id':'example_library','entry_id':entry['entry_id'],'generation_sha256':generation})
    if answer['entry']!=entry or answer['authority_granted'] is not False or answer['human_authenticated'] is not False:raise ValueError('exact readback differs')
    if b'SYNTHETIC PRIVATE' in local('contract').encoded(result):raise ValueError('private text disclosed')
    try:call(query('other_repo'))
    except ValueError:pass
    else:raise ValueError('cross repository search succeeded')
    for method in ('history','document','submit','publish','withdraw','approve','launch','merge','deploy'):
        try:call({'method':method,'repository_id':'example_library'})
        except ValueError:pass
        else:raise ValueError('forbidden curated route succeeded')
    local('link_delivery').write(STATE/'client/context.json',{'entry_id':entry['entry_id'],'generation_sha256':generation})
    return {'exact_curated_read':True,'other_repository_denied':True,'private_and_action_routes_denied':True}


def withdraw():
    catalog=local('curated_publication');head=catalog.head(CATALOG)
    page=catalog.search(CATALOG,'example_library','')
    catalog.withdraw(CATALOG,[entry['entry_id'] for entry in page['entries']],head,'withdraw',approve_withdrawal=True)
    return {'withdrawn':True}


def after_withdraw():
    old=local('link_delivery').read(STATE/'client/context.json')
    if call(query())['entries']:raise ValueError('withdrawn content visible')
    for request in (query(generation=old['generation_sha256']),{'method':'read','repository_id':'example_library',**old}):
        try:call(request)
        except ValueError:pass
        else:raise ValueError('old generation still readable')
    return {'withdrawal_retained':True,'stale_cursor_and_read_denied':True}


def main(role):
    boundary=local('managed_host_probe').boundary();uid=os.getuid()
    if role in ('seed','service','ready','withdraw') and uid!=SERVICE:raise ValueError('fixture service role differs')
    if role in ('read','after-withdraw','revoked') and uid!=CLIENT:raise ValueError('fixture reader role differs')
    if role=='seed':result=seed()
    elif role=='service':result=serve()
    elif role=='ready':call(query());result={'ready':True}
    elif role=='read':result=read()
    elif role=='withdraw':result=withdraw()
    elif role=='after-withdraw':result=after_withdraw()
    elif role in ('denial','revoked'):
        if uid not in (CLIENT,UNKNOWN,996):raise ValueError('unknown denial role')
        for path in (STATE/'source/private.fixture',STATE/'private/history/history.sqlite3',CATALOG/'current.json',STATE/'policy.json'):denied(path)
        if uid!=CLIENT or role=='revoked':
            try:call(query())
            except (ValueError,OSError):pass
            else:raise ValueError('denied reader connected')
        result={'private_files_denied':True,'reader_revoked':role=='revoked'}
    else:raise ValueError('unknown probe role')
    return {'boundary':boundary,'result':result}


if __name__=='__main__':print(json.dumps(main(sys.argv[1])))
