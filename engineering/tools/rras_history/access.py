"""Private repository-scoped service dispatcher; no listener or peer discovery.

The adapter must supply a kernel-authenticated UID, never a JSON actor field.
The store owner is the trusted service boundary, not an adversarial caller.
"""
import copy
import re
import uuid

from pathlib import Path
import importlib.util


def local(name):
    spec = importlib.util.spec_from_file_location('history_access_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


class Access:
    def __init__(self, store, policy):
        # Exact in-memory configuration. Loading/protecting a host policy file and
        # obtaining SO_PEERCRED belong to the following transport/install slice.
        if type(policy) is not dict or set(policy) != {'contract', 'principals'} or policy['contract'] not in (
                'engineering-history-access.v1', 'engineering-history-access.v2', 'engineering-history-access.v3'):
            raise ValueError('invalid access policy')
        if type(policy['principals']) is not list or len(policy['principals']) > 128:
            raise ValueError('bounded principal policy required')
        self.grants = {}
        for entry in policy['principals']:
            fields = {'uid', 'private_read', 'write'}
            if policy['contract'] in ('engineering-history-access.v2','engineering-history-access.v3'):
                fields |= {'category_read', 'category_write'}
            if policy['contract'] == 'engineering-history-access.v3':
                fields |= {'planning_agent','planning_organization_id','planning_teams','planning_repositories','planning_categories'}
            if type(entry) is not dict or set(entry) != fields:
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
            if policy['contract'] in ('engineering-history-access.v2','engineering-history-access.v3'):
                for name in ('category_read', 'category_write'):
                    if type(entry[name]) is not list or len(entry[name]) > 1 or any(v != 'jarvis-non-git' for v in entry[name]):
                        raise ValueError('only the initial non-Git category is supported')
                if not set(entry['category_write']) <= set(entry['category_read']):
                    raise ValueError('category write requires private read')
            if policy['contract'] == 'engineering-history-access.v3':
                repos=entry['planning_repositories'];categories=entry['planning_categories'];agent=entry['planning_agent']
                organization=entry['planning_organization_id'];teams=entry['planning_teams']
                if (agent not in (None,'jarvis','codex') or type(repos) is not list or type(categories) is not list or
                        type(teams) is not list or len(teams)>128 or len(set(teams))!=len(teams) or
                        len(set(repos))!=len(repos) or len(set(categories))!=len(categories) or
                        not set(repos)<=set(entry['private_read']) or not set(categories)<=set(entry['category_read']) or
                        bool(repos or categories)!=(agent is not None)):
                    raise ValueError('explicit scoped planning grant required')
                if agent is None:
                    if organization is not None or teams:raise ValueError('inactive planning identity required')
                else:
                    local('onboarding_reservations').canonical(organization)
                    if not teams:raise ValueError('explicit planning teams required')
                    for team in teams:local('onboarding_reservations').canonical(team)
                if agent is not None and (entry['write'] or entry['category_write'] or
                        set(repos)!=set(entry['private_read']) or set(categories)!=set(entry['category_read'])):
                    raise ValueError('planning identity must not receive broader read or general write grants')
            self.grants[uid] = copy.deepcopy(entry)
        self.store = store

    def dispatch(self, peer_uid, message):
        if type(peer_uid) is not int or peer_uid not in self.grants:
            raise ValueError('access refused')
        if type(message) is not dict or 'method' not in message:
            raise ValueError('invalid service message')
        grant = self.grants[peer_uid]
        method = message['method']
        if method in ('planning_reserve','planning_binding','planning_project_submit','planning_reporting_submit'):
            return self.planning(peer_uid,grant,message)
        if method == 'workspace_scopes' and set(message) == {'method'}:
            scopes = [{'kind': 'repository', 'id': name} for name in grant['private_read']]
            scopes += [{'kind': 'non_git', 'id': name} for name in grant.get('category_read', [])]
            registry = local('scopes').Scopes(self.store)
            with self.store.connection() as db:
                metadata = [registry.metadata(selected, registry.events(db, selected)) for selected in scopes]
            return dict(scopes=scopes, scope_metadata=metadata, authority_granted=False)
        if method == 'scope_submit' and set(message) == {'method', 'request'}:
            scopes = local('scopes'); request = scopes.validate(copy.deepcopy(message['request']))
            if not self.allowed(grant, request['scope'], write=True): raise ValueError('access refused')
            return scopes.Scopes(self.store).submit(request, peer_uid=peer_uid)
        if method == 'project_submit' and set(message) == {'method', 'request'}:
            projects = local('projects')
            request = projects.validate(copy.deepcopy(message['request']))
            if not self.allowed(grant, request['scope'], write=True):
                raise ValueError('access refused')
            return projects.Projects(self.store).submit(request, peer_uid=peer_uid)
        if method == 'project_read' and set(message) == {'method', 'scope', 'query'}:
            selected = local('projects').scope(message['scope'])
            if not self.allowed(grant, selected):
                raise ValueError('access refused')
            return local('projects').Projects(self.store).read(selected, message['query'])
        if method == 'reporting_submit' and set(message) == {'method', 'request'}:
            request = local('reporting_contract').validate(copy.deepcopy(message['request']))
            if not self.allowed(grant, request['scope'], write=True): raise ValueError('access refused')
            return local('reporting').Reporting(self.store).submit(request, peer_uid=peer_uid)
        if method=='evidence_upload' and set(message)=={'method','request'}:
            request,raw=local('evidence').validate(copy.deepcopy(message['request']))
            if not self.allowed(grant,request['scope'],write=True):raise ValueError('access refused')
            return local('evidence').Evidence(self.store).upload(request,peer_uid=peer_uid)
        if method=='evidence_read' and set(message)=={'method','scope','query'}:
            selected=local('projects').scope(message['scope'])
            if not self.allowed(grant,selected):raise ValueError('access refused')
            return local('evidence').Evidence(self.store).read(selected,message['query'])
        if method == 'submit' and set(message) == {'method', 'request'}:
            request = local('contract').validate(copy.deepcopy(message['request']))
            body = request['body']
            with self.store.connection() as db:
                rows = self.store.rows(db)
            works = {r['body']['work_item_id']: local('contract').scope(r['body'])
                     for r, _, _, _ in rows if r['operation'].startswith('work.')}
            selected = local('contract').scope(body) if request['operation'].startswith('work.') else works.get(body['work_item_id'])
            # Check both proposed and existing repository before duplicate lookup.
            # A revision cannot move a work item across an access boundary.
            existing = works.get(body['work_item_id'])
            if not self.allowed(grant, selected, write=True) or (existing is not None and not self.allowed(grant, existing, write=True)):
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
            works = {r['body']['work_item_id']: local('contract').scope(r['body'])
                     for r, _, _, _ in rows if r['operation'].startswith('work.')}
            selected = [{'submission': r, 'receipt': receipt} for r, receipt, _, _ in rows
                        if works[r['body']['work_item_id']] == {'kind': 'repository', 'id': repo}]
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
            works = {r['body']['work_item_id']: local('contract').scope(r['body'])
                     for r, _, _, _ in rows if r['operation'].startswith('work.')}
            selected = [(raw, meta) for r, _, raw, meta in rows if r['operation'] == 'document.render' and
                        r['body']['document_id'] == doc_id and
                        self.allowed(grant, works[r['body']['work_item_id']]) and
                        (version is None or r['body']['document_version'] == version)]
            if not selected: raise ValueError('document unavailable')
            raw, manifest = selected[-1]
            return dict(markdown=raw.decode('utf-8'), manifest=manifest, authority_granted=False)
        raise ValueError('unsupported service message')

    def planning(self,peer_uid,grant,message):
        agent=grant.get('planning_agent')
        if agent not in ('jarvis','codex'):raise ValueError('access refused')
        scopes=[{'kind':'repository','id':name} for name in grant['planning_repositories']]
        scopes += [{'kind':'non_git','id':name} for name in grant['planning_categories']]
        method=message['method'];reservations=local('onboarding_reservations').Reservations(self.store)
        if method=='planning_binding' and set(message)=={'method','organization_id','linear_project_id'}:
            if message['organization_id']!=grant['planning_organization_id']:raise ValueError('access refused')
            binding=local('reporting').Reporting(self.store).planning_project_binding(
                message['organization_id'],message['linear_project_id'],scopes)
            if binding is not None and binding['team_id'] not in grant['planning_teams']:raise ValueError('access refused')
            return binding
        if method=='planning_reserve' and set(message)=={'method','organization_id','linear_project_id','team_id','project_id','scope'}:
            selected=local('projects').scope(message['scope'])
            if selected not in scopes:raise ValueError('access refused')
            organization=local('onboarding_reservations').canonical(message['organization_id'])
            linear=local('onboarding_reservations').canonical(message['linear_project_id'])
            if organization!=grant['planning_organization_id'] or message['team_id'] not in grant['planning_teams']:
                raise ValueError('access refused')
            expected='prj_'+uuid.uuid5(uuid.NAMESPACE_URL,'rras-onboarding-v1:'+organization+':'+linear).hex
            if message['project_id']!=expected:raise ValueError('access refused')
            return reservations.reserve(organization,linear,message['team_id'],expected,selected)
        if method in ('planning_project_submit','planning_reporting_submit') and set(message)=={'method','request'}:
            if method=='planning_project_submit':
                request=local('projects').validate(copy.deepcopy(message['request']))
                if request['operation'] not in ('project.create','architecture.save'):
                    raise ValueError('access refused')
                if request['operation']=='architecture.save' and (request['body']['version']!=1 or request['body']['previous_sha256'] is not None):
                    raise ValueError('access refused')
                project_id=request['project_id'];selected=request['scope']
            else:
                request=local('reporting_contract').validate(copy.deepcopy(message['request']))
                if (request['operation']!='mapping.record' or request['body']['kind']!='project' or
                        request['body']['version']!=1 or request['context']['work'] is not None):raise ValueError('access refused')
                project_id=request['context']['project_id'];selected=request['scope']
            if selected not in scopes or request['source']['kind']!='agent_reported' or request['source']['namespace']!='linear_'+agent:
                raise ValueError('access refused')
            with self.store.connection() as db:
                if db.execute('PRAGMA user_version').fetchone()[0]!=6:raise ValueError('access refused')
                reserved=db.execute('SELECT organization_id,linear_project_id,team_id,scope_kind,scope_id FROM onboarding_reservations WHERE project_id=?',
                                    (project_id,)).fetchone()
            if reserved is None or tuple(reserved[3:])!=(selected['kind'],selected['id']):raise ValueError('access refused')
            if reserved[0]!=grant['planning_organization_id'] or reserved[2] not in grant['planning_teams']:
                raise ValueError('access refused')
            expected_document='doc_'+uuid.uuid5(uuid.NAMESPACE_URL,'rras-onboarding-v1:'+reserved[0]+':'+reserved[1]).hex
            if method=='planning_project_submit' and request['operation']=='architecture.save' and request['body']['document_id']!=expected_document:
                raise ValueError('access refused')
            if method=='planning_reporting_submit':
                linear=request['body']['linear']
                if (linear['organization_id'],linear['project_id'],linear['team_id'])!=tuple(reserved[:3]):raise ValueError('access refused')
                expected_mapping='map_'+uuid.uuid5(uuid.NAMESPACE_URL,'rras-onboarding-v1:'+reserved[0]+':'+reserved[1]).hex
                if (request['body']['mapping_id']!=expected_mapping or request['context']['architecture']['document_id']!=expected_document
                        or request['context']['architecture']['version']!=1):raise ValueError('access refused')
                project=local('projects').Projects(self.store).read(selected,{'view':'project','project_id':project_id})['project']
                if project['governing_version'] is not None:raise ValueError('access refused')
                return local('reporting').Reporting(self.store).submit(request,peer_uid=peer_uid)
            return local('projects').Projects(self.store).submit(request,peer_uid=peer_uid)
        raise ValueError('access refused')

    @staticmethod
    def allowed(grant, selected, *, write=False):
        if selected is None:
            return False
        if selected['kind'] == 'repository':
            return selected['id'] in grant['write' if write else 'private_read']
        return selected['id'] in grant.get('category_write' if write else 'category_read', [])
