"""Private repository-scoped service dispatcher; no listener or peer discovery.

The adapter must supply a kernel-authenticated UID, never a JSON actor field.
The store owner is the trusted service boundary, not an adversarial caller.
"""
import copy
import re

from pathlib import Path
import importlib.util


def local(name):
    spec = importlib.util.spec_from_file_location('history_access_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


class Access:
    def __init__(self, store, policy):
        # Exact in-memory configuration. Loading/protecting a host policy file and
        # obtaining SO_PEERCRED belong to the following transport/install slice.
        if type(policy) is not dict or set(policy) != {'contract', 'principals'} or policy['contract'] != 'engineering-history-access.v1':
            raise ValueError('invalid access policy')
        if type(policy['principals']) is not list or len(policy['principals']) > 128:
            raise ValueError('bounded principal policy required')
        self.grants = {}
        for entry in policy['principals']:
            if type(entry) is not dict or set(entry) != {'uid', 'private_read', 'write'}:
                raise ValueError('invalid principal policy')
            uid = entry['uid']
            if type(uid) is not int or not 1 <= uid < 2**32 - 1 or uid in (996, 997) or uid in self.grants:
                raise ValueError('inadmissible or duplicate principal')
            for name in ('private_read', 'write'):
                values = entry[name]
                if (type(values) is not list or len(values) > 128 or
                        any(type(v) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', v) for v in values) or
                        len(set(values)) != len(values)):
                    raise ValueError('exact repository grants required')
            # Writes return private work heads and document receipts. Require an
            # explicit private-read grant rather than creating a covert read role.
            if not set(entry['write']) <= set(entry['private_read']):
                raise ValueError('write requires explicit private read')
            self.grants[uid] = copy.deepcopy(entry)
        self.store = store

    def dispatch(self, peer_uid, message):
        if type(peer_uid) is not int or peer_uid not in self.grants:
            raise ValueError('access refused')
        if type(message) is not dict or 'method' not in message:
            raise ValueError('invalid service message')
        grant = self.grants[peer_uid]
        method = message['method']
        if method == 'submit' and set(message) == {'method', 'request'}:
            request = local('contract').validate(copy.deepcopy(message['request']))
            body = request['body']
            with self.store.connection() as db:
                rows = self.store.rows(db)
            works = {r['body']['work_item_id']: r['body']['repository_id']
                     for r, _, _, _ in rows if r['operation'].startswith('work.')}
            repo = body.get('repository_id', works.get(body['work_item_id']))
            # Check both proposed and existing repository before duplicate lookup.
            # A revision cannot move a work item across an access boundary.
            existing = works.get(body['work_item_id'])
            if repo not in grant['write'] or (existing is not None and existing not in grant['write']):
                raise ValueError('access refused')
            return self.store.submit(request, peer_uid=peer_uid)
        if method == 'history' and set(message) == {'method', 'repository_id', 'offset', 'limit'}:
            repo = message['repository_id']; offset = message['offset']; limit = message['limit']
            if type(repo) is not str or repo not in grant['private_read']:
                raise ValueError('access refused')
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise ValueError('bounded cursor required')
            with self.store.connection() as db:
                rows = self.store.rows(db)
            works = {r['body']['work_item_id']: r['body']['repository_id']
                     for r, _, _, _ in rows if r['operation'].startswith('work.')}
            selected = [{'submission': r, 'receipt': receipt} for r, receipt, _, _ in rows
                        if works[r['body']['work_item_id']] == repo]
            page = selected[offset:offset + limit]
            return dict(records=page, next_offset=offset + len(page),
                        has_more=offset + len(page) < len(selected), audience='authorized_repository_private',
                        authority_granted=False)
        if method == 'document' and set(message) == {'method', 'document_id', 'version'}:
            doc_id = message['document_id']; version = message['version']
            if type(doc_id) is not str or not re.fullmatch('doc_[0-9a-f]{32}', doc_id):
                raise ValueError('document unavailable')
            if version is not None and (type(version) is not int or version < 1):
                raise ValueError('document unavailable')
            with self.store.connection() as db:
                rows = self.store.rows(db)
            works = {r['body']['work_item_id']: r['body']['repository_id']
                     for r, _, _, _ in rows if r['operation'].startswith('work.')}
            selected = [(raw, meta) for r, _, raw, meta in rows if r['operation'] == 'document.render' and
                        r['body']['document_id'] == doc_id and
                        works[r['body']['work_item_id']] in grant['private_read'] and
                        (version is None or r['body']['document_version'] == version)]
            if not selected: raise ValueError('document unavailable')
            raw, manifest = selected[-1]
            return dict(markdown=raw.decode('utf-8'), manifest=manifest, authority_granted=False)
        raise ValueError('unsupported service message')
