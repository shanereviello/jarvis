"""Private project workspace: explicit migration, immutable intake and scoped reads.

All writers use the history store's transaction/ownership boundary. No network,
Git inspection, automatic classification, publication or execution authority.
"""
import copy
from datetime import datetime, timezone
import difflib
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import re
import secrets
import uuid

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/engineering-project-v1.schema.json'
MAX_EVENTS = 10000
DDL = (
    'CREATE TABLE project_metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1), snapshot_key BLOB NOT NULL)',
    '''CREATE TRIGGER project_metadata_no_update BEFORE UPDATE ON project_metadata
       BEGIN SELECT RAISE(ABORT,'immutable snapshot key'); END''',
    '''CREATE TRIGGER project_metadata_no_delete BEFORE DELETE ON project_metadata
       BEGIN SELECT RAISE(ABORT,'immutable snapshot key'); END''',
    '''CREATE TABLE project_submissions(
       sequence INTEGER PRIMARY KEY, principal INTEGER NOT NULL,
       scope_kind TEXT NOT NULL, scope_id TEXT NOT NULL, project_id TEXT NOT NULL,
       operation TEXT NOT NULL, client_key TEXT NOT NULL, request BLOB NOT NULL,
       request_sha256 TEXT NOT NULL, receipt BLOB NOT NULL,
       UNIQUE(principal,operation,client_key))''',
    'CREATE INDEX project_scope ON project_submissions(scope_kind,scope_id,sequence)',
    'CREATE INDEX project_identity ON project_submissions(project_id,sequence)',
    '''CREATE TRIGGER project_no_update BEFORE UPDATE ON project_submissions
       BEGIN SELECT RAISE(ABORT,'immutable project record'); END''',
    '''CREATE TRIGGER project_no_delete BEFORE DELETE ON project_submissions
       BEGIN SELECT RAISE(ABORT,'immutable project record'); END''',
    '''CREATE TABLE project_outbox(sequence INTEGER PRIMARY KEY
       REFERENCES project_submissions(sequence), request_sha256 TEXT NOT NULL)''',
    '''CREATE TRIGGER project_outbox_no_update BEFORE UPDATE ON project_outbox
       BEGIN SELECT RAISE(ABORT,'immutable pending project index'); END''',
    '''CREATE TRIGGER project_outbox_no_delete BEFORE DELETE ON project_outbox
       BEGIN SELECT RAISE(ABORT,'project delivery not implemented'); END''',
)


def local(name):
    spec = importlib.util.spec_from_file_location('project_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scope(value):
    if (type(value) is not dict or set(value) != {'kind', 'id'} or
            value['kind'] not in ('repository', 'non_git') or type(value['id']) is not str or
            not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', value['id']) or
            (value['kind'] == 'non_git' and value['id'] != 'jarvis-non-git')):
        raise ValueError('exact organization scope required')
    return dict(value)


def validate(value):
    c = local('contract')
    value = c.decode(c.encoded(value))
    Draft202012Validator(json.loads(SCHEMA.read_text()), format_checker=FormatChecker()).validate(value)
    scope(value['scope'])
    stamp = value['occurred_at']
    if stamp is not None:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', stamp):
            raise ValueError('exact UTC source time required')
        datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    def text(item):
        if isinstance(item, str) and ('\0' in item or not item.strip()):
            raise ValueError('nonempty bounded text required')
        if isinstance(item, dict):
            for child in item.values():
                text(child)
        elif isinstance(item, list):
            for child in item:
                text(child)
    text(value)
    for key in ('name', 'title', 'owner', 'label'):
        label = value['body'].get(key)
        if isinstance(label, str) and ('\n' in label or '\r' in label):
            raise ValueError('single-line label required')
    return value


def bounded(value, maximum=10000):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('bounded integer required')
    return value


def public_document(document):
    return {key: value for key, value in document.items() if key != 'markdown'}


class Projects:
    def __init__(self, store):
        self.store = store
        self.c = local('contract')

    def fingerprint(self, db):
        """Bind an upgrade to exact existing bytes and schema, not file mtime."""
        self.store.rows(db)
        digest = hashlib.sha256()
        count = 0
        for row in db.execute('SELECT * FROM submissions ORDER BY sequence'):
            digest.update(self.c.encoded([v.hex() if isinstance(v, bytes) else v for v in row]))
            count += 1
        for row in db.execute('SELECT * FROM outbox ORDER BY sequence'):
            digest.update(self.c.encoded(list(row)))
        for row in db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name"):
            digest.update(self.c.encoded(list(row)))
        return dict(contract='engineering-project-migration.v1', from_version=db.execute('PRAGMA user_version').fetchone()[0],
                    to_version=2, legacy_records=count, expected_sha256=digest.hexdigest(),
                    changes='add project tables only; preserve existing bytes and receipts', authority_granted=False)

    def migration_plan(self):
        with self.store.connection() as db:
            db.execute('BEGIN')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('database integrity differs')
            return self.fingerprint(db)

    def migrate(self, expected_sha256):
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            plan = self.fingerprint(db)
            if plan['from_version'] != 1 or plan['expected_sha256'] != expected_sha256:
                raise ValueError('exact reviewed v1 migration plan required')
            for statement in DDL:
                db.execute(statement)
            db.execute('INSERT INTO project_metadata VALUES(1,?)', (secrets.token_bytes(32),))
            db.execute('PRAGMA user_version=2')
            db.commit()
        self.store.sync()
        return dict(plan, migrated=True, rollback='retain v2 data; old runtime must not open it')

    def events(self, db):
        if db.execute('PRAGMA user_version').fetchone()[0] == 1:
            return []
        result = []
        for seq, raw, digest, saved in db.execute(
                'SELECT sequence,request,request_sha256,receipt FROM project_submissions ORDER BY sequence'):
            request = validate(self.c.decode(raw))
            receipt = self.c.decode(saved, max_bytes=1800 * 1024)
            if (len(result) >= MAX_EVENTS or seq != len(result) + 1 or
                    self.c.encoded(request) != raw or self.c.digest(raw) != digest or
                    receipt.get('sequence') != seq or receipt.get('request_sha256') != digest or
                    receipt.get('scope') != request['scope'] or receipt.get('project_id') != request['project_id'] or
                    receipt.get('visibility') != 'operator_private' or receipt.get('authority_granted') is not False):
                raise ValueError('project record association differs')
            if request['operation'] == 'architecture.save':
                if receipt['effect']['architecture']['markdown_sha256'] != self.c.digest(request['body']['markdown'].encode('utf-8')):
                    raise ValueError('retained architecture digest differs')
            result.append((request, receipt))
        return result

    def snapshot(self, db, selected_scope, boundary):
        """A scoped MAC binds the exact pair observed in one transaction.

        It is a view-consistency token, never an access grant. Legacy v1 reads
        have only one stream and need no project-stream consistency signature.
        """
        value = dict(boundary)
        if db.execute('PRAGMA user_version').fetchone()[0] == 2:
            key = db.execute('SELECT snapshot_key FROM project_metadata WHERE singleton=1').fetchone()[0]
            value['sha256'] = hmac.new(key, self.c.encoded({'scope': selected_scope, 'boundary': boundary}), hashlib.sha256).hexdigest()
        return value

    def replay(self, events):
        projects, assignments = {}, {}
        for request, receipt in events:
            body = request['body']
            project_id = request['project_id']
            operation = request['operation']
            effect = receipt['effect']
            if operation == 'project.create':
                projects[project_id] = dict(project_id=project_id, scope=request['scope'], state='planned', archived=False,
                    architecture=[], governing_version=None, baselines=[], starting_baseline=None, current_baseline=None,
                    closeouts=[], created_at=receipt['recorded_at'], **body)
            project = projects[project_id]
            if operation == 'project.revise':
                project.update(body)
            elif operation == 'project.state':
                project['state'] = body['state']
                if 'closeout' in effect:
                    project['closeouts'].append(effect['closeout'])
            elif operation == 'project.archive':
                project['archived'] = body['archived']
            elif operation == 'architecture.save':
                project['architecture'].append(dict(effect['architecture'], markdown=body['markdown']))
            elif operation == 'architecture.designate':
                project['governing_version'] = body['version']
            elif operation == 'baseline.record':
                project['baselines'].append(effect['baseline'])
            elif operation == 'baseline.select':
                project[body['role'] + '_baseline'] = body['version']
            elif operation.startswith('membership.'):
                previous = assignments.get(body['work_item_id'])
                if previous and previous['project_id'] and previous['project_id'] != project_id:
                    old = projects[previous['project_id']]
                    old.update(head=receipt['request_sha256'], last_project_update=receipt['recorded_at'])
                assignments[body['work_item_id']] = dict(project_id=None if operation == 'membership.remove' else project_id,
                    architecture_version=None if operation == 'membership.remove' else body['architecture_version'],
                    assignment_sha256=receipt['request_sha256'], recorded_at=receipt['recorded_at'], reason=body['reason'])
            project.update(head=receipt['request_sha256'], last_project_update=receipt['recorded_at'])
        return projects, assignments

    def work_index(self, rows):
        works = {}
        for request, receipt, _, _ in rows:
            body = request['body']
            work_id = body['work_item_id']
            if request['operation'].startswith('work.'):
                works[work_id] = dict(work=body, work_revision_sha256=receipt['work_revision_sha256'],
                    scope=self.c.scope(body), latest_outcome=None, outcome_revision_sha256=None,
                    records=0, last_recorded_at=receipt['recorded_at'])
        for request, receipt, _, _ in rows:
            work = works[request['body']['work_item_id']]
            work['records'] += 1
            work['last_recorded_at'] = receipt['recorded_at']
            if request['operation'] == 'outcome.record':
                work['latest_outcome'] = request['body']['outcome']
                work['outcome_revision_sha256'] = receipt['work_revision_sha256']
        return works

    def effect(self, request, project, projects, assignments, works, sequence):
        body, op, sha = request['body'], request['operation'], self.c.digest(self.c.encoded(request))
        if op == 'project.create':
            if project is not None or request['expected_head'] is not None or body['revision'] != 1:
                raise ValueError('fresh first project revision required')
            return {}
        if project is None or project['scope'] != request['scope'] or request['expected_head'] != project['head']:
            raise ValueError('exact project scope and head required')
        if op == 'project.archive':
            if project['archived'] == body['archived']:
                raise ValueError('archive state unchanged')
            return {}
        if project['archived']:
            raise ValueError('unarchive before changing project')
        closed = project['state'] in ('completed', 'cancelled')
        if closed and not (op == 'project.state' and body['state'] == 'active'):
            raise ValueError('reopen before changing closed project')
        if op == 'project.revise':
            if body['revision'] != project['revision'] + 1:
                raise ValueError('next project revision required')
        elif op == 'project.state':
            if body['state'] == project['state']:
                raise ValueError('project state unchanged')
            if body['state'] in ('completed', 'cancelled'):
                members = []
                for work_id, assignment in assignments.items():
                    if assignment['project_id'] == request['project_id']:
                        work = works[work_id]
                        members.append(dict(work_item_id=work_id, assignment=assignment, **work))
                unresolved = {m['work_item_id'] for m in members if
                    m['latest_outcome'] != 'completed_claim' or m['outcome_revision_sha256'] != m['work_revision_sha256']}
                ids = [d['work_item_id'] for d in body['dispositions']]
                if len(ids) != len(set(ids)) or set(ids) != unresolved:
                    raise ValueError('exact disposition of unresolved work required')
                if body['state'] == 'completed':
                    if project['governing_version'] is None:
                        raise ValueError('governing architecture required for completion')
                    if request['scope']['kind'] == 'repository' and project['current_baseline'] is None and not body['baseline_omission_reason']:
                        raise ValueError('final baseline or recorded omission required')
                return {'closeout': dict(sequence=sequence, state=body['state'], summary=body['reason'],
                    project_revision=project['revision'], project_head=project['head'],
                    architecture=next((public_document(d) for d in project['architecture'] if d['version'] == project['governing_version']), None),
                    baseline=next((b for b in project['baselines'] if b['version'] == project['current_baseline']), None),
                    baseline_applicability='not_applicable' if request['scope']['kind'] == 'non_git' else 'repository',
                    baseline_omission_reason=body['baseline_omission_reason'], members=members, dispositions=body['dispositions'])}
            if body['dispositions'] or body['baseline_omission_reason'] is not None:
                raise ValueError('closeout fields only apply to closure')
        elif op == 'architecture.save':
            previous = project['architecture'][-1] if project['architecture'] else None
            if (body['version'] != (previous['version'] + 1 if previous else 1) or
                    body['previous_sha256'] != (previous['markdown_sha256'] if previous else None) or
                    (previous and previous['document_id'] != body['document_id'])):
                raise ValueError('exact next architecture version required')
            if any(d['document_id'] == body['document_id'] for p in projects.values()
                   if p['project_id'] != request['project_id'] for d in p['architecture']):
                raise ValueError('architecture identity already bound')
            return {'architecture': dict(contract='engineering-project-architecture.v1', project_id=request['project_id'],
                visibility='operator_private', document_id=body['document_id'], version=body['version'], title=body['title'],
                source_reference=body['source_reference'],
                change_summary=body['change_summary'], previous_sha256=body['previous_sha256'],
                markdown_sha256=self.c.digest(body['markdown'].encode('utf-8')), project_revision=project['revision'],
                baseline=next((b for b in project['baselines'] if b['version'] == project['current_baseline']), None),
                baseline_applicability='not_applicable' if request['scope']['kind'] == 'non_git' else 'repository')}
        elif op == 'architecture.designate':
            if not any(d['version'] == body['version'] and d['markdown_sha256'] == body['markdown_sha256'] for d in project['architecture']):
                raise ValueError('exact saved design required')
        elif op == 'baseline.record':
            if request['scope']['kind'] != 'repository':
                raise ValueError('Git baseline not applicable')
            previous = project['baselines'][-1] if project['baselines'] else None
            if (body['version'] != (previous['version'] + 1 if previous else 1) or
                    body['previous_sha256'] != (previous['baseline_sha256'] if previous else None) or
                    (previous and previous['baseline_id'] != body['baseline_id'])):
                raise ValueError('exact next Git baseline required')
            if any(b['baseline_id'] == body['baseline_id'] for p in projects.values()
                   if p['project_id'] != request['project_id'] for b in p['baselines']):
                raise ValueError('baseline identity already bound')
            return {'baseline': dict(body, repository_id=request['scope']['id'], baseline_sha256=sha,
                                     verification='reported_source_information')}
        elif op == 'baseline.select':
            if not any(b['version'] == body['version'] and b['baseline_sha256'] == body['baseline_sha256'] for b in project['baselines']):
                raise ValueError('exact saved baseline required')
            if body['role'] == 'starting' and project['starting_baseline'] is not None:
                raise ValueError('original starting baseline is retained')
        elif op.startswith('membership.'):
            work_id = body['work_item_id']
            work = works.get(work_id)
            if work is None or work['scope'] != request['scope']:
                raise ValueError('work and project scope must match')
            previous = assignments.get(work_id)
            if body['expected_assignment_sha256'] != (previous['assignment_sha256'] if previous else None):
                raise ValueError('stale work association')
            if op != 'membership.assign' and (not previous or previous['project_id'] != request['project_id']):
                raise ValueError('current project association required')
            if op != 'membership.remove':
                selected = body['architecture_version']
                if selected is not None and not any(d['version'] == selected for d in project['architecture']):
                    raise ValueError('saved architecture reference required')
                if op == 'membership.assign' and selected != project['governing_version']:
                    raise ValueError('assignment must explicitly pin current governing design')
            if op == 'membership.assign' and previous and previous['project_id']:
                old = projects[previous['project_id']]
                if old['project_id'] == request['project_id']:
                    raise ValueError('already assigned; designate design explicitly')
                if (body['expected_previous_project_head'] != old['head'] or old['archived'] or
                        old['state'] in ('completed', 'cancelled')):
                    raise ValueError('exact open previous project required')
            elif op == 'membership.assign' and body['expected_previous_project_head'] is not None:
                raise ValueError('no previous project head applies')
            return {'previous_project_id': previous['project_id'] if previous else None}
        return {}

    def submit(self, value, *, peer_uid=None):
        request = validate(value)
        raw = self.c.encoded(request)
        digest = self.c.digest(raw)
        # Same local/service idempotency namespace and UID rules as legacy intake.
        import os
        if peer_uid is not None:
            local('unix').uid(peer_uid)
        principal = os.getuid() if peer_uid is None else -peer_uid
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] != 2:
                raise ValueError('explicit project migration required')
            duplicate = db.execute('SELECT request,receipt FROM project_submissions WHERE principal=? AND operation=? AND client_key=?',
                                   (principal, request['operation'], request['client_event_key'])).fetchone()
            if duplicate:
                if duplicate[0] != raw:
                    raise ValueError('project idempotency conflict')
                return dict(inserted=False, receipt=self.c.decode(duplicate[1], max_bytes=1800 * 1024))
            events = self.events(db)
            if len(events) >= MAX_EVENTS:
                raise ValueError('project event capacity reached')
            projects, assignments = self.replay(events)
            rows = self.store.rows(db)
            works = self.work_index(rows)
            if request['operation'] == 'architecture.save' and any(
                    r['operation'] == 'document.render' and r['body']['document_id'] == request['body']['document_id']
                    for r, _, _, _ in rows):
                raise ValueError('document identity already belongs to work history')
            effect = self.effect(request, projects.get(request['project_id']), projects, assignments, works, len(events) + 1)
            if 'closeout' in effect:
                effect['closeout']['snapshot'] = self.snapshot(db, request['scope'], dict(
                    work_sequence=sum(works[r['body']['work_item_id']]['scope'] == request['scope'] for r, _, _, _ in rows),
                    project_sequence=sum(r['scope'] == request['scope'] for r, _ in events) + 1))
            stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            if 'architecture' in effect:
                effect['architecture'].update(recorded_at=stamp, occurred_at=request['occurred_at'], source=request['source'],
                                               writer_uid=os.getuid(), peer_uid=peer_uid)
            if 'baseline' in effect:
                effect['baseline'].update(recorded_at=stamp, occurred_at=request['occurred_at'], source=request['source'])
            receipt = dict(contract='engineering-project-receipt.v1', receipt_id='rcp_' + uuid.uuid4().hex,
                sequence=len(events) + 1, request_sha256=digest, project_id=request['project_id'], scope=request['scope'],
                recorded_at=stamp, writer_uid=os.getuid(), peer_uid=peer_uid, provenance=request['source']['kind'],
                visibility='operator_private', authority_granted=False, effect=effect)
            if len(self.c.encoded(receipt)) > 1800 * 1024:
                raise ValueError('project snapshot exceeds current receipt bound')
            db.execute('INSERT INTO project_submissions VALUES(?,?,?,?,?,?,?,?,?,?)',
                (len(events) + 1, principal, request['scope']['kind'], request['scope']['id'], request['project_id'],
                 request['operation'], request['client_event_key'], raw, digest, self.c.encoded(receipt)))
            db.execute('INSERT INTO project_outbox VALUES(?,?)', (len(events) + 1, digest))
            db.commit()
        self.store.sync()
        return dict(inserted=True, receipt=receipt)

    def read(self, selected_scope, query):
        selected_scope = scope(selected_scope)
        if type(query) is not dict or set(query) - {'view', 'project_id', 'work_id', 'version', 'left', 'right',
                'offset', 'limit', 'q', 'state', 'archived', 'unassigned', 'snapshot', 'closeout_sequence', 'document_id', 'architecture_version'}:
            raise ValueError('bounded project query required')
        view = query.get('view')
        if view not in ('projects', 'project', 'works', 'work', 'architecture', 'compare', 'history', 'document'):
            raise ValueError('unsupported project view')
        offset = bounded(query.get('offset', 0))
        limit = bounded(query.get('limit', 20), 50)
        if not limit:
            raise ValueError('positive page size required')
        for name in ('archived', 'unassigned'):
            if name in query and type(query[name]) is not bool:
                raise ValueError('exact boolean filter required')
        for name in ('version', 'left', 'right', 'architecture_version'):
            if name in query and not bounded(query[name]):
                raise ValueError('positive version required')
        text = query.get('q', '')
        if type(text) is not str or len(text) > 200:
            raise ValueError('bounded search required')
        with self.store.connection() as db:
            db.execute('BEGIN')
            rows, events = self.store.rows(db), self.events(db)
            scope_works = self.work_index(rows)
            rows = [row for row in rows if scope_works[row[0]['body']['work_item_id']]['scope'] == selected_scope]
            events = [(r, receipt) for r, receipt in events if r['scope'] == selected_scope]
            current = dict(work_sequence=len(rows), project_sequence=len(events))
            token = query.get('snapshot', self.snapshot(db, selected_scope, current))
            if type(token) is not dict or set(token) != set(self.snapshot(db, selected_scope, current)):
                raise ValueError('exact snapshot boundary required')
            for name in current:
                if bounded(token[name]) > current[name]:
                    raise ValueError('future snapshot refused')
            expected = self.snapshot(db, selected_scope, {name: token[name] for name in current})
            if not hmac.compare_digest(self.c.encoded(token), self.c.encoded(expected)):
                raise ValueError('snapshot boundary changed')
        rows, events = rows[:token['work_sequence']], events[:token['project_sequence']]
        # Scope filtering precedes projection, sorting, search, counts and output.
        projects, assignments = self.replay(events)
        all_works = self.work_index(rows)
        works = {k: w for k, w in all_works.items() if w['scope'] == selected_scope}
        projects = {k: p for k, p in projects.items() if p['scope'] == selected_scope}
        events = [(r, receipt) for r, receipt in events if r['scope'] == selected_scope]
        def summary(work_id, work):
            definition = work['work']
            return dict(work_item_id=work_id, title=definition['title'], objective=definition['objective'],
                revision=definition['revision'], work_revision_sha256=work['work_revision_sha256'],
                last_recorded_at=work['last_recorded_at'], latest_outcome=work['latest_outcome'],
                outcome_revision_sha256=work['outcome_revision_sha256'], records=work['records'],
                assignment=assignments.get(work_id))
        def page(values):
            return dict(items=values[offset:offset + limit], total=len(values), next_offset=offset + len(values[offset:offset + limit]),
                        has_more=offset + limit < len(values))
        def project_public(project):
            result = copy.deepcopy(project)
            result['architecture'] = [public_document(d) for d in project['architecture']]
            result['closeouts'] = [{k: v for k, v in c.items() if k != 'members'} |
                                  {'work_count': len(c['members'])} for c in project['closeouts']]
            result['designations'] = [dict(version=r['body']['version'], recorded_at=rcpt['recorded_at'])
                for r, rcpt in events if r['project_id'] == project['project_id'] and r['operation'] == 'architecture.designate']
            designated = {d['version'] for d in result['designations']}
            for document in result['architecture']:
                document['designation_status'] = ('governing' if document['version'] == project['governing_version'] else
                    'previously_governing' if document['version'] in designated else 'draft')
            members = [w for wid, w in works.items() if assignments.get(wid, {}).get('project_id') == project['project_id']]
            result.update(work_count=len(members), last_work_activity=max((w['last_recorded_at'] for w in members), default=None),
                          baseline_applicability='not_applicable' if selected_scope['kind'] == 'non_git' else 'repository')
            return result
        result = dict(scope=selected_scope, snapshot=token, authority_granted=False, audience='authorized_scope_private')
        project_id = query.get('project_id')
        project = projects.get(project_id)
        if project_id is not None and project is None:
            raise ValueError('project unavailable')
        if 'closeout_sequence' in query:
            if project is None:
                raise ValueError('exact project required')
            number = bounded(query['closeout_sequence'])
            closeout = next((c for c in project['closeouts'] if c['sequence'] == number), None)
            if closeout is None:
                raise ValueError('closeout unavailable')
            # Closeout stores exact work heads and membership; unrelated later
            # appends do not alter its immutable references or counts.
            if view == 'works':
                result.update(page([dict(m['work'], work_revision_sha256=m['work_revision_sha256'],
                    latest_outcome=m['latest_outcome'], outcome_revision_sha256=m['outcome_revision_sha256'],
                    assignment=m['assignment'], last_recorded_at=m['last_recorded_at']) for m in closeout['members']]))
                result['closeout'] = closeout
                return result
            if view == 'project':
                result['closeout'] = closeout
                result['snapshot'] = closeout['snapshot']
                events = [(r, rcpt) for r, rcpt in events if rcpt['sequence'] <= number]
                historical, assignments = self.replay(events)
                project = historical[project_id]
                works = {m['work_item_id']: m for m in closeout['members']}
            else:
                raise ValueError('closeout query supports project and work views')
        if view == 'projects':
            values = [project_public(p) for p in projects.values() if
                (query.get('archived', False) or not p['archived']) and
                (not query.get('state') or p['state'] == query['state']) and
                all(term in ' '.join((p['name'], p['overview'], p['intended_outcome'])).casefold() for term in text.casefold().split())]
            values.sort(key=lambda p: (p['last_project_update'], p['project_id']), reverse=True)
            # List pages do not carry whole project histories/documents.
            result.update(page([{k: v for k, v in p.items() if k not in ('architecture', 'baselines', 'closeouts')} |
                {'governing_architecture': next((d for d in p['architecture'] if d['version'] == p['governing_version']), None),
                 'latest_architecture': p['architecture'][-1] if p['architecture'] else None} for p in values]))
        elif view == 'works':
            values = [summary(wid, w) for wid, w in works.items() if
                (project_id is None or assignments.get(wid, {}).get('project_id') == project_id) and
                ('architecture_version' not in query or assignments.get(wid, {}).get('architecture_version') == query['architecture_version']) and
                (not query.get('unassigned', False) or not assignments.get(wid, {}).get('project_id')) and
                all(term in ' '.join((w['work']['title'], w['work']['objective'], w['work']['rationale'])).casefold() for term in text.casefold().split())]
            values.sort(key=lambda w: (w['last_recorded_at'], w['work_item_id']), reverse=True)
            result.update(page(values))
        elif view in ('work', 'document'):
            work_id = query.get('work_id')
            if work_id not in works:
                raise ValueError('work unavailable')
            selected = [(r, rcpt, raw, manifest) for r, rcpt, raw, manifest in rows if r['body']['work_item_id'] == work_id]
            if view == 'document':
                documents = [(raw, m) for _, _, raw, m in selected if m and m['document_id'] == query.get('document_id') and m['document_version'] == query.get('version')]
                if len(documents) != 1:
                    raise ValueError('document unavailable')
                raw, manifest = documents[0]
                result.update(markdown=raw.decode('utf-8'), manifest=manifest, digest_verified=True)
            else:
                result.update(work=works[work_id]['work'], work_revision_sha256=works[work_id]['work_revision_sha256'],
                    assignment=assignments.get(work_id), records=[{'submission': r, 'receipt': rcpt} for r, rcpt, _, _ in selected])
        else:
            if project is None:
                raise ValueError('exact project required')
            if view == 'project':
                result['project'] = project_public(project)
            elif view == 'history':
                values = []
                for request, receipt in reversed(events):
                    if (request['project_id'] == project_id or
                            (request['operation'] == 'membership.assign' and
                             receipt['effect'].get('previous_project_id') == project_id)):
                        body = {k: v for k, v in request['body'].items() if k != 'markdown'}
                        values.append(dict(operation=request['operation'], body=body, source=request['source'],
                            occurred_at=request['occurred_at'], recorded_at=receipt['recorded_at'],
                            sequence=receipt['sequence'], receipt_id=receipt['receipt_id']))
                result.update(page(values))
            else:
                def document(version):
                    return next((d for d in project['architecture'] if d['version'] == version), None)
                if view == 'architecture':
                    doc = document(query.get('version'))
                    if doc is None:
                        raise ValueError('architecture unavailable')
                    result.update(document=doc, digest_verified=True)
                else:
                    left, right = document(query.get('left')), document(query.get('right'))
                    if left is None or right is None:
                        raise ValueError('exact comparison versions required')
                    diff = ''.join(difflib.unified_diff(left['markdown'].splitlines(keepends=True), right['markdown'].splitlines(keepends=True),
                        fromfile='architecture-v' + str(left['version']), tofile='architecture-v' + str(right['version'])))
                    result.update(left=public_document(left), right=public_document(right), diff=diff)
        if len(self.c.encoded(result)) > 1800 * 1024:
            raise ValueError('project response bound exceeded; use smaller pages')
        return result
