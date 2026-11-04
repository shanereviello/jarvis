"""Bounded repository-authorized reads only; never opens SQLite or submits notes."""
import hashlib
import importlib.util
import json
from functools import lru_cache
from pathlib import Path
import re
import time
from urllib.parse import urlsplit


@lru_cache(maxsize=2)
def local(name):
    path=Path(__file__).parents[1]/'rras_history'/(name+'.py')
    spec=importlib.util.spec_from_file_location('web_history_'+name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def integer(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('unavailable')
    return value


def evidence(body):
    references=list(body.get('references',[]))
    if type(body.get('summary')) is str:
        try:
            quoted=json.loads(body['summary'].split('\n',1)[1])['source_fact']
            references+=quoted.get('public_references',[])
        except (ValueError,KeyError,TypeError,IndexError):pass
    links=[]
    for reference in references[:128]:
        if type(reference) is not dict:continue
        url=reference.get('id','')
        if type(url) is not str or len(url)>2048:continue
        try:parts=urlsplit(url)
        except ValueError:continue
        if parts.scheme=='https' and parts.netloc=='github.com' and parts.path.startswith('/') and not any(ord(c)<33 for c in url):
            links.append({'url':url,'label':url.removeprefix('https://')})
    return links


class Reader:
    def __init__(self,repositories,call):
        if (type(repositories) not in (list,tuple) or not 1<=len(repositories)<=128 or len(set(repositories))!=len(repositories) or
                any(type(repo) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',repo) for repo in repositories)):
            raise ValueError('explicit repository read grants required')
        self.repositories=tuple(repositories);self.call=call

    def records(self,repo):
        if repo not in self.repositories:raise ValueError('unavailable')
        rows=[];offset=0;size=0;previous=0;deadline=time.monotonic()+15
        for _ in range(1001):
            if time.monotonic()>deadline:raise ValueError('unavailable')
            page=self.call({'method':'history','repository_id':repo,'offset':offset,'limit':10})
            if (type(page) is not dict or page.get('audience')!='authorized_repository_private' or page.get('authority_granted') is not False or
                    type(page.get('records')) is not list or len(page['records'])>10 or type(page.get('has_more')) is not bool or
                    type(page.get('next_offset')) is not int or page['next_offset']!=offset+len(page['records'])):raise ValueError('unavailable')
            for row in page['records']:
                if type(row) is not dict or set(row)!={'submission','receipt'}:raise ValueError('unavailable')
                request=local('contract').validate(row['submission']);receipt=row['receipt']
                if (type(receipt) is not dict or receipt.get('request_sha256')!=local('contract').digest(local('contract').encoded(request)) or
                        receipt.get('authority_granted') is not False or receipt.get('visibility')!='operator_private' or
                        receipt.get('work_item_id')!=request['body']['work_item_id'] or receipt.get('provenance')!=request['source']['kind'] or
                        type(receipt.get('sequence')) is not int or receipt['sequence']<=previous):raise ValueError('unavailable')
                if request['operation'].startswith('work.') and request['body']['repository_id']!=repo:raise ValueError('unavailable')
                previous=receipt['sequence'];size+=len(local('contract').encoded(row));rows.append(row)
                if size>8*1024*1024 or len(rows)>10000:raise ValueError('unavailable')
            if not page['has_more']:return rows
            if not page['records']:raise ValueError('unavailable')
            offset=page['next_offset']
        raise ValueError('unavailable')

    def works(self,repo,query='',offset=0,limit=20):
        integer(offset,0,10000);integer(limit,1,50)
        if type(query) is not str or len(query)>200:raise ValueError('unavailable')
        works={};rows=self.records(repo)
        for row in rows:
            request=row['submission'];body=request['body'];work=body['work_item_id']
            if request['operation'].startswith('work.'):
                works[work]={'work_item_id':work,'title':body['title'],'objective':body['objective'],'rationale':body['rationale'],
                    'revision':body['revision'],'last_recorded_at':row['receipt']['recorded_at'],'latest_outcome':None,'records':0}
        for row in rows:
            body=row['submission']['body'];work=works.get(body['work_item_id'])
            if work is None:raise ValueError('unavailable')
            work['records']+=1;work['last_recorded_at']=row['receipt']['recorded_at']
            if row['submission']['operation']=='outcome.record':work['latest_outcome']=body['outcome']
        return self._work_page(repo,query,offset,limit,works)

    def _work_page(self,repo,query,offset,limit,works):
        # Work definitions are indexed without inferring execution from existence.
        values=[work for work in works.values() if all(term in ' '.join((work['title'],work['objective'],work['rationale'])).casefold() for term in query.casefold().split())]
        values.sort(key=lambda work:(work['last_recorded_at'],work['work_item_id']),reverse=True)
        return {'repository_id':repo,'works':values[offset:offset+limit],'total':len(values),'next_offset':offset+len(values[offset:offset+limit]),
            'has_more':offset+limit<len(values),'retrieval':'history_service_snapshot','authority_granted':False}

    def work(self,repo,work_id):
        if type(work_id) is not str or not re.fullmatch('wrk_[0-9a-f]{32}',work_id):raise ValueError('unavailable')
        rows=[row for row in self.records(repo) if row['submission']['body']['work_item_id']==work_id]
        definitions=[row['submission']['body'] for row in rows if row['submission']['operation'].startswith('work.')]
        if not definitions:raise ValueError('unavailable')
        definition=max(definitions,key=lambda value:value['revision']);timeline=[];documents=[];links=[]
        for row in rows:
            request=row['submission'];body=request['body'];receipt=row['receipt']
            timeline.append({'operation':request['operation'],'summary':body.get('summary',body.get('objective',body.get('fields',{}).get('title','Work association recorded'))),
                'recorded_at':receipt['recorded_at'],'occurred_at':request['occurred_at'],'provenance':request['source']['kind'],
                'receipt_id':receipt['receipt_id'],'sequence':receipt['sequence'],'session_id':body.get('session_id'),
                'outcome':body.get('outcome'),'decisions':body.get('decisions',[]),'next_action':body.get('next_action')})
            if request['operation']=='document.render':documents.append({'document_id':body['document_id'],'version':body['document_version'],
                'type':body['document_type'],'title':body['fields']['title'],'markdown_sha256':receipt['document_manifest']['markdown_sha256'],
                'manifest':receipt['document_manifest']})
            links+=evidence(body)
        return {'repository_id':repo,'work':definition,'timeline':timeline,'documents':documents,
            'evidence':list({link['url']:link for link in links}.values()),'authority_granted':False,'release_status':'not_inferred',
            'retrieval':'history_service_snapshot'}

    def document(self,repo,work_id,doc_id,version):
        integer(version,1,1000000)
        if type(doc_id) is not str or not re.fullmatch('doc_[0-9a-f]{32}',doc_id):raise ValueError('unavailable')
        work=self.work(repo,work_id)
        selected=[doc for doc in work['documents'] if doc['document_id']==doc_id and doc['version']==version]
        if len(selected)!=1:raise ValueError('unavailable')
        result=self.call({'method':'document','document_id':doc_id,'version':version})
        if type(result) is not dict or result.get('authority_granted') is not False or type(result.get('markdown')) is not str:raise ValueError('unavailable')
        raw=result['markdown'].encode();manifest=result.get('manifest')
        if (len(raw)>256*1024 or type(manifest) is not dict or manifest!=selected[0]['manifest'] or manifest.get('document_id')!=doc_id or manifest.get('document_version')!=version or
                manifest.get('work_item_id')!=work_id or manifest.get('visibility')!='operator_private' or
                hashlib.sha256(raw).hexdigest()!=manifest.get('markdown_sha256') or manifest['markdown_sha256']!=selected[0]['markdown_sha256']):raise ValueError('unavailable')
        return {'markdown':result['markdown'],'manifest':manifest,'digest_verified':True,'authority_granted':False}
