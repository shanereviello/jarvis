"""Repeatable operator-driven passive sync from reviewed private handoffs.

No root source access, work creation, narration, scheduler or execution authority.
"""
from contextlib import contextmanager
import fcntl
import os
import re
from pathlib import Path
import stat


def local(name):
    import importlib.util
    spec=importlib.util.spec_from_file_location('managed_sync_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def history(call,repo):
    rows=[];offset=0
    for _ in range(101):
        page=call({'method':'history','repository_id':repo,'offset':offset,'limit':100});rows.extend(page['records'])
        if not page['has_more']:return rows
        if page['next_offset']<=offset:raise ValueError('history cursor differs')
        offset=page['next_offset']
    raise ValueError('history exceeds bound')


def target(call,work):
    c=local('contract');body=work['body'];rows=history(call,body['repository_id'])
    revisions=[row['submission']['body'] for row in rows if row['submission']['operation'].startswith('work.') and
               row['submission']['body']['work_item_id']==body['work_item_id']]
    if not revisions or c.digest(c.encoded(max(revisions,key=lambda r:r['revision'])))!=c.digest(c.encoded(body)):
        raise ValueError('existing exact engineering work head required; never create or revise implicitly')
    return rows


def initialize(root,work,packet,socket,service_uid,call):
    d=local('link_delivery');c=local('contract');t=local('unix');work=c.validate(work)
    binding=local('managed_link').plan(work,packet)['binding'];t.uid(service_uid);endpoint=t.endpoint(socket)
    target(call,work)
    root=Path(root)
    if not root.is_absolute() or root.parent.resolve(strict=True)!=root.parent:raise ValueError('canonical sync state required')
    if os.getuid()==0 or os.geteuid()!=os.getuid():raise ValueError('unprivileged sync caller required')
    root.mkdir(mode=0o700);d.guard(root)
    d.write(root/'configuration.json',{'contract':'engineering-managed-sync.v1','writer_uid':os.getuid(),
            'service_uid':service_uid,'service_socket':str(endpoint),'work_request':work,'binding':binding})
    (root/'captures').mkdir(mode=0o700)
    return {'initialized':True,'work_item_id':work['body']['work_item_id'],'history_records_written':False}


def configuration(root):
    d=local('link_delivery');root=d.guard(root);value=d.read(root/'configuration.json')
    if (set(value)!={'contract','writer_uid','service_uid','service_socket','work_request','binding'} or
            value['contract']!='engineering-managed-sync.v1' or type(value['writer_uid']) is not int or value['writer_uid']!=os.getuid()):
        raise ValueError('fixed sync configuration differs')
    local('contract').validate(value['work_request']);local('unix').uid(value['service_uid']);local('unix').endpoint(value['service_socket'])
    d.guard(root/'captures');return value


@contextmanager
def locked(root):
    fd=os.open(root/'sync.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('private sync lock required')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('another sync is active') from None
        yield
    finally:os.close(fd)


def capture(config,handoff):
    d=local('link_delivery');handoff=d.guard(handoff);meta=d.read(handoff/'export-result.json')
    members=meta.get('packets') if type(meta) is dict else None
    if type(members) is not list or not 1<=len(members)<=101:raise ValueError('bounded export packet list required')
    packets=[]
    for index,member in enumerate(members):
        if type(member) is not dict or member.get('file')!=f'packet-{index:03d}.json':raise ValueError('fixed export packet name required')
        packets.append(d.read(handoff/member['file']))
    return captured(config,meta,packets)


def captured(config,meta,values):
    c=local('contract');link=local('managed_link')
    if (set(meta)!={'contract','work','journal_id','packets','next_after','source_open_mode','source_rows_written','history_records_written','api_calls'} or
            meta['contract']!='engineering-production-export-result.v1' or meta['source_open_mode']!='ro' or
            meta['source_rows_written'] is not False or meta['history_records_written'] is not False or type(meta['api_calls']) is not int or meta['api_calls']!=0 or
            type(meta['packets']) is not list or not 1<=len(meta['packets'])<=101):raise ValueError('bounded passive export manifest required')
    if len(values)!=len(meta['packets']):raise ValueError('capture packet count differs')
    packets=[];plans=[];after=0;seen=set();size=len(c.encoded(meta))
    for index,member in enumerate(meta['packets']):
        name=f'packet-{index:03d}.json'
        if type(member) is not dict or set(member)!={'file','sha256','events'} or member['file']!=name:
            raise ValueError('fixed export packet name required')
        packet=link.validate(values[index]);raw=c.encoded(packet);size+=len(raw)
        if size>1536*1024 or c.digest(raw)!=member['sha256'] or type(member['events']) is not int or member['events']!=len(packet['facts']):
            raise ValueError('bounded export packet digest/count differs')
        if (packet['work']!=meta['work'] or packet['journal_id']!=meta['journal_id'] or packet['after']!=after or
                (index<len(meta['packets'])-1)!=packet['has_more']):raise ValueError('complete frozen export pages required')
        ids={fact['event_id'] for fact in packet['facts']}
        if ids&seen:raise ValueError('source event repeated across pages')
        seen.update(ids)
        plan=link.plan(config['work_request'],packet)
        if plan['binding']!=config['binding']:raise ValueError('fixed operational/engineering revision binding differs')
        after=packet['next_after'];packets.append(packet);plans.append(plan)
    if type(meta['next_after']) is not int or meta['next_after']!=after:raise ValueError('final source cursor differs')
    digest=c.digest(c.encoded({'manifest':meta,'packets':packets}))
    return {'manifest':meta,'packets':packets,'plans':plans,'sha256':digest}


def completed(root,config):
    d=local('link_delivery');c=local('contract');link=local('managed_link');known={};high=0;count=0
    directories=list((root/'captures').iterdir())
    if len(directories)>128:raise ValueError('sync capture bound exceeded')
    for directory in sorted(directories):
        if not re.fullmatch('capture-[0-9a-f]{64}',directory.name):raise ValueError('unexpected sync capture directory')
        d.guard(directory)
        if not (directory/'complete.json').exists():continue
        done=d.read(directory/'complete.json')
        saved=d.read(directory/'input.json')
        if set(saved)!={'manifest','packets'}:raise ValueError('saved capture differs')
        frozen=captured(config,saved['manifest'],saved['packets'])
        expected=completion(frozen,config)
        if done!=expected:raise ValueError('completed capture summary differs')
        if (done.get('binding')!=config['binding'] or done.get('capture_sha256')!=directory.name.removeprefix('capture-') or
                type(done.get('pages')) is not int or not 1<=done['pages']<=101 or
                type(done.get('next_after')) is not int or done['next_after']<0):raise ValueError('completed sync binding differs')
        for index in range(done['pages']):
            page=directory/f'page-{index:03d}';bundle=d.read(page/'plan.json');plan=link.plan(config['work_request'],bundle['packet'])
            if (bundle['work_request']!=config['work_request'] or bundle['packet']!=frozen['packets'][index] or
                    bundle['plan']!=plan or d.read(page/'complete.json')!=d.completion(plan)):raise ValueError('completed page differs')
            for number,request in enumerate(plan['requests']):
                d.check_receipt(d.read(page/f'receipt-{number:03d}.json'),request,config['service_uid'],config['writer_uid'])
                key=request['client_event_key'];sha=c.digest(c.encoded(request))
                if key in known and known[key]!=sha:raise ValueError('completed source claim changed')
                known[key]=sha
        high=max(high,done['next_after']);count+=1
    return known,high,count


def inspect(root,handoff):
    root=Path(root);config=configuration(root);bundle=capture(config,handoff)
    return {'capture_sha256':bundle['sha256'],'work_item_id':config['binding']['work_item_id'],
            'source_events':sum(len(plan['requests']) for plan in bundle['plans']),'pages':len(bundle['plans']),
            'next_after':bundle['manifest']['next_after'],'history_records_written':False,'authority_granted':False}


def apply(root,handoff,expected_capture_sha256,call):
    root=Path(root);config=configuration(root)
    return run_capture(root,config,capture(config,handoff),expected_capture_sha256,call)


def resume(root,expected_capture_sha256,call):
    if not isinstance(expected_capture_sha256,str) or not re.fullmatch('[0-9a-f]{64}',expected_capture_sha256):raise ValueError('exact capture digest required')
    root=Path(root);config=configuration(root);d=local('link_delivery')
    saved=d.read(root/'captures'/('capture-'+expected_capture_sha256)/'input.json')
    if set(saved)!={'manifest','packets'}:raise ValueError('saved capture differs')
    return run_capture(root,config,captured(config,saved['manifest'],saved['packets']),expected_capture_sha256,call)


def run_capture(root,config,bundle,expected_capture_sha256,call):
    d=local('link_delivery');c=local('contract')
    with locked(root):
        if bundle['sha256']!=expected_capture_sha256:raise ValueError('exact reviewed capture digest required')
        target(call,config['work_request'])
        known,high,_=completed(root,config)
        incoming={request['client_event_key']:c.digest(c.encoded(request)) for plan in bundle['plans'] for request in plan['requests']}
        if bundle['manifest']['next_after']<high or any(incoming.get(key)!=sha for key,sha in known.items()):
            raise ValueError('export regresses or changes already completed source claims')
        directory=root/'captures'/('capture-'+bundle['sha256'])
        if not directory.exists():
            if len(list((root/'captures').iterdir()))>=128:raise ValueError('sync capture bound exceeded')
            directory.mkdir(mode=0o700)
        d.guard(directory)
        frozen={'manifest':bundle['manifest'],'packets':bundle['packets']}
        if (directory/'input.json').exists():
            if d.read(directory/'input.json')!=frozen:raise ValueError('saved capture input differs')
        else:d.write(directory/'input.json',frozen)
        previous=None
        for index,packet in enumerate(bundle['packets']):
            page=directory/f'page-{index:03d}'
            if not page.exists():d.prepare(page,config['work_request'],packet,previous=previous)
            saved_page=d.read(page/'plan.json')
            if saved_page!={'work_request':config['work_request'],'packet':packet,'plan':bundle['plans'][index]}:
                raise ValueError('saved page differs from reviewed frozen input')
            d.deliver(page,lambda request:call({'method':'submit','request':request}),writer_uid=config['service_uid'],peer_uid=config['writer_uid'])
            previous=page
        result=completion(bundle,config)
        path=directory/'complete.json'
        if path.exists():
            if d.read(path)!=result:raise ValueError('completed capture differs')
        else:d.write(path,result)
        return result


def status(root):
    root=Path(root);config=configuration(root);known,high,count=completed(root,config)
    return {'work_item_id':config['binding']['work_item_id'],'completed_captures':count,'unique_linked_source_events':len(known),
            'completed_source_cursor':high,'source_freshness':'not_polled','automatic_capture':False,'authority_granted':False}


def completion(bundle,config):
    return {'contract':'engineering-managed-sync-complete.v1','capture_sha256':bundle['sha256'],'binding':config['binding'],
            'pages':len(bundle['plans']),'source_events':sum(len(plan['requests']) for plan in bundle['plans']),
            'next_after':bundle['manifest']['next_after'],'authority_granted':False,'release_status':'not_inferred','automatic_capture':False}
