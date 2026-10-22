"""Caller-owned local engineering store. No daemon, root journal or action API."""
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import os
import re
from pathlib import Path
import sqlite3
import stat
import uuid

MAX_RECORDS = 10000


def local(name):
    s = importlib.util.spec_from_file_location('engineering_' + name, Path(__file__).with_name(name + '.py'))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


SCHEMA = '''
CREATE TABLE submissions(
 sequence INTEGER PRIMARY KEY, principal INTEGER NOT NULL, operation TEXT NOT NULL,
 client_key TEXT NOT NULL, request BLOB NOT NULL, request_sha256 TEXT NOT NULL,
 receipt BLOB NOT NULL, document BLOB, manifest BLOB,
 UNIQUE(principal, operation, client_key));
CREATE TRIGGER no_update BEFORE UPDATE ON submissions BEGIN SELECT RAISE(ABORT,'immutable record'); END;
CREATE TRIGGER no_delete BEFORE DELETE ON submissions BEGIN SELECT RAISE(ABORT,'immutable record'); END;
CREATE TABLE outbox(sequence INTEGER PRIMARY KEY REFERENCES submissions(sequence), request_sha256 TEXT NOT NULL);
CREATE TRIGGER outbox_no_update BEFORE UPDATE ON outbox BEGIN SELECT RAISE(ABORT,'immutable pending index'); END;
CREATE TRIGGER outbox_no_delete BEFORE DELETE ON outbox BEGIN SELECT RAISE(ABORT,'delivery not implemented'); END;
PRAGMA user_version=1;
'''


class Store:
    def __init__(self, root, *, create=False):
        if os.getuid() == 0 or os.geteuid() != os.getuid():
            raise ValueError('unprivileged local caller required')
        self.root = Path(root)
        self.check_root()
        self.path = self.root / 'history.sqlite3'
        if create:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with self.connection(initializing=True) as db:
                db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
                db.commit()
            self.sync()
        else:
            with self.connection(): pass

    def check_root(self):
        if not self.root.is_absolute() or self.root.resolve(strict=True) != self.root:
            raise ValueError('absolute canonical local store required')
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('caller-owned0700 local store required')

    def sync(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

    @contextmanager
    def connection(self, initializing=False):
        self.check_root()
        info = self.path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('private regular local database required')
        for suffix in ('-wal', '-shm', '-journal'):
            p = Path(str(self.path) + suffix)
            if p.exists() or p.is_symlink():
                s = p.lstat()
                if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or
                        s.st_nlink != 1 or s.st_mode & 0o077):
                    raise ValueError('unsafe database sidecar')
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=10)
        try:
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA foreign_keys=ON')
            if not initializing and db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('unsupported local store version')
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            yield db
        finally:
            db.close()

    def rows(self, db):
        c = local('contract'); result = []
        for seq, raw, sha, receipt, document, manifest in db.execute(
                'SELECT sequence,request,request_sha256,receipt,document,manifest FROM submissions ORDER BY sequence'):
            if len(result) >= MAX_RECORDS or seq != len(result) + 1 or c.digest(raw) != sha:
                raise ValueError('local store exceeds bound or digest changed')
            request = c.validate(c.decode(raw)); saved = c.decode(receipt)
            if (saved['sequence'] != seq or saved['request_sha256'] != sha or
                    saved['visibility'] != 'operator_private' or saved['authority_granted'] is not False):
                raise ValueError('receipt association changed')
            if document is not None:
                meta = c.decode(manifest)
                if (c.digest(document) != meta['markdown_sha256'] or meta != saved['document_manifest'] or
                        meta['document_id'] != request['body'].get('document_id') or
                        meta['work_revision_sha256'] != request['body'].get('work_revision_sha256')):
                    raise ValueError('stored document changed')
            else: meta = None
            result.append((request, saved, document, meta))
        return result

    def submit(self, value):
        c = local('contract'); request = c.validate(value); raw = c.encoded(request)
        sha = c.digest(raw); operation = request['operation']; body = request['body']; principal = os.getuid()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = self.rows(db)
            duplicate = db.execute('SELECT request,receipt FROM submissions WHERE principal=? AND operation=? AND client_key=?',
                                   (principal, operation, request['client_event_key'])).fetchone()
            if duplicate:
                if duplicate[0] != raw: raise ValueError('idempotency key conflict')
                return {'inserted': False, 'receipt': c.decode(duplicate[1])}
            if len(rows) >= MAX_RECORDS: raise ValueError('local record capacity reached')
            works = [r['body'] for r, _, _, _ in rows if r['operation'].startswith('work.') and r['body']['work_item_id'] == body['work_item_id']]
            latest = works[-1] if works else None
            head = c.digest(c.encoded(latest)) if latest else None
            document = manifest = None
            if operation == 'work.create':
                if latest is not None or body['revision'] != 1 or request['expected_head'] is not None:
                    raise ValueError('fresh first work revision required')
                head = c.digest(c.encoded(body))
            elif operation == 'work.revise':
                if (latest is None or request['expected_head'] != head or
                        body['revision'] != latest['revision'] + 1 or body['repository_id'] != latest['repository_id']):
                    raise ValueError('work revision conflict')
                head = c.digest(c.encoded(body))
            else:
                if (latest is None or request['expected_head'] != head or body['work_revision_sha256'] != head):
                    raise ValueError('exact current work revision required')
                if operation == 'document.render':
                    prior = [(r['body'], meta) for r, _, _, meta in rows
                             if r['operation'] == operation and r['body']['document_id'] == body['document_id']]
                    previous = prior[-1] if prior else None
                    if previous:
                        old, meta = previous
                        if (old['work_item_id'] != body['work_item_id'] or old['document_type'] != body['document_type'] or
                                body['document_version'] != old['document_version'] + 1 or
                                body['supersedes_document_sha256'] != meta['markdown_sha256']):
                            raise ValueError('document version conflict')
                    elif body['document_version'] != 1 or body['supersedes_document_sha256'] is not None:
                        raise ValueError('first document version required')
                    document, manifest = local('documents').render(request, latest)
            receipt = dict(contract='engineering-history-receipt.v1', receipt_id='rcp_' + uuid.uuid4().hex,
                sequence=len(rows) + 1, request_sha256=sha, work_item_id=body['work_item_id'],
                work_revision_sha256=head, recorded_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                writer_uid=principal, transport='local_caller_store', provenance=request['source']['kind'],
                visibility='operator_private', authority_granted=False,
                document_manifest=manifest)
            db.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?,?)',
                       (len(rows) + 1, principal, operation, request['client_event_key'], raw, sha,
                        c.encoded(receipt), document, None if manifest is None else c.encoded(manifest)))
            self.queue(db, receipt['sequence'], sha)
            db.commit()
            self.sync()
            return {'inserted': True, 'receipt': receipt}

    def queue(self, db, sequence, sha):
        db.execute('INSERT INTO outbox VALUES(?,?)', (sequence, sha))

    def pending(self, *, offset=0, limit=100):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('bounded cursor required')
        with self.connection() as db:
            self.rows(db)
            rows = db.execute('SELECT sequence,request_sha256 FROM outbox ORDER BY sequence LIMIT ? OFFSET ?',
                              (limit + 1, offset)).fetchall()
        return dict(pending=[{'sequence': seq, 'request_sha256': sha} for seq, sha in rows[:limit]],
                    next_offset=offset + min(len(rows), limit), has_more=len(rows) > limit,
                    delivery='not_implemented', authority_granted=False)

    def history(self, work_id=None, *, offset=0, limit=100):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('bounded cursor required')
        if work_id is not None and (not isinstance(work_id, str) or not re.fullmatch('wrk_[0-9a-f]{32}', work_id)):
            raise ValueError('exact work ID required')
        with self.connection() as db:
            rows = self.rows(db)
        selected = [(r, receipt) for r, receipt, _, _ in rows if work_id is None or r['body']['work_item_id'] == work_id]
        page = selected[offset:offset + limit]
        return dict(records=[{'submission': r, 'receipt': receipt} for r, receipt in page],
                    next_offset=offset + len(page), has_more=offset + len(page) < len(selected),
                    audience='local_operator_private', authority_granted=False)

    def document(self, document_id, version=None):
        if not isinstance(document_id, str) or not re.fullmatch('doc_[0-9a-f]{32}', document_id):
            raise ValueError('exact document ID required')
        if version is not None and (type(version) is not int or version < 1):
            raise ValueError('positive document version required')
        with self.connection() as db: rows = self.rows(db)
        selected = [(raw, meta) for r, _, raw, meta in rows if r['operation'] == 'document.render' and
                    r['body']['document_id'] == document_id and
                    (version is None or r['body']['document_version'] == version)]
        if not selected: raise ValueError('document unavailable')
        return selected[-1]
