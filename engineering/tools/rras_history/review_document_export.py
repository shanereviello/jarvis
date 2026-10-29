"""Root-only historical document custody reader and explicit private handoff.

No live admission approval, model run, service mutation or history submission.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import sys

JOURNALS=Path('/var/lib/rras-history-exports')
HANDOFFS=Path('/var/lib/rras-history-handoffs')
READER=1000


def local(name):
    s=importlib.util.spec_from_file_location('review_export_'+name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def protected(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical protected export path required')
    for item in (path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('root-protected export path required')
    return path


def administrator():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('root private export required')
    protected(Path(__file__))


def read(path,limit):
    path=protected(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:raise ValueError('bounded regular protected source required')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('protected source exceeds bound')
        return raw
    finally:os.close(fd)


def source_module(code_root,manifest_sha256):
    root=protected(code_root)
    if type(manifest_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',manifest_sha256):raise ValueError('exact source manifest required')
    raw=read(root/'release-manifest.json',1024*1024)
    if hashlib.sha256(raw).hexdigest()!=manifest_sha256:raise ValueError('source manifest changed')
    manifest=local('contract').decode(raw,max_bytes=1024*1024)
    if type(manifest) is not dict:raise ValueError('source manifest object required')
    files=manifest.get('files')
    if type(files) is not dict or not 1<=len(files)<=512:raise ValueError('bounded source manifest files required')
    total=0
    for name,sha in files.items():
        p=PurePosixPath(name)
        if (p.is_absolute() or str(p)!=name or '..' in p.parts or not name.startswith(('engineering/','vendor/','config/','entrypoints/')) or
                type(sha) is not str or not re.fullmatch('[0-9a-f]{64}',sha)):raise ValueError('invalid source manifest member')
        content=read(root/name,4*1024*1024);total+=len(content)
        if total>16*1024*1024 or hashlib.sha256(content).hexdigest()!=sha:raise ValueError('source payload changed')
    name='engineering/tools/rras_native/document_approval.py'
    if name not in files:raise ValueError('document source module absent')
    # All imports below use verified root-owned source/vendor, never the handoff.
    sys.path.insert(0,str(root/'vendor'))
    s=importlib.util.spec_from_file_location('historical_document_source',root/name)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def snapshot(state,review_id,code_root,manifest_sha256,*,approve_private_export=False):
    administrator()
    if approve_private_export is not True:raise ValueError('explicit private document export approval required')
    if type(review_id) is not str or not re.fullmatch('[0-9a-f]{64}',review_id):raise ValueError('exact review identity required')
    doc=source_module(code_root,manifest_sha256);operator=doc.local('operator_control');state=operator.require_operator(state)
    a=doc.local('activity');review=doc.private_read(state/(review_id+'.review.json'))
    if a.digest(a.encoded(review))!=review_id:raise ValueError('historical capture changed')
    # Custody is historical. Live registration, Git refs and session settings may
    # have changed; do not call validate_review or turn export into a launch grant.
    if review['admission']['control_files']!=operator.control_hashes():raise ValueError('different captured source version')
    value=doc.private_read(doc.marker(state,review_id))
    if (set(value)!={'contract','review_id','configuration','work_request','narrative','package'} or
            value['contract']!='protected-engineering-review.v1' or value['review_id']!=review_id or
            value['configuration']!=review['admission']['configuration'] or
            value['work_request']['body']['work_item_id']!=review['admission']['work_item']['work_item_id']):
        raise ValueError('historical document association changed')
    doc.local('managed_review','rras_history').verify(value['package'],review,review_id,value['work_request'],value['narrative'])
    if doc.private_bytes(state/(review_id+'.review.md'))!=value['package']['markdown'].encode():raise ValueError('historical Markdown changed')
    return local('review_document_link').build(value)


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def write(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sync(path.parent)


def parent(path,mode):
    path=Path(path)
    if not path.exists():protected(path.parent);path.mkdir(mode=mode);path.chmod(mode);sync(path.parent)
    protected(path);info=path.stat()
    if (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(0,0,mode):raise ValueError('exact export parent role required')
    return path


def handoff(export_id,packet,*,approve_private_export=False,journal_parent=JOURNALS,handoff_parent=HANDOFFS):
    administrator()
    if approve_private_export is not True:raise ValueError('explicit private document handoff approval required')
    if type(export_id) is not str or not re.fullmatch('[0-9a-f]{32}',export_id):raise ValueError('fresh export identity required')
    packet=local('review_document_link').validate(packet);c=local('contract');raw=c.encoded(packet)
    journals=parent(journal_parent,0o700);handoffs=parent(handoff_parent,0o711)
    journal=journals/('document-'+export_id);receiver=handoffs/('document-'+export_id)
    if any(path.exists() or path.is_symlink() for path in (journal,receiver)):raise ValueError('preserve existing document export; no retry')
    journal.mkdir(mode=0o700);sync(journals)
    manifest={'contract':'engineering-private-document-handoff.v1','packet_sha256':c.digest(raw),
              'review_id':packet['binding']['review_id'],'document_id':packet['manifest']['document_id'],
              'markdown_sha256':packet['binding']['markdown_sha256'],'reader_uid':READER,
              'source_provenance':'imported','authority_granted':False}
    write(journal/'packet.json',raw);write(journal/'handoff.json',c.encoded(manifest))
    receiver.mkdir(mode=0o700)
    for name,value in (('packet.json',raw),('handoff.json',c.encoded(manifest))):write(receiver/name,value)
    sync(receiver)
    for name in ('packet.json','handoff.json'):os.chown(receiver/name,READER,READER,follow_symlinks=False)
    os.chown(receiver,READER,READER,follow_symlinks=False)  # Transfer last; no root writes inside afterward.
    sync(handoffs)
    result={'phase':'private_review_document_handoff_complete','journal':str(journal),'handoff':str(receiver),
            'packet_sha256':manifest['packet_sha256'],'history_records_written':False,'authority_granted':False,'api_calls':0}
    write(journal/'complete.json',c.encoded(result));return result
