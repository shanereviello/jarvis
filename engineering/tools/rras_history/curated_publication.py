"""Private local publication catalog; no listener, sharing grant or production path.

The owner is trusted. Publication flags record local selection, not human identity.
"""
from datetime import datetime,timezone
import importlib.util
import os
from pathlib import Path
import re


def local(name):
    spec=importlib.util.spec_from_file_location('curated_publication_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def initialize(root,repositories):
    if (type(repositories) is not list or not 1<=len(repositories)<=128 or len(set(repositories))!=len(repositories) or
            any(type(repo) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',repo) for repo in repositories)):
        raise ValueError('explicit repository policy required')
    root=Path(root);d=local('link_delivery')
    if not root.is_absolute():raise ValueError('absolute private catalog required')
    d.guard(root.parent);root.mkdir(mode=0o700);d.guard(root)
    d.write(root/'configuration.json',{'contract':'engineering-curated-catalog.v1','owner_uid':os.getuid(),'repositories':repositories})
    (root/'generations').mkdir(mode=0o700);sync(root)
    return {'initialized':True,'publication_recorded':False,'authority_granted':False}


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def configuration(root):
    d=local('link_delivery');root=d.guard(Path(root));config=d.read(root/'configuration.json');d.guard(root/'generations')
    if (type(config) is not dict or set(config)!={'contract','owner_uid','repositories'} or
            config['contract']!='engineering-curated-catalog.v1' or type(config['owner_uid']) is not int or config['owner_uid']!=os.getuid() or
            type(config['repositories']) is not list or not 1<=len(config['repositories'])<=128 or
            any(type(repo) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',repo) for repo in config['repositories']) or
            len(set(config['repositories']))!=len(config['repositories'])):raise ValueError('fixed repository policy differs')
    return root,config


def validate_preview(preview,repositories):
    c=local('contract');preview=c.decode(c.encoded(preview),max_bytes=2*1024*1024)
    sha=c.digest(c.encoded(preview))
    # This validates every entry/header before filtering; no source fallback.
    local('curated_preview').search(preview,sha,repositories[0],'',limit=1)
    if any(entry['repository_id'] not in repositories for entry in preview['entries']):raise ValueError('publication outside repository policy')
    return preview


def head(root):
    path=root/'current.json'
    if not path.exists() and not path.is_symlink():return None
    value=local('link_delivery').read(path)
    if type(value) is not dict or set(value)!={'generation_sha256'} or not isinstance(value['generation_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',value['generation_sha256']):
        raise ValueError('catalog pointer differs')
    return value['generation_sha256']


def chain(root,config):
    c=local('contract');d=local('link_delivery');current=head(root);rows=[];seen=set()
    while current is not None:
        if current in seen or len(rows)>=128:raise ValueError('bounded acyclic catalog required')
        seen.add(current);value=d.read(root/'generations'/(current+'.json'))
        if (type(value) is not dict or set(value)!={'request','preview','receipt'} or c.digest(c.encoded(value))!=current):raise ValueError('generation digest differs')
        request=value['request'];receipt=value['receipt']
        if (type(request) is not dict or set(request)!={'operation','client_key','expected_head','preview_sha256','withdrawn_ids'} or
                request['operation'] not in ('publish','withdraw') or type(request['client_key']) is not str or
                not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',request['client_key']) or
                (request['expected_head'] is not None and (type(request['expected_head']) is not str or not re.fullmatch('[0-9a-f]{64}',request['expected_head']))) or
                type(request['withdrawn_ids']) is not list or len(request['withdrawn_ids'])>100):raise ValueError('generation request differs')
        preview=validate_preview(value['preview'],config['repositories'])
        if request['preview_sha256']!=c.digest(c.encoded(preview)):raise ValueError('generation preview differs')
        if (type(receipt) is not dict or set(receipt)!={'contract','request_sha256','recorded_at','owner_uid','publication_recorded','human_authenticated','authority_granted'} or
                receipt['contract']!='engineering-curated-publication-receipt.v1' or receipt['request_sha256']!=c.digest(c.encoded(request)) or
                receipt['owner_uid']!=config['owner_uid'] or receipt['publication_recorded'] is not True or
                receipt['human_authenticated'] is not False or receipt['authority_granted'] is not False):raise ValueError('generation receipt differs')
        datetime.fromisoformat(receipt['recorded_at'].replace('Z','+00:00'))
        rows.append((current,value));current=request['expected_head']
    return rows


def publish(root,preview,reviewed_sha256,expected_head,client_key,*,approve_publication=False):
    if approve_publication is not True:raise ValueError('explicit curated publication approval required')
    root,config=configuration(root);preview=validate_preview(preview,config['repositories']);c=local('contract')
    if c.digest(c.encoded(preview))!=reviewed_sha256:raise ValueError('exact reviewed preview required')
    return commit(root,config,'publish',preview,expected_head,client_key,[])


def withdraw(root,entry_ids,expected_head,client_key,*,approve_withdrawal=False):
    if approve_withdrawal is not True:raise ValueError('explicit withdrawal approval required')
    root,config=configuration(root)
    if (type(entry_ids) is not list or not 1<=len(entry_ids)<=100 or any(type(item) is not str or not re.fullmatch('cur_[0-9a-f]{64}',item) for item in entry_ids) or
            len(set(entry_ids))!=len(entry_ids)):raise ValueError('exact withdrawn entry identities required')
    return commit(root,config,'withdraw',None,expected_head,client_key,entry_ids)


def commit(root,config,operation,preview,expected_head,client_key,withdrawn):
    c=local('contract');d=local('link_delivery')
    if type(client_key) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',client_key):raise ValueError('bounded publication key required')
    if expected_head is not None and (type(expected_head) is not str or not re.fullmatch('[0-9a-f]{64}',expected_head)):raise ValueError('exact expected generation required')
    with local('managed_sync').locked(root):
        rows=chain(root,config);current=rows[0][0] if rows else None
        # Reconstruct a withdrawal from its exact historical base, including on replay.
        if operation=='withdraw':
            base=next((value['preview'] for sha,value in rows if sha==expected_head),None)
            if base is None or not set(withdrawn)<={e['entry_id'] for e in base['entries']}:raise ValueError('withdrawal source unavailable')
            preview=c.decode(c.encoded(base),max_bytes=2*1024*1024)
            preview['entries']=[e for e in preview['entries'] if e['entry_id'] not in withdrawn]
        request={'operation':operation,'client_key':client_key,'expected_head':expected_head,
                 'preview_sha256':c.digest(c.encoded(preview)),'withdrawn_ids':withdrawn}
        for sha,value in rows:
            if value['request']['client_key']==client_key:
                if value['request']!=request:raise ValueError('publication key conflict')
                return dict(value['receipt'],generation_sha256=sha,replayed=True)
        if current!=expected_head:raise ValueError('stale publication generation')
        if len(rows)>=128:raise ValueError('catalog generation bound exceeded')
        # A retained intent after failure needs diagnosis, not automatic retry.
        d.write(root/('intent-'+c.digest(c.encoded(client_key))+'.json'),request)
        receipt={'contract':'engineering-curated-publication-receipt.v1','request_sha256':c.digest(c.encoded(request)),
                 'recorded_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'owner_uid':os.getuid(),
                 'publication_recorded':True,'human_authenticated':False,'authority_granted':False}
        value={'request':request,'preview':preview,'receipt':receipt};sha=c.digest(c.encoded(value))
        if len(c.encoded(value))>2*1024*1024:raise ValueError('generation exceeds bound')
        # Unreferenced generations/pending files are retained, never auto-adopted.
        d.write(root/'generations'/(sha+'.json'),value)
        pending=root/('.current-'+receipt['request_sha256']+'.pending');d.write(pending,{'generation_sha256':sha})
        os.replace(pending,root/'current.json');sync(root)
        return dict(receipt,generation_sha256=sha,replayed=False)


def search(root,repository_id,query,*,generation_sha256=None,offset=0,limit=20):
    root,config=configuration(root)
    if type(repository_id) is not str or repository_id not in config['repositories']:raise ValueError('repository access refused')
    if offset!=0 and generation_sha256 is None:raise ValueError('generation-bound page cursor required')
    rows=chain(root,config)
    if not rows:
        if generation_sha256 is not None:raise ValueError('stale catalog cursor; discard cached results')
        c=local('contract')
        empty={'contract':'engineering-curated-preview.v1','audience':'jarvis_candidate','visibility':'operator_private',
               'publication_authorized':False,'authority_granted':False,'source_freshness':'not_polled','entries':[]}
        answer=local('curated_preview').search(empty,c.digest(c.encoded(empty)),repository_id,query,offset=offset,limit=limit)
        return dict(answer,generation_sha256=None,publication_recorded=False,human_authenticated=False,catalog_state='empty')
    current,value=rows[0]
    if generation_sha256 is not None and generation_sha256!=current:raise ValueError('stale catalog cursor; discard cached results')
    c=local('contract');answer=local('curated_preview').search(value['preview'],c.digest(c.encoded(value['preview'])),repository_id,query,offset=offset,limit=limit)
    return dict(answer,generation_sha256=current,publication_recorded=True,human_authenticated=False)
