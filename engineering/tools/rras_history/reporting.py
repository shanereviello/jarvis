"""Explicit v3-to-v4 reporting metadata stream; private, immutable and passive.

Artifact finalization is refused until private byte custody is implemented.
This module never contacts Linear, launches a worker or designates architecture.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import uuid

MAX_EVENTS = 10000
DDL = (
    '''CREATE TABLE reporting_submissions(sequence INTEGER PRIMARY KEY,principal INTEGER NOT NULL,
       scope_kind TEXT NOT NULL,scope_id TEXT NOT NULL,operation TEXT NOT NULL,client_key TEXT NOT NULL,
       request BLOB NOT NULL,request_sha256 TEXT NOT NULL,receipt BLOB NOT NULL,
       UNIQUE(principal,operation,client_key))''',
    'CREATE INDEX reporting_scope ON reporting_submissions(scope_kind,scope_id,sequence)',
    '''CREATE TRIGGER reporting_no_update BEFORE UPDATE ON reporting_submissions
       BEGIN SELECT RAISE(ABORT,'immutable reporting record'); END''',
    '''CREATE TRIGGER reporting_no_delete BEFORE DELETE ON reporting_submissions
       BEGIN SELECT RAISE(ABORT,'immutable reporting record'); END''',
    '''CREATE TABLE reporting_outbox(sequence INTEGER PRIMARY KEY REFERENCES reporting_submissions(sequence),
       request_sha256 TEXT NOT NULL)''',
    '''CREATE TRIGGER reporting_outbox_no_update BEFORE UPDATE ON reporting_outbox
       BEGIN SELECT RAISE(ABORT,'immutable reporting outbox'); END''',
    '''CREATE TRIGGER reporting_outbox_no_delete BEFORE DELETE ON reporting_outbox
       BEGIN SELECT RAISE(ABORT,'reporting delivery not implemented'); END''',
)


def local(name):
    spec = importlib.util.spec_from_file_location('history_reporting_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


class Reporting:
    def __init__(self, store):
        self.store, self.c = store, local('contract')

    def fingerprint(self, db):
        local('projects').Projects(self.store).events(db)
        local('scopes').Scopes(self.store).events(db)
        base = local('projects').Projects(self.store).fingerprint(db)
        digest = hashlib.sha256(self.c.encoded(base))
        for table in ('project_submissions', 'project_outbox', 'project_metadata', 'scope_submissions', 'scope_outbox'):
            for row in db.execute('SELECT * FROM ' + table + ' ORDER BY 1'):
                digest.update(self.c.encoded([v.hex() if isinstance(v, bytes) else v for v in row]))
        return dict(contract='engineering-reporting-migration.v1', from_version=base['from_version'], to_version=4,
            expected_sha256=digest.hexdigest(), legacy_records=base['legacy_records'], authority_granted=False,
            changes='add reporting metadata log only; preserve all prior rows, schema and snapshot key')

    def migration_plan(self):
        with self.store.connection() as db:
            db.execute('BEGIN')
            if db.execute('PRAGMA user_version').fetchone()[0] != 3:
                raise ValueError('exact v3 store required; no implicit chained upgrade')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise ValueError('database integrity differs')
            return self.fingerprint(db)

    def migrate(self, expected_sha256):
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] != 3: raise ValueError('explicit v3 store required')
            plan = self.fingerprint(db)
            if plan['expected_sha256'] != expected_sha256: raise ValueError('exact reviewed migration plan required')
            for statement in DDL: db.execute(statement)
            db.execute('PRAGMA user_version=4'); db.commit()
        self.store.sync()
        return dict(plan, migrated=True, rollback='retain v4 data and compatible runtime; never rewrite legacy receipts')

    def events(self, db, selected=None):
        if db.execute('PRAGMA user_version').fetchone()[0] < 4: return []
        sql, args = 'SELECT sequence,request,request_sha256,receipt FROM reporting_submissions', ()
        if selected is not None:
            local('projects').scope(selected); sql += ' WHERE scope_kind=? AND scope_id=?'
            args = (selected['kind'], selected['id'])
        result = []
        for seq, raw, digest, saved in db.execute(sql + ' ORDER BY sequence', args):
            request = local('reporting_contract').validate(self.c.decode(raw)); receipt = self.c.decode(saved)
            if (len(result) >= MAX_EVENTS or self.c.encoded(request) != raw or self.c.digest(raw) != digest or
                    (selected is not None and request['scope'] != selected) or
                    receipt.get('sequence') != seq or receipt.get('request_sha256') != digest or
                    receipt.get('scope') != request['scope'] or receipt.get('context') != request['context'] or
                    receipt.get('visibility') != 'operator_private' or receipt.get('authority_granted') is not False):
                raise ValueError('reporting receipt or record association differs')
            result.append((request, receipt))
        return result

    @staticmethod
    def entity(request):
        body = request['body']
        fields = {'mapping.record': 'mapping_id', 'attempt.record': 'attempt_id', 'handoff.record': 'handoff_id',
                  'decision.observe': 'decision_id', 'artifact.record': 'artifact_id', 'checkpoint.report': 'report_id'}
        if request['operation'] == 'artifact.associate': return ('artifact.associate', body['artifact_id'])
        key = fields.get(request['operation'])
        return (request['operation'], body[key]) if key else None

    def check_context(self, db, request):
        context = request['context']
        if context is None: return
        pm = local('projects').Projects(self.store); events = pm.events(db)
        projects, _ = pm.replay(events)
        project = projects.get(context['project_id'])
        if project is None or project['scope'] != request['scope']: raise ValueError('exact scoped project required')
        pin = context['architecture']
        if not any(d['document_id'] == pin['document_id'] and d['version'] == pin['version'] and
                   d['markdown_sha256'] == pin['markdown_sha256'] for d in project['architecture']):
            raise ValueError('exact retained architecture required')
        work = context['work']
        if work is None: return
        rows = self.store.rows(db)
        if not any(r['operation'].startswith('work.') and r['body']['work_item_id'] == work['work_item_id'] and
                   self.c.scope(r['body']) == request['scope'] and
                   self.c.digest(self.c.encoded(r['body'])) == work['work_revision_sha256'] for r, _, _, _ in rows):
            raise ValueError('exact retained scoped work revision required')
        # A late import may name an earlier association; never substitute today's
        # primary membership. The referenced assignment/designation must exist.
        if not any(r['operation'] in ('membership.assign', 'membership.designate') and
                   r['project_id'] == context['project_id'] and r['body']['work_item_id'] == work['work_item_id'] and
                   r['body']['architecture_version'] == pin['version'] and rcpt['request_sha256'] == work['assignment_sha256']
                   for r, rcpt in events):
            raise ValueError('exact retained project/work/architecture assignment required')

    def check_entity(self, request, events):
        entity = self.entity(request)
        previous = [(r, receipt) for r, receipt in events if entity is not None and self.entity(r) == entity]
        body = request['body']
        if 'version' in body:
            if previous:
                old, receipt = previous[-1]
                if old['scope'] != request['scope'] or body['version'] != old['body']['version'] + 1 or request['expected_head'] != receipt['request_sha256']:
                    raise ValueError('exact next reporting entity version required')
                if request['operation'] in ('attempt.record', 'handoff.record') and old['context'] != request['context']:
                    raise ValueError('attempt/handoff retains its original work and architecture context')
                if request['operation'] == 'attempt.record' and (
                        body['actor'] != old['body']['actor'] or old['body']['phase'] in ('failed', 'completed')):
                    raise ValueError('new executor or terminal-attempt retry requires a distinct attempt')
                if request['operation'] == 'mapping.record' and any(body[k] != old['body'][k] for k in ('kind', 'plan_id')):
                    raise ValueError('stable mapping kind and plan identity required')
                if request['operation'] == 'mapping.record':
                    old_work, new_work = old['context']['work'], request['context']['work']
                    if ((old_work or {}).get('work_item_id') != (new_work or {}).get('work_item_id') or
                            (old_work is None and old['context']['project_id'] != request['context']['project_id'])):
                        raise ValueError('mapping identity cannot be reused for unrelated work/project')
                if request['operation'] == 'handoff.record':
                    fixed = ('sender', 'recipient', 'source_session', 'issue_id', 'requested_action')
                    allowed = {'requested': {'acknowledged', 'declined'}, 'acknowledged': {'completed'}}
                    if (any(body[k] != old['body'][k] for k in fixed) or
                            body['state'] not in allowed.get(old['body']['state'], set()) or
                            (old['body']['target_session'] is not None and body['target_session'] != old['body']['target_session'])):
                        raise ValueError('exact correlated next handoff state required')
            elif body['version'] != 1 or request['expected_head'] is not None:
                raise ValueError('fresh first reporting entity required')
            elif request['operation'] == 'handoff.record' and body['state'] != 'requested':
                raise ValueError('handoff begins with an actual request')
        elif previous and request['operation'] == 'checkpoint.report':
            raise ValueError('report ID already retained; corrections append a new attributed report')
        if request['operation'] == 'mapping.record':
            latest = {}
            for r, receipt in events:
                if r['operation'] == 'mapping.record': latest[self.entity(r)] = r
            if body['kind'] != 'project':
                project_maps = [r for r in latest.values() if r['body']['kind'] == 'project' and
                                r['context']['project_id'] == request['context']['project_id']]
                if len(project_maps) != 1 or any(body['linear'][k] != project_maps[0]['body']['linear'][k]
                                                for k in ('organization_id', 'team_id', 'project_id')):
                    raise ValueError('exact retained Linear project mapping required before issue mapping')
            for key, old in latest.items():
                if key != entity and body['kind'] == 'project' and old['body']['kind'] == 'project' and (
                        old['context']['project_id'] == request['context']['project_id'] or
                        (old['body']['linear']['organization_id'], old['body']['linear']['project_id']) ==
                        (body['linear']['organization_id'], body['linear']['project_id'])):
                    raise ValueError('project already has a stable mapping identity')
                if body['kind'] != 'execution': continue
                if key == entity or old['body']['kind'] != 'execution': continue
                linear, current = old['body']['linear'], body['linear']
                if (old['context']['work']['work_item_id'] == request['context']['work']['work_item_id'] or
                        (old['context']['project_id'], old['body']['plan_id']) == (request['context']['project_id'], body['plan_id']) or
                        (linear['organization_id'], linear['issue_id']) == (current['organization_id'], current['issue_id'])):
                    raise ValueError('execution work/issue already has a stable mapping identity')
        if request['operation'] == 'artifact.record':
            raise ValueError('private evidence byte intake/finalization is not implemented; do not accept an unverified manifest')
        if request['operation'] == 'artifact.associate':
            raise ValueError('retained private artifact required; byte intake is not implemented')

    def submit(self, value, *, peer_uid=None):
        request = local('reporting_contract').validate(value); raw = self.c.encoded(request); digest = self.c.digest(raw)
        if peer_uid is not None: local('unix').uid(peer_uid)
        principal = os.getuid() if peer_uid is None else -peer_uid
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] != 4: raise ValueError('explicit reporting upgrade required')
            duplicate = db.execute('SELECT request,receipt FROM reporting_submissions WHERE principal=? AND operation=? AND client_key=?',
                                   (principal, request['operation'], request['client_event_key'])).fetchone()
            if duplicate:
                if duplicate[0] != raw: raise ValueError('reporting idempotency conflict')
                return dict(inserted=False, receipt=self.c.decode(duplicate[1]))
            events = self.events(db)
            if len(events) >= MAX_EVENTS: raise ValueError('reporting event capacity reached; retain pending delivery')
            self.check_context(db, request); self.check_entity(request, events)
            stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            receipt = dict(contract='engineering-reporting-receipt.v1', receipt_id='rcp_' + uuid.uuid4().hex,
                sequence=len(events) + 1, request_sha256=digest, scope=request['scope'], context=request['context'],
                recorded_at=stamp, writer_uid=os.getuid(), peer_uid=peer_uid,
                provenance=request['source']['kind'], visibility='operator_private', authority_granted=False)
            db.execute('INSERT INTO reporting_submissions VALUES(?,?,?,?,?,?,?,?,?)',
                (len(events) + 1, principal, request['scope']['kind'], request['scope']['id'], request['operation'],
                 request['client_event_key'], raw, digest, self.c.encoded(receipt)))
            db.execute('INSERT INTO reporting_outbox VALUES(?,?)', (len(events) + 1, digest)); db.commit()
        self.store.sync()
        return dict(inserted=True, receipt=receipt)

    def summary(self, events, *, available, project_id=None, work_id=None):
        selected = [(r, receipt) for r, receipt in events if
            (project_id is None or (r['context'] or {}).get('project_id') == project_id) and
            (work_id is None or ((r['context'] or {}).get('work') or {}).get('work_item_id') == work_id)]
        latest = {}
        for request, receipt in events:
            if self.entity(request): latest[self.entity(request)] = (request, receipt)
        latest = {key: (r, receipt) for key, (r, receipt) in latest.items() if
            (project_id is None or (r['context'] or {}).get('project_id') == project_id) and
            (work_id is None or ((r['context'] or {}).get('work') or {}).get('work_item_id') == work_id)}
        mappings = [(r, receipt) for r, receipt in latest.values() if r['operation'] == 'mapping.record']
        return dict(available=available, record_count=len(selected),
            latest_recorded_at=selected[-1][1]['recorded_at'] if selected else None,
            execution_mapping_count=sum(r['body']['kind'] == 'execution' for r, _ in mappings),
            mappings=[dict(body=r['body'], context=r['context'], source=r['source'], receipt=receipt) for r, receipt in mappings[:20]],
            reported_active_attempts=sum(r['operation'] == 'attempt.record' and r['body']['phase'] in ('started', 'progress', 'paused')
                                         for r, _ in latest.values()))
