"""Repository-scoped curated search/read dispatcher; no private-history routes.

Peer UID must come from the kernel transport, never caller JSON. Policy is trusted.
"""
import copy
import importlib.util
from pathlib import Path
import re


def local(name):
    spec=importlib.util.spec_from_file_location('curated_reader_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Access:
    def __init__(self,catalog_root,policy):
        if type(policy) is not dict or set(policy)!={'contract','principals'} or policy['contract']!='engineering-curated-read-access.v1':
            raise ValueError('curated read policy required')
        if type(policy['principals']) is not list or len(policy['principals'])>128:raise ValueError('bounded reader policy required')
        self.grants={}
        for item in policy['principals']:
            if type(item) is not dict or set(item)!={'uid','repositories'}:raise ValueError('read-only principal required')
            uid=item['uid'];repos=item['repositories']
            local('unix').uid(uid)
            if uid in self.grants or type(repos) is not list or len(repos)>128 or any(type(repo) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',repo) for repo in repos) or len(set(repos))!=len(repos):
                raise ValueError('exact distinct reader/repository grants required')
            self.grants[uid]=copy.deepcopy(repos)
        self.root,config=local('curated_publication').configuration(catalog_root)
        if any(repo not in config['repositories'] for repos in self.grants.values() for repo in repos):raise ValueError('reader exceeds catalog repository policy')

    def dispatch(self,peer_uid,message):
        if type(peer_uid) is not int or peer_uid not in self.grants:raise ValueError('access refused')
        if type(message) is not dict or message.get('repository_id') not in self.grants[peer_uid]:raise ValueError('access refused')
        method=message.get('method');repo=message['repository_id'];catalog=local('curated_publication')
        if method=='search' and set(message)=={'method','repository_id','query','generation_sha256','offset','limit'}:
            generation=message['generation_sha256']
            if generation is not None and (type(generation) is not str or not re.fullmatch('[0-9a-f]{64}',generation)):raise ValueError('exact generation required')
            return catalog.search(self.root,repo,message['query'],generation_sha256=generation,offset=message['offset'],limit=message['limit'])
        if method=='read' and set(message)=={'method','repository_id','entry_id','generation_sha256'}:
            entry_id=message['entry_id'];generation=message['generation_sha256']
            if (type(entry_id) is not str or not re.fullmatch('cur_[0-9a-f]{64}',entry_id) or
                    type(generation) is not str or not re.fullmatch('[0-9a-f]{64}',generation)):raise ValueError('exact entry and generation required')
            for offset in (0,50):
                page=catalog.search(self.root,repo,'',generation_sha256=generation,offset=offset,limit=50)
                for entry in page['entries']:
                    if entry['entry_id']==entry_id:
                        return {'entry':entry,'generation_sha256':generation,'authority_granted':False,
                                'human_authenticated':False,'source_freshness':'not_polled'}
                if not page['has_more']:break
            raise ValueError('curated entry unavailable')
        raise ValueError('unsupported curated read message')
