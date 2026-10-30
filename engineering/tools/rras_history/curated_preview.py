"""Private curated retrieval previews. No publication, service grant or root access.

Input rows are supplied claims; a valid digest is consistency, not authentication.
"""
import importlib.util
from pathlib import Path
import re
from datetime import datetime

LIMIT=2*1024*1024


def local():
    spec=importlib.util.spec_from_file_location('curated_contract',Path(__file__).with_name('contract.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def text(value,limit):
    if type(value) is not str or not value.strip() or len(value.encode())>limit or any(ord(ch)<32 and ch not in '\n\t' for ch in value):
        raise ValueError('bounded explicit curated text required')
    return value


def build(rows,selections):
    c=local();rows=c.decode(c.encoded(rows),max_bytes=LIMIT);selections=c.decode(c.encoded(selections),max_bytes=LIMIT)
    if type(rows) is not list or len(rows)>1000 or type(selections) is not list or not 1<=len(selections)<=100:
        raise ValueError('bounded source and explicit selections required')
    source={};repos={}
    for row in rows:
        if type(row) is not dict or set(row)!={'submission','receipt'}:raise ValueError('history row required')
        request=c.validate(row['submission']);sha=c.digest(c.encoded(request));receipt=row['receipt'];body=request['body']
        if (type(receipt) is not dict or receipt.get('request_sha256')!=sha or receipt.get('work_item_id')!=body['work_item_id'] or
                not isinstance(receipt.get('receipt_id'),str) or not re.fullmatch('rcp_[0-9a-f]{32}',receipt['receipt_id'])):
            raise ValueError('source receipt association differs')
        stamp=receipt.get('recorded_at')
        if type(stamp) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z',stamp):raise ValueError('source recording time required')
        datetime.fromisoformat(stamp[:-1]+'+00:00')
        if sha in source:raise ValueError('duplicate source request')
        source[sha]=(request,receipt)
        if request['operation'].startswith('work.'):
            work_id=body['work_item_id'];repo=body['repository_id']
            if work_id in repos and repos[work_id]!=repo:raise ValueError('work cannot move repositories')
            repos[work_id]=repo
    entries=[];seen=set()
    for selection in selections:
        if type(selection) is not dict or set(selection)!={'source_request_sha256','summary','rationale','limitations'}:
            raise ValueError('exact curated selection required')
        sha=selection['source_request_sha256']
        if type(sha) is not str or sha not in source or sha in seen:raise ValueError('unique exact source selection required')
        seen.add(sha);request,receipt=source[sha];work_id=request['body']['work_item_id']
        if work_id not in repos:raise ValueError('source work repository missing')
        for key in ('summary','rationale','limitations'):text(selection[key],4096)
        entry={'entry_id':'cur_'+c.digest(c.encoded(selection)),'repository_id':repos[work_id],'work_item_id':work_id,
            'summary':selection['summary'],'rationale':selection['rationale'],'limitations':selection['limitations'],
            'source_operation':request['operation'],'source_provenance':request['source']['kind'],
            'source_request_sha256':sha,'source_receipt_id':receipt['receipt_id'],
            'source_recorded_at':receipt['recorded_at'],'source_occurred_at':request['occurred_at'],
            'curation_provenance':'agent_reported','source_authenticated':False,'release_status':'not_inferred'}
        entries.append(entry)
    preview={'contract':'engineering-curated-preview.v1','audience':'jarvis_candidate','visibility':'operator_private',
             'publication_authorized':False,'authority_granted':False,'source_freshness':'not_polled','entries':entries}
    if len(c.encoded(preview))>LIMIT:raise ValueError('preview exceeds bound')
    return preview


def search(preview,reviewed_sha256,repository_id,query,*,offset=0,limit=20):
    """Search only a pinned private preview; caller access policy remains external."""
    c=local();preview=c.decode(c.encoded(preview),max_bytes=LIMIT)
    if c.digest(c.encoded(preview))!=reviewed_sha256:raise ValueError('reviewed preview changed')
    if (type(preview) is not dict or set(preview)!={'contract','audience','visibility','publication_authorized','authority_granted','source_freshness','entries'} or
            preview['contract']!='engineering-curated-preview.v1' or preview['audience']!='jarvis_candidate' or
            preview['visibility']!='operator_private' or preview['publication_authorized'] is not False or
            preview['authority_granted'] is not False or preview['source_freshness']!='not_polled' or
            type(preview['entries']) is not list or len(preview['entries'])>100):raise ValueError('private preview required')
    fields={'entry_id','repository_id','work_item_id','summary','rationale','limitations','source_operation',
            'source_provenance','source_request_sha256','source_receipt_id','source_recorded_at','source_occurred_at',
            'curation_provenance','source_authenticated','release_status'}
    seen=set()
    for entry in preview['entries']:
        if type(entry) is not dict or set(entry)!=fields:raise ValueError('exact curated entry required')
        for key in ('summary','rationale','limitations'):text(entry[key],4096)
        selected={key:entry[key] for key in ('source_request_sha256','summary','rationale','limitations')}
        if (entry['entry_id']!='cur_'+c.digest(c.encoded(selected)) or entry['entry_id'] in seen or
                entry['curation_provenance']!='agent_reported' or entry['source_authenticated'] is not False or
                entry['release_status']!='not_inferred' or entry['source_provenance'] not in ('agent_reported','human_reported','imported') or
                entry['source_operation'] not in ('work.create','work.revise','session.attach','checkpoint.append','outcome.record','document.render')):
            raise ValueError('curated source claims grant no authority')
        for key,pattern in (('repository_id','[A-Za-z0-9][A-Za-z0-9_.-]{0,95}'),('work_item_id','wrk_[0-9a-f]{32}'),
                            ('source_request_sha256','[0-9a-f]{64}'),('source_receipt_id','rcp_[0-9a-f]{32}')):
            if type(entry[key]) is not str or not re.fullmatch(pattern,entry[key]):raise ValueError('exact curated identity required')
        for key in ('source_recorded_at','source_occurred_at'):
            value=entry[key]
            if value is None and key=='source_occurred_at':continue
            if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z',value):raise ValueError('explicit source time required')
            datetime.fromisoformat(value[:-1]+'+00:00')
        seen.add(entry['entry_id'])
    if type(repository_id) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',repository_id):raise ValueError('exact repository required')
    if type(query) is not str or len(query.encode())>256 or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50:
        raise ValueError('bounded query/cursor required')
    terms=query.casefold().split();matches=[]
    for entry in preview['entries']:
        if entry['repository_id']!=repository_id:continue
        haystack=' '.join(entry[key] for key in ('summary','rationale','limitations')).casefold()
        if all(term in haystack for term in terms):matches.append(entry)
    page=matches[offset:offset+limit]
    return {'entries':page,'next_offset':offset+len(page),'has_more':offset+len(page)<len(matches),
            'preview_sha256':reviewed_sha256,'publication_authorized':False,'authority_granted':False,'source_freshness':'not_polled'}
