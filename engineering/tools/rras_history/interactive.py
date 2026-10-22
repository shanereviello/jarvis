"""Explicit interactive client with transactional private spool; local transport only.

No automatic session discovery, observer/human authority, hooks or action execution.
"""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sqlite3
import stat
import uuid
from datetime import datetime, timezone
from jsonschema import ValidationError

MAX_PENDING = 256
MAX_ACTIONS = 10000


def local(name):
    s = importlib.util.spec_from_file_location('interactive_' + name, Path(__file__).with_name(name + '.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


SCHEMA = '''
CREATE TABLE configuration(singleton INTEGER PRIMARY KEY CHECK(singleton=1), body BLOB NOT NULL);
CREATE TABLE context(singleton INTEGER PRIMARY KEY CHECK(singleton=1), body BLOB NOT NULL);
CREATE TABLE actions(action_key TEXT PRIMARY KEY, input_sha256 TEXT NOT NULL, body BLOB NOT NULL);
CREATE TABLE queue(sequence INTEGER PRIMARY KEY, action_key TEXT NOT NULL REFERENCES actions(action_key),
 request BLOB NOT NULL, receipt BLOB, error TEXT, disposition BLOB);
CREATE TRIGGER configuration_no_update BEFORE UPDATE ON configuration BEGIN SELECT RAISE(ABORT,'fixed client configuration'); END;
CREATE TRIGGER configuration_no_delete BEFORE DELETE ON configuration BEGIN SELECT RAISE(ABORT,'fixed client configuration'); END;
CREATE TRIGGER action_no_update BEFORE UPDATE ON actions BEGIN SELECT RAISE(ABORT,'immutable action'); END;
CREATE TRIGGER action_no_delete BEFORE DELETE ON actions BEGIN SELECT RAISE(ABORT,'immutable action'); END;
CREATE TRIGGER queue_no_delete BEFORE DELETE ON queue BEGIN SELECT RAISE(ABORT,'retain pending and delivered requests'); END;
CREATE TRIGGER queue_request_no_update BEFORE UPDATE OF request,action_key,sequence ON queue BEGIN SELECT RAISE(ABORT,'immutable request'); END;
CREATE TRIGGER disposition_no_update BEFORE UPDATE ON queue WHEN OLD.disposition IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable disposition'); END;
CREATE TRIGGER receipt_no_update BEFORE UPDATE ON queue WHEN OLD.receipt IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
PRAGMA user_version=1;
'''


class Client:
    def __init__(self, state, *, store=None, create=False):
        if os.getuid() == 0 or os.geteuid() != os.getuid():
            raise ValueError('unprivileged local client required')
        self.root = Path(state); self.path = self.root / 'client.sqlite3'
        self.guard()
        if create:
            target = Path(store)
            if not target.is_absolute() or target.resolve(strict=False) != target or target == self.root:
                raise ValueError('explicit canonical local store required')
            # Select a local transport once; do not create/adopt a history service.
            configuration = dict(contract='engineering-client.v1', store=str(target),
                                 client_id=uuid.uuid4().hex, writer_uid=os.getuid(), transport='local_caller_store')
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with self.connection(initializing=True) as db:
                db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
                db.execute('INSERT INTO configuration VALUES(1,?)', (local('contract').encoded(configuration),))
                db.commit()
            self.sync()
        else:
            if store is not None: raise ValueError('client transport is fixed at initialization')
            with self.connection() as db: self.configuration(db)

    def guard(self):
        if not self.root.is_absolute() or self.root.resolve(strict=True) != self.root:
            raise ValueError('absolute canonical client state required')
        s = self.root.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
            raise ValueError('caller-owned0700 client state required')

    def sync(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

    @contextmanager
    def connection(self, initializing=False):
        self.guard()
        for p in (self.path, *(Path(str(self.path) + s) for s in ('-wal', '-shm', '-journal'))):
            if p != self.path and not (p.exists() or p.is_symlink()): continue
            info = p.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or
                    stat.S_IMODE(info.st_mode) != 0o600):
                raise ValueError('private regular client database required')
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=10)
        try:
            db.execute('PRAGMA trusted_schema=OFF'); db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=DELETE'); db.execute('PRAGMA synchronous=FULL')
            if not initializing and db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('unsupported client version')
            yield db
        finally: db.close()

    def configuration(self, db):
        row = db.execute('SELECT body FROM configuration WHERE singleton=1').fetchone()
        if row is None: raise ValueError('client configuration unavailable')
        config = local('contract').decode(row[0])
        if config['writer_uid'] != os.getuid() or config['transport'] != 'local_caller_store':
            raise ValueError('local client identity/transport changed')
        return config

    def enqueue(self, kind, action_key, payload, *, session_id=None):
        """Durably queue an explicit action/context together; no backend call here."""
        c = local('contract')
        if kind not in ('start','attach') and session_id is not None:
            raise ValueError('session identity changes require explicit attachment')
        if not isinstance(action_key, str) or not 1 <= len(action_key) <= 128 or '\0' in action_key:
            raise ValueError('bounded stable action key required')
        intent = {'kind': kind, 'payload': payload, 'session_id': session_id}
        raw_intent = c.encoded(intent)
        if len(raw_intent) > c.MAX_REQUEST: raise ValueError('bounded client action required')
        intent = c.decode(raw_intent); payload = intent['payload']; sha = c.digest(raw_intent)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); config = self.configuration(db)
            duplicate = db.execute('SELECT input_sha256 FROM actions WHERE action_key=?', (action_key,)).fetchone()
            if duplicate:
                if duplicate[0] != sha: raise ValueError('client action key conflict')
                return {'queued_new_action': False, 'action_key': action_key, 'authority_granted': False}
            if db.execute('SELECT COUNT(*) FROM actions').fetchone()[0] >= MAX_ACTIONS:
                raise ValueError('client action capacity reached')
            active = db.execute('SELECT body FROM context WHERE singleton=1').fetchone()
            active = None if active is None else c.decode(active[0])
            requests = []
            def envelope(operation, body, head):
                key = 'cli_' + config['client_id'] + '_' + c.digest((action_key + ':' + str(len(requests))).encode())[:32]
                return c.validate(dict(contract='engineering-history.v1', operation=operation,
                    client_event_key=key, expected_head=head,
                    source={'kind':'agent_reported', 'namespace':'codex_interactive', 'id':session_id if kind in ('start','attach') else active['session_id']},
                    occurred_at=None, body=body))
            if kind == 'start':
                work = c.validate(payload)
                if work['operation'] != 'work.create' or work['body']['revision'] != 1 or work['expected_head'] is not None:
                    raise ValueError('start requires a fresh work.create request')
                # Client-local key is the retry boundary; use a per-client store key.
                work['client_event_key'] = 'cli_' + config['client_id'] + '_' + c.digest((action_key + ':work').encode())[:32]
                requests.append(c.validate(work))
                active = dict(work_item_id=work['body']['work_item_id'],
                              work_revision_sha256=c.digest(c.encoded(work['body'])), session_id=session_id)
            elif kind == 'attach':
                if not isinstance(payload, dict) or set(payload) != {'work_item_id','work_revision_sha256'}:
                    raise ValueError('explicit work/revision attachment required')
                active = {**payload, 'session_id': session_id}
            elif kind not in ('checkpoint','pause','handoff','finish'):
                raise ValueError('unsupported interactive operation')
            elif active is None:
                raise ValueError('start or attach an explicit work context first')
            if kind in ('start','attach'):
                body = {key: active[key] for key in ('work_item_id','work_revision_sha256')}
                body.update(client_namespace='codex_interactive', session_id=session_id)
                requests.append(envelope('session.attach',body,active['work_revision_sha256']))
            else:
                if not isinstance(payload, dict): raise ValueError('structured engineering note required')
                links = {key:active[key] for key in ('work_item_id','work_revision_sha256')}
                if set(links) & set(payload): raise ValueError('note cannot override active context')
                body = {**payload, **links}
                if kind in ('pause','handoff'):
                    if 'checkpoint_type' in payload: raise ValueError('fixed handoff/pause kind required')
                    body['checkpoint_type'] = kind
                operation = 'outcome.record' if kind == 'finish' else 'checkpoint.append'
                requests.append(envelope(operation,body,active['work_revision_sha256']))
            count = db.execute('SELECT COUNT(*) FROM queue WHERE receipt IS NULL AND disposition IS NULL').fetchone()[0]
            if count + len(requests) > MAX_PENDING: raise ValueError('pending client queue is full')
            db.execute('INSERT INTO actions VALUES(?,?,?)', (action_key,sha,raw_intent))
            for request in requests:
                db.execute('INSERT INTO queue(action_key,request) VALUES(?,?)',(action_key,c.encoded(request)))
            if kind in ('start','attach'):
                db.execute('INSERT INTO context VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET body=excluded.body', (c.encoded(active),))
            db.commit(); self.sync()
        return {'queued_new_action': True, 'action_key': action_key, 'authority_granted': False}

    def acknowledge(self, db, sequence, request, receipt):
        """Association checks before local receipt acceptance; separate for fault tests."""
        c = local('contract')
        expected = c.digest(c.encoded(request))
        if (receipt['request_sha256'] != expected or receipt['work_item_id'] != request['body']['work_item_id'] or
                receipt['visibility'] != 'operator_private' or receipt['authority_granted'] is not False or
                receipt['transport'] != 'local_caller_store' or receipt['writer_uid'] != os.getuid() or
                receipt['provenance'] != request['source']['kind'] or
                receipt['work_revision_sha256'] != (c.digest(c.encoded(request['body'])) if request['operation'].startswith('work.') else request['body']['work_revision_sha256'])):
            raise ValueError('store receipt differs from pending request')
        db.execute('UPDATE queue SET receipt=?,error=NULL WHERE sequence=?', (c.encoded(receipt),sequence))

    def flush(self):
        """Deliver passive intake in original order; stop at first unresolved item."""
        c = local('contract'); delivered = 0
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); config = self.configuration(db)
            for seq, raw in db.execute('SELECT sequence,request FROM queue WHERE receipt IS NULL AND disposition IS NULL ORDER BY sequence').fetchall():
                request = c.validate(c.decode(raw))
                try:
                    receipt = local('store').Store(config['store']).submit(request)['receipt']
                except (OSError, sqlite3.OperationalError):
                    db.execute('UPDATE queue SET error=? WHERE sequence=?', ('store_unavailable',seq)); break
                except (ValueError, ValidationError, sqlite3.IntegrityError):
                    db.execute('UPDATE queue SET error=? WHERE sequence=?', ('store_refused',seq)); break
                self.acknowledge(db,seq,request,receipt); delivered += 1
            db.commit(); self.sync()
        return {'delivered_now':delivered, 'status':self.status(), 'authority_granted':False}

    def abandon(self, action_key, reason):
        # Local delivery disposition only. It cannot undo a backend commit or
        # cancel/stop/approve coding; retain exact requests and any receipts.
        if not isinstance(reason, str) or not 1 <= len(reason) <= 4096 or '\0' in reason:
            raise ValueError('bounded explicit abandonment reason required')
        c = local('contract')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM actions WHERE action_key=?',(action_key,)).fetchone() is None:
                raise ValueError('unknown client action')
            rows = db.execute('SELECT sequence,disposition FROM queue WHERE action_key=? AND receipt IS NULL',(action_key,)).fetchall()
            if not rows: raise ValueError('no unresolved delivery for action')
            for sequence, existing in rows:
                if existing is not None:
                    if c.decode(existing)['reason'] != reason: raise ValueError('abandonment reason conflict')
                    continue
                disposition = dict(reason=reason,recorded_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
                    writer_uid=os.getuid(),state='delivery_abandoned_remote_outcome_not_inferred',authority_granted=False)
                db.execute('UPDATE queue SET disposition=? WHERE sequence=?',(c.encoded(disposition),sequence))
            db.commit(); self.sync()
        return self.status()

    def status(self):
        c = local('contract')
        with self.connection() as db:
            config = self.configuration(db)
            row = db.execute('SELECT body FROM context WHERE singleton=1').fetchone()
            context = None if row is None else c.decode(row[0])
            rows = db.execute('SELECT sequence,action_key,request,receipt,error,disposition FROM queue ORDER BY sequence').fetchall()
        pending = []; abandoned = []; last_receipt = None; context_confirmed = False
        for seq, key, raw, saved, error, disposition in rows:
            request = c.validate(c.decode(raw)); body = request['body']
            if saved is not None:
                receipt = c.decode(saved); last_receipt = receipt['receipt_id']
                if (context is not None and request['operation']=='session.attach' and
                        body['work_item_id']==context['work_item_id'] and body['work_revision_sha256']==context['work_revision_sha256'] and
                        body['session_id']==context['session_id']): context_confirmed = True
            elif disposition is not None:
                abandoned.append(dict(sequence=seq,action_key=key,operation=request['operation'],state='delivery_abandoned_remote_outcome_not_inferred'))
            else: pending.append(dict(sequence=seq,action_key=key,operation=request['operation'],error=error))
        return dict(transport=config['transport'], context=context, context_recorded=context_confirmed,
                    pending=pending, abandoned=abandoned, delivered=len(rows)-len(pending)-len(abandoned), last_receipt_id=last_receipt,
                    context_freshness='not_polled',
                    recording_state='pending' if pending else 'incomplete' if abandoned else 'recorded' if rows else 'empty',
                    authority_granted=False)
