"""Durable private import plan and receipts; no operational action or scheduler."""
import os
import re
from datetime import datetime
from pathlib import Path
import stat


def local(name):
    import importlib.util
    spec=importlib.util.spec_from_file_location('link_delivery_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def guard(root):
    if os.getuid()==0 or os.geteuid()!=os.getuid():raise ValueError('unprivileged link client required')
    root=Path(root);info=root.lstat()
    if root.resolve(strict=True)!=root or not root.is_absolute() or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('private caller-owned link state required')
    return root


def write(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(local('contract').encoded(value));stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def read(path):
    info=path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or
            stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>2*1024*1024):raise ValueError('private bounded link file required')
    return local('contract').decode(path.read_bytes(),max_bytes=2*1024*1024)


def prepare(root,work,packet,*,previous=None):
    link=local('managed_link');c=local('contract')
    work=c.validate(work);packet=link.validate(packet);plan=link.plan(work,packet)
    if previous is None:
        if packet['after']!=0:raise ValueError('initial import must start at source cursor zero')
    else:
        prior=guard(previous);saved=read(prior/'plan.json');old=link.plan(saved['work_request'],saved['packet'])
        complete=read(prior/'complete.json')
        if (saved['plan']!=old or complete!=completion(old) or plan['binding']!=old['binding'] or
                packet['after']!=old['next_after']):raise ValueError('completed matching prior import cursor required')
    root=Path(root)
    if not root.is_absolute() or root.parent.resolve(strict=True)!=root.parent:raise ValueError('canonical link state required')
    if os.getuid()==0 or os.geteuid()!=os.getuid():raise ValueError('unprivileged link client required')
    root.mkdir(mode=0o700);guard(root)
    bundle={'work_request':work,'packet':packet,'plan':plan}
    if len(c.encoded(bundle))>2*1024*1024:raise ValueError('link plan exceeds bound')
    write(root/'plan.json',bundle)
    return {'prepared':True,'requests':len(plan['requests']),'plan_sha256':c.digest(c.encoded(plan)),'delivery_started':False}


def check_receipt(receipt,request,writer_uid,peer_uid):
    c=local('contract');body=request['body']
    if type(receipt) is not dict:raise ValueError('import receipt must be an object')
    if (not isinstance(receipt.get('receipt_id'),str) or not re.fullmatch('rcp_[0-9a-f]{32}',receipt['receipt_id']) or
            type(receipt.get('sequence')) is not int or receipt['sequence']<1 or receipt.get('document_manifest') is not None):
        raise ValueError('import receipt identity differs')
    stamp=receipt.get('recorded_at')
    if not isinstance(stamp,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z',stamp):
        raise ValueError('import receipt timestamp differs')
    datetime.fromisoformat(stamp[:-1]+'+00:00')
    if (receipt.get('contract')!='engineering-history-receipt.v2' or receipt.get('transport')!='authenticated_local_service' or
            type(receipt.get('writer_uid')) is not int or receipt['writer_uid']!=writer_uid or
            type(receipt.get('peer_uid')) is not int or receipt['peer_uid']!=peer_uid or
            receipt.get('request_sha256')!=c.digest(c.encoded(request)) or receipt.get('work_item_id')!=body['work_item_id'] or
            receipt.get('work_revision_sha256')!=body['work_revision_sha256'] or receipt.get('provenance')!='imported' or
            receipt.get('authority_granted') is not False or receipt.get('visibility')!='operator_private'):
        raise ValueError('import receipt association differs')


def deliver(root,submit,*,writer_uid,peer_uid):
    root=guard(root)
    if type(peer_uid) is not int or peer_uid!=os.getuid() or type(writer_uid) is not int or writer_uid<1 or writer_uid in (996,997):
        raise ValueError('explicit caller and service identities required')
    c=local('contract');link=local('managed_link');bundle=read(root/'plan.json')
    if set(bundle)!={'work_request','packet','plan'}:raise ValueError('link bundle differs')
    plan=link.plan(bundle['work_request'],bundle['packet'])
    if bundle['plan']!=plan:raise ValueError('link plan differs')
    for index,request in enumerate(plan['requests']):
        path=root/f'receipt-{index:03d}.json'
        if path.exists() or path.is_symlink():receipt=read(path)
        else:
            answer=submit(request)
            if type(answer) is not dict or set(answer)!={'inserted','receipt'} or type(answer['inserted']) is not bool:
                raise ValueError('import response differs')
            receipt=answer['receipt'];check_receipt(receipt,request,writer_uid,peer_uid);write(path,receipt)
        check_receipt(receipt,request,writer_uid,peer_uid)
    complete=completion(plan)
    path=root/'complete.json'
    if path.exists() or path.is_symlink():
        if read(path)!=complete:raise ValueError('completed import checkpoint differs')
    else:write(path,complete)
    return complete


def completion(plan):
    return {'plan_sha256':local('contract').digest(local('contract').encoded(plan)),'binding':plan['binding'],
            'source_packet_sha256':plan['source_packet_sha256'],'next_after':plan['next_after'],
            'has_more':plan['has_more'],'receipts':len(plan['requests']),'authority_granted':False,
            'release_status':'not_inferred'}
