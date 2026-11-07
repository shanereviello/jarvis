"""Explicit owner-only v2-to-v3 upgrade and immutable, permission-neutral scopes."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/engineering-scope-v1.schema.json'
MAX_EVENTS = 10000
DDL = (
    '''CREATE TABLE scope_submissions(
       sequence INTEGER PRIMARY KEY, principal INTEGER NOT NULL,
       scope_kind TEXT NOT NULL, scope_id TEXT NOT NULL, operation TEXT NOT NULL,
       client_key TEXT NOT NULL, request BLOB NOT NULL, request_sha256 TEXT NOT NULL,
       receipt BLOB NOT NULL, UNIQUE(principal,operation,client_key))''',
    'CREATE INDEX scope_identity ON scope_submissions(scope_kind,scope_id,sequence)',
    '''CREATE TRIGGER scope_no_update BEFORE UPDATE ON scope_submissions
       BEGIN SELECT RAISE(ABORT,'immutable scope record'); END''',
    '''CREATE TRIGGER scope_no_delete BEFORE DELETE ON scope_submissions
       BEGIN SELECT RAISE(ABORT,'immutable scope record'); END''',
    '''CREATE TABLE scope_outbox(sequence INTEGER PRIMARY KEY
       REFERENCES scope_submissions(sequence), request_sha256 TEXT NOT NULL)''',
    '''CREATE TRIGGER scope_outbox_no_update BEFORE UPDATE ON scope_outbox
       BEGIN SELECT RAISE(ABORT,'immutable scope outbox'); END''',
    '''CREATE TRIGGER scope_outbox_no_delete BEFORE DELETE ON scope_outbox
       BEGIN SELECT RAISE(ABORT,'scope delivery not implemented'); END''',
)


def local(name):
    spec = importlib.util.spec_from_file_location('scope_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def validate(value):
    c = local('contract'); value = c.decode(c.encoded(value))
    Draft202012Validator(json.loads(SCHEMA.read_text()), format_checker=FormatChecker()).validate(value)
    local('projects').scope(value['scope'])
    if value['occurred_at'] is not None:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value['occurred_at']):
            raise ValueError('exact UTC source time required')
    def text(item):
        if isinstance(item, str) and ('\0' in item or not item.strip()): raise ValueError('nonempty text required')
        if isinstance(item, dict):
            for child in item.values(): text(child)
    text(value); body = value['body']
    if any(ch in body['display_name'] for ch in '\r\n'): raise ValueError('single-line scope name required')
    url = body['repository_url']
    if url is not None:
        parts = urlsplit(url)
        if (value['scope']['kind'] != 'repository' or parts.scheme != 'https' or not parts.hostname or
                parts.username is not None or parts.password is not None or parts.query or parts.fragment or
                any(ord(ch) <= 32 or ch == '\\' for ch in url)):
            raise ValueError('credential-free HTTPS repository URL required')
    return value


class Scopes:
    def __init__(self, store):
        self.store = store; self.c = local('contract')

    def fingerprint(self, db):
        projects = local('projects').Projects(self.store)
        projects.events(db)
        base = projects.fingerprint(db)
        digest = hashlib.sha256(self.c.encoded(base))
        for table in ('project_submissions', 'project_outbox', 'project_metadata'):
            for row in db.execute('SELECT * FROM ' + table + ' ORDER BY 1'):
                digest.update(self.c.encoded([v.hex() if isinstance(v, bytes) else v for v in row]))
        return dict(contract='engineering-scope-migration.v1', from_version=base['from_version'], to_version=3,
                    expected_sha256=digest.hexdigest(), legacy_records=base['legacy_records'],
                    changes='add scope log only; preserve existing records and snapshot key', authority_granted=False)

    def migration_plan(self):
        with self.store.connection() as db:
            db.execute('BEGIN')
            if db.execute('PRAGMA user_version').fetchone()[0] not in (2, 3):
                raise ValueError('explicit project v1-to-v2 upgrade required first')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise ValueError('database integrity differs')
            return self.fingerprint(db)

    def migrate(self, expected_sha256):
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] != 2:
                raise ValueError('explicit v2 store required')
            plan = self.fingerprint(db)
            if plan['from_version'] != 2 or plan['expected_sha256'] != expected_sha256:
                raise ValueError('exact reviewed v2 migration plan required')
            for statement in DDL: db.execute(statement)
            db.execute('PRAGMA user_version=3'); db.commit()
        self.store.sync()
        return dict(plan, migrated=True, rollback='retain v3 data; use a compatible runtime')

    def events(self, db, selected=None):
        if db.execute('PRAGMA user_version').fetchone()[0] < 3: return []
        sql = 'SELECT sequence,request,request_sha256,receipt FROM scope_submissions'
        args = ()
        if selected is not None:
            local('projects').scope(selected); sql += ' WHERE scope_kind=? AND scope_id=?'
            args = (selected['kind'], selected['id'])
        result = []
        for seq, raw, digest, saved in db.execute(sql + ' ORDER BY sequence', args):
            request = validate(self.c.decode(raw)); receipt = self.c.decode(saved)
            if (len(result) >= MAX_EVENTS or self.c.encoded(request) != raw or self.c.digest(raw) != digest or
                    receipt.get('sequence') != seq or receipt.get('request_sha256') != digest or
                    receipt.get('scope') != request['scope'] or receipt.get('authority_granted') is not False or
                    receipt.get('visibility') != 'operator_private'):
                raise ValueError('scope record association differs')
            result.append((request, receipt))
        return result

    def metadata(self, selected, events, version=None):
        selected = local('projects').scope(selected)
        chosen = [(r, receipt) for r, receipt in events if r['scope'] == selected]
        if version is not None:
            if type(version) is not int or not 1 <= version <= len(chosen): raise ValueError('scope version unavailable')
            chosen = chosen[:version]
        if not chosen:
            return dict(scope=selected, recorded=False, display_name=selected['id'], description=None,
                        repository_url=None, revision=None, head=None)
        request, receipt = chosen[-1]
        return dict(request['body'], scope=selected, recorded=True, head=receipt['request_sha256'],
                    source=request['source'], occurred_at=request['occurred_at'],
                    recorded_at=receipt['recorded_at'], writer_uid=receipt['writer_uid'], peer_uid=receipt['peer_uid'])

    def submit(self, value, *, peer_uid=None):
        request = validate(value); raw = self.c.encoded(request); digest = self.c.digest(raw)
        if peer_uid is not None: local('unix').uid(peer_uid)
        principal = os.getuid() if peer_uid is None else -peer_uid
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0] != 3: raise ValueError('explicit scope migration required')
            duplicate = db.execute('SELECT request,receipt FROM scope_submissions WHERE principal=? AND operation=? AND client_key=?',
                                   (principal, request['operation'], request['client_event_key'])).fetchone()
            if duplicate:
                if duplicate[0] != raw: raise ValueError('scope idempotency conflict')
                return dict(inserted=False, receipt=self.c.decode(duplicate[1]))
            count = db.execute('SELECT COUNT(*) FROM scope_submissions').fetchone()[0]
            if count >= MAX_EVENTS: raise ValueError('scope event capacity reached')
            previous = self.metadata(request['scope'], self.events(db, request['scope']))
            if request['operation'] == 'scope.create':
                if previous['recorded'] or request['expected_head'] is not None or request['body']['revision'] != 1:
                    raise ValueError('fresh first scope revision required')
            elif (not previous['recorded'] or request['expected_head'] != previous['head'] or
                  request['body']['revision'] != previous['revision'] + 1):
                raise ValueError('exact previous scope head and next revision required')
            stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            receipt = dict(contract='engineering-scope-receipt.v1', receipt_id='rcp_' + uuid.uuid4().hex,
                           sequence=count + 1, request_sha256=digest, scope=request['scope'],
                           revision=request['body']['revision'], recorded_at=stamp, writer_uid=os.getuid(),
                           peer_uid=peer_uid, provenance=request['source']['kind'],
                           visibility='operator_private', authority_granted=False)
            db.execute('INSERT INTO scope_submissions VALUES(?,?,?,?,?,?,?,?,?)',
                       (count + 1, principal, request['scope']['kind'], request['scope']['id'], request['operation'],
                        request['client_event_key'], raw, digest, self.c.encoded(receipt)))
            db.execute('INSERT INTO scope_outbox VALUES(?,?)', (count + 1, digest)); db.commit()
        self.store.sync()
        return dict(inserted=True, receipt=receipt)
