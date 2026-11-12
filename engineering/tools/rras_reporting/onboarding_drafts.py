"""Plan-only, bounded draft creation; transport and origin verification are separate.

This module is not a listener or an authorization grant. Its caller must supply
the kernel-authenticated peer UID and a trusted verifier; never construct those
from an agent's JSON. The storage adapter must enforce global project binding
uniqueness and return authoritative absence, rather than interpreting a read
failure as absence.
"""
import hashlib
import re
import uuid
from urllib.parse import urlsplit


def identity(prefix, organization, project):
    return prefix + uuid.uuid5(uuid.NAMESPACE_URL, 'rras-onboarding-v1:' + organization + ':' + project).hex


def work_identity(prefix, organization, project, plan):
    return prefix + uuid.uuid5(uuid.NAMESPACE_URL, 'rras-onboarding-work-v1:' + organization + ':' + project + ':' + plan).hex


def identifier(value):
    if type(value) is not str:
        raise ValueError('UUID required')
    try:
        if str(uuid.UUID(value)) != value: raise ValueError('canonical UUID required')
    except (ValueError, AttributeError):
        raise ValueError('canonical UUID required') from None
    return value


def text(value, maximum, *, single_line=False):
    if type(value) is not str or not value.strip() or '\x00' in value or len(value) > maximum:
        raise ValueError('bounded nonempty text required')
    if single_line and ('\n' in value or '\r' in value): raise ValueError('single-line text required')
    return value


def selected_scope(value):
    if type(value) is not dict or set(value) != {'kind', 'id'}: raise ValueError('explicit scope required')
    kind, name = value['kind'], value['id']
    if kind == 'non_git' and name == 'jarvis-non-git': return dict(value)
    if kind == 'repository' and type(name) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', name):
        return dict(value)
    raise ValueError('explicit supported scope required')


def verified(value):
    required = {'organization_id', 'team_id', 'project_id', 'project_identifier', 'project_url', 'scope', 'source_session', 'source_actor', 'agent'}
    if type(value) is not dict or set(value) != required: raise ValueError('verified planning origin required')
    for key in ('organization_id', 'team_id', 'project_id', 'source_session', 'source_actor'): identifier(value[key])
    if value['agent'] not in ('jarvis', 'codex'): raise ValueError('named agent required')
    if (type(value['project_identifier']) is not str or
            (value['project_identifier'] != value['project_id'] and
             not re.fullmatch(r'P-[A-Z0-9]+-[0-9]+',value['project_identifier']))):
        raise ValueError('exact Linear project identifier or UUID required')
    scope = selected_scope(value['scope'])
    url = urlsplit(text(value['project_url'], 1024))
    if url.scheme != 'https' or url.netloc != 'linear.app' or url.query or url.fragment or not url.path.startswith('/'):
        raise ValueError('exact credential-free Linear project URL required')
    return dict(value, scope=scope)


def proposal(value):
    required = {'name', 'overview', 'intended_outcome', 'in_scope', 'out_of_scope', 'markdown', 'plan_ids'}
    if type(value) is not dict or set(value) != required: raise ValueError('exact draft proposal required')
    text(value['name'], 180, single_line=True)
    for key in ('overview', 'intended_outcome', 'in_scope', 'out_of_scope'): text(value[key], 16384)
    markdown = text(value['markdown'], 90000)
    plans = value['plan_ids']
    if (type(plans) is not list or not 1 <= len(plans) <= 128
            or any(type(plan) is not str for plan in plans) or len(set(plans)) != len(plans)):
        raise ValueError('distinct explicit plan IDs required')
    for plan in plans:
        if type(plan) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', plan):
            raise ValueError('bounded plan ID required')
        if not re.search(r'(?<![A-Za-z0-9_.-])' + re.escape(plan) + r'(?![A-Za-z0-9_.-])', markdown):
            raise ValueError('plan ID must appear in retained draft')
    return dict(value, plan_ids=list(plans))


class DraftWriter:
    """Create only a first unapproved draft through an injected trusted adapter.

    `verify_origin(evidence)` returns verified native human/session/project
    metadata or raises. `store` supplies authoritative `reserve`, `binding`, `project`,
    `submit_project`, and `submit_mapping` methods. Its read methods raise on
    inaccessible/uncertain state and return None only for proven absence.
    """
    def __init__(self, grants, verify_origin, store):
        if type(grants) is not dict or not grants or not callable(verify_origin): raise ValueError('explicit grants required')
        self.grants, self.verify_origin, self.store = grants, verify_origin, store

    def save(self, peer_uid, evidence, value):
        if type(peer_uid) is not int or peer_uid not in self.grants: raise ValueError('planning peer refused')
        origin = verified(self.verify_origin(evidence))
        grant = self.grants[peer_uid]
        if (type(grant) is not dict or set(grant) != {'agent', 'organization_id', 'team_id', 'scopes'}
                or grant['agent'] != origin['agent'] or grant['organization_id'] != origin['organization_id']
                or grant['team_id'] != origin['team_id'] or origin['scope'] not in grant['scopes']):
            raise ValueError('planning scope or identity refused')
        draft = proposal(value)
        org, linear = origin['organization_id'], origin['project_id']
        project_id, document_id = identity('prj_', org, linear), identity('doc_', org, linear)
        digest = hashlib.sha256(draft['markdown'].encode('utf-8')).hexdigest()
        self.store.reserve(origin, project_id)
        binding = self.store.binding(org, linear)
        if binding is not None and (binding['project_id'] != project_id or binding['scope'] != origin['scope']
                                    or binding['team_id'] != origin['team_id']):
            raise ValueError('conflicting existing project binding')
        existing = self.store.project(origin['scope'], project_id)
        if binding is not None and existing is None:
            raise ValueError('binding points to unavailable project; reconcile explicitly')
        source = {'kind': 'agent_reported', 'namespace': 'linear_'+origin['agent'], 'id': origin['source_session']}
        common = {'contract':'engineering-project.v1','project_id':project_id,'scope':origin['scope'],
                  'occurred_at':None,'source':source}
        if existing is None:
            create = dict(common, operation='project.create', client_event_key='onboard-project:'+project_id,
                expected_head=None, body={'revision':1,'name':draft['name'],'overview':draft['overview'],
                'intended_outcome':draft['intended_outcome'],'in_scope':draft['in_scope'],
                'out_of_scope':draft['out_of_scope'],'owner':None,'change_summary':'Create Linear-linked draft project.'})
            self.store.submit_project(create)
            existing = self.store.project(origin['scope'], project_id)
        if existing is None or existing['scope'] != origin['scope'] or existing['governing_version'] is not None:
            raise ValueError('project unavailable or already governed; reconcile explicitly')
        if any(existing[key] != draft[key] for key in ('name', 'overview', 'intended_outcome', 'in_scope', 'out_of_scope')):
            raise ValueError('existing project differs; reconcile explicitly')
        documents = existing['architecture']
        if not documents:
            save = dict(common, operation='architecture.save', client_event_key='onboard-draft:'+project_id,
                expected_head=existing['head'], body={'document_id':document_id,'version':1,'previous_sha256':None,
                'title':draft['name']+' architecture','change_summary':'Retain first unapproved draft.',
                'markdown':draft['markdown'],'source_reference':'linear:agent-session:'+origin['source_session']+':human:'+origin['source_actor']})
            self.store.submit_project(save)
            existing = self.store.project(origin['scope'], project_id)
            documents = existing['architecture']
        if (len(documents) != 1 or documents[0]['document_id'] != document_id or documents[0]['version'] != 1
                or documents[0]['markdown_sha256'] != digest or existing['governing_version'] is not None):
            raise ValueError('draft differs or is governed; reconcile explicitly')
        # The adapter must perform an atomic uniqueness check against all
        # admitted scopes, and use the history service's stable client key.
        if binding is None:
            self.store.submit_mapping(origin, project_id, document_id, digest)
        confirmed = self.store.binding(org, linear)
        if (confirmed is None or confirmed['project_id'] != project_id or confirmed['scope'] != origin['scope']
                or confirmed['team_id'] != origin['team_id']):
            raise ValueError('mapping outcome uncertain; reconcile before retry')
        return {'project_id':project_id,'document_id':document_id,'version':1,'markdown_sha256':digest,
                'plan_ids':draft['plan_ids'],'designation':'draft','execution_authorized':False}
