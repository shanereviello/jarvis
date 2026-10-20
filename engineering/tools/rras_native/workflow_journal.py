"""Private durable workflow records/artifacts and a sanitized Jarvis projection.

Passive history only: never authorizes execution, runs recipes, fetches references
or contacts the ledger. CLI writers/readers require ownership of the private store.
Jarvis reads an exported projection, never the database or artifact blobs.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile

MAX_RECORDS = 10000
MAX_BATCH = 256
MAX_ARTIFACT = 4 * 1024 * 1024
IDENTITY = {'repository_registration': 'registration_id', 'work_item': 'work_item_id',
            'attempt': 'attempt_id', 'event': 'event_id'}
TERMINAL = {'attempt.finished', 'attempt.interrupted', 'cancellation.recorded'}
STAGES = {'attempt.finished': 'execution', 'validation.finished': 'validation',
          'artifact.recorded': 'artifacts', 'branch.published': 'publication',
          'pull_request.opened': 'pull_requests', 'change.merged': 'merge',
          'release.deployed': 'deployment', 'release.verified': 'verification',
          'decision.recorded': 'human_decisions'}


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def encoded(value):
    return local('workflow_records').encoded(value)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('exact SHA-256 required')
    return value


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid JSON number')))


def load_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('bounded regular JSON input required')
    return decode(path.read_bytes())


def private_root(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('absolute non-symlink store directory required')
    info = path.stat()
    if not path.is_dir() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('caller-owned 0700 directory required')
    return path


def _commit(connection):
    connection.commit()


SCHEMA = '''
CREATE TABLE meta(version INTEGER NOT NULL CHECK(version=1));
INSERT INTO meta VALUES(1);
CREATE TABLE records(
 digest TEXT PRIMARY KEY, kind TEXT NOT NULL, identity TEXT NOT NULL, revision INTEGER NOT NULL,
 body BLOB NOT NULL, ingest_kind TEXT NOT NULL, received_at TEXT NOT NULL, writer_uid INTEGER NOT NULL,
 UNIQUE(kind,identity,revision));
CREATE TABLE artifacts(digest TEXT PRIMARY KEY, body BLOB NOT NULL);
CREATE TABLE outbox(record_digest TEXT PRIMARY KEY REFERENCES records(digest));
CREATE TRIGGER records_no_update BEFORE UPDATE ON records BEGIN SELECT RAISE(ABORT,'immutable record'); END;
CREATE TRIGGER records_no_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT,'immutable record'); END;
CREATE TRIGGER artifacts_no_update BEFORE UPDATE ON artifacts BEGIN SELECT RAISE(ABORT,'immutable artifact'); END;
CREATE TRIGGER artifacts_no_delete BEFORE DELETE ON artifacts BEGIN SELECT RAISE(ABORT,'immutable artifact'); END;
'''


class Journal:
    def __init__(self, root, *, create=False):
        self.root = private_root(root)
        self.path = self.root / 'workflow.sqlite3'
        if create:
            # Exclusive creation with private mode before SQLite opens the file.
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            try:
                with self.connection(initializing=True) as db:
                    db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
                    _commit(db)
                directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except BaseException:
                # Preserve incomplete initialization for explicit inspection.
                raise
        with self.connection() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('journal integrity check failed')

    @contextmanager
    def connection(self, *, initializing=False):
        private_root(self.root)
        info = self.path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('caller-owned private regular database required')
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            if not initializing and db.execute('SELECT version FROM meta').fetchall() != [(1,)]:
                raise ValueError('unsupported journal version')
            yield db
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _rows(self, db):
        rows = db.execute('SELECT digest,body,ingest_kind,received_at,writer_uid FROM records ORDER BY rowid').fetchall()
        if len(rows) > MAX_RECORDS:
            raise ValueError('journal exceeds current supported record limit')
        result = []
        for sha, raw, origin, received, uid in rows:
            record = decode(raw)
            if digest(raw) != sha or encoded(record) != raw:
                raise ValueError('stored record digest mismatch')
            result.append((record, {'digest': sha, 'ingest_kind': origin,
                                   'received_at': received, 'writer_uid': uid}))
        return result

    def append(self, records, artifacts=None, *, interactive_import=False, transition=None):
        if not isinstance(records, list) or not (0 < len(records) <= MAX_BATCH or (not records and transition is not None)):
            raise ValueError('bounded nonempty record batch required')
        # Copy inputs before validation; caller mutations cannot change committed bytes.
        records = decode(encoded(records))
        blobs = dict(artifacts or {})
        if len(blobs) > 64 or sum(len(raw) for raw in blobs.values()) > 16 * 1024 * 1024:
            raise ValueError('artifact batch too large')
        for sha, raw in blobs.items():
            exact_digest(sha)
            if not isinstance(raw, bytes) or len(raw) > MAX_ARTIFACT or digest(raw) != sha:
                raise ValueError('artifact digest or size mismatch')
        validator = local('workflow_records')
        for record in records:
            validator.validate_record(record)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = self._rows(db)
            known = {meta['digest']: row for row, meta in existing}
            if transition is not None:
                if interactive_import:
                    raise ValueError('observed transitions cannot be interactive imports')
                event, attempt = decode(encoded(transition))
                now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                if attempt is not None:
                    matches = [r for r in known.values() if r['kind'] == 'attempt' and r['attempt_id'] == attempt['attempt_id']]
                    if matches:
                        saved = matches[0]
                        if any(saved.get(k) != v for k, v in attempt.items()):
                            raise ValueError('attempt association changed')
                        attempt = saved
                    else:
                        number = max((r['attempt_number'] for r in known.values() if r['kind'] == 'attempt' and r['work_item_id'] == attempt['work_item_id']), default=0) + 1
                        attempt.update(schema_version=1, kind='attempt', attempt_number=number, created_at=now)
                    records.append(attempt)
                matches = [r for r in known.values() if r['kind'] == 'event' and r['event_id'] == event['event_id']]
                if matches:
                    saved = matches[0]
                    if any(saved.get(k) != v for k, v in event.items()):
                        raise ValueError('transition identity conflicts')
                    event = saved
                else:
                    stream = sorted([r for r in known.values() if r['kind'] == 'event' and r['work_item_id'] == event['work_item_id']], key=lambda r: r['sequence'])
                    event.update(schema_version=1, kind='event', occurred_at=now, recorded_at=now,
                        sequence=stream[-1]['sequence'] + 1 if stream else 1,
                        previous_event_sha256=digest(encoded(stream[-1])) if stream else None)
                records.append(event)
            if len(records) > MAX_BATCH:
                raise ValueError('transition exceeds record batch limit')
            incoming = {digest(encoded(row)): row for row in records}
            if len(incoming) != len(records):
                raise ValueError('duplicate records within batch')
            additions = {sha: row for sha, row in incoming.items() if sha not in known}
            combined = {**known, **additions}
            if len(combined) > MAX_RECORDS:
                raise ValueError('journal exceeds current supported record limit')
            validator.validate_history(combined.values())
            if interactive_import:
                works = {sha: row for sha, row in combined.items() if row['kind'] == 'work_item'}
                for row in records:
                    if row['provenance']['kind'] not in {'imported', 'human_reported'}:
                        raise ValueError('interactive imports cannot claim observed provenance')
                    if row['kind'] == 'work_item' and row['mode'] != 'interactive':
                        raise ValueError('interactive work required')
                    if row['kind'] == 'attempt' and (row['mode'] != 'interactive' or row['executor'] != 'interactive_session'):
                        raise ValueError('interactive attempt required')
                    if row['kind'] == 'event' and works[row['work_item_sha256']]['mode'] != 'interactive':
                        raise ValueError('interactive event required')
            refs = {ref['sha256'] for row in records for ref in row.get('artifacts', [])}
            if set(blobs) - refs:
                raise ValueError('unreferenced artifact payload')
            for sha in refs:
                old = db.execute('SELECT body FROM artifacts WHERE digest=?', (sha,)).fetchone()
                if old is not None and digest(old[0]) != sha:
                    raise ValueError('stored artifact digest mismatch')
                if old is None and sha not in blobs:
                    raise ValueError('local artifact bytes required')
            for sha, raw in blobs.items():
                old = db.execute('SELECT body FROM artifacts WHERE digest=?', (sha,)).fetchone()
                if old is not None and old[0] != raw:
                    raise ValueError('artifact conflict')
                db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?)', (sha, raw))
            received = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            for sha, row in additions.items():
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?)',
                           (sha, row['kind'], row[IDENTITY[row['kind']]], row.get('revision', 0),
                            encoded(row), 'interactive_import' if interactive_import else 'operator_record', received, os.getuid()))
                db.execute('INSERT INTO outbox VALUES(?)', (sha,))
            _commit(db)
        return {'inserted': len(additions), 'already_present': len(records) - len(additions),
                'index_delivery': 'queued_only', 'execution_authorized': False}

    def records(self):
        with self.connection() as db:
            db.execute('BEGIN')
            rows = self._rows(db)
            local('workflow_records').validate_history(row for row, _ in rows)
            return rows

    def history(self, work_id, *, after=0, limit=100, audience='operator'):
        if not isinstance(work_id, str) or not re.fullmatch('wrk_[0-9a-f]{32}', work_id):
            raise ValueError('exact work identity required')
        bounds(after, limit)
        audience_check(audience)
        rows = self.records()
        events = sorted(((r, meta) for r, meta in rows if r['kind'] == 'event' and r['work_item_id'] == work_id),
                        key=lambda pair: pair[0]['sequence'])
        works = [r for r, _ in rows if r['kind'] == 'work_item' and r['work_item_id'] == work_id]
        if not works:
            raise ValueError('unknown work identity')
        work = max(works, key=lambda r: r['revision'])
        selected = [(r, meta) for r, meta in events if r['sequence'] > after][:limit]
        return {'work_item_id': work_id, 'repository_id': work['repository_id'],
                'mode': work['mode'], 'revision': work['revision'], 'events': [event_view(r, meta, audience) for r, meta in selected],
                'next_after': selected[-1][0]['sequence'] if selected else after,
                'has_more': len([r for r, _ in events if r['sequence'] > after]) > len(selected)}

    def status(self, *, repository_id=None, offset=0, limit=100, audience='operator'):
        bounds(offset, limit)
        audience_check(audience)
        if repository_id is not None:
            local('activity').identifier(repository_id)
        rows = self.records()
        latest = {}
        for row, _ in rows:
            if row['kind'] == 'work_item' and (repository_id is None or row['repository_id'] == repository_id):
                old = latest.get(row['work_item_id'])
                if old is None or row['revision'] > old['revision']:
                    latest[row['work_item_id']] = row
        works = sorted(latest.values(), key=lambda r: (r['repository_id'], r['work_item_id']))
        answer = []
        for work in works[offset:offset + limit]:
            work_id = work['work_item_id']
            events = sorted([r for r, _ in rows if r['kind'] == 'event' and r['work_item_id'] == work_id], key=lambda r: r['sequence'])
            corrected = {r['corrects_event_id'] for r in events if r['corrects_event_id'] is not None}
            attempts = []
            for row, _ in rows:
                if row['kind'] != 'attempt' or row['work_item_id'] != work_id:
                    continue
                claims = [r for r in events if r['attempt_id'] == row['attempt_id'] and r['event_type'] in TERMINAL and r['event_id'] not in corrected]
                terminal = claims[-1] if claims else None
                attempts.append({'attempt_id': row['attempt_id'], 'attempt_number': row['attempt_number'],
                                 'state': 'terminal_claim_recorded' if terminal else 'unfinished',
                                 'terminal_claim': None if terminal is None else {'event_type': terminal['event_type'], 'outcome': terminal['outcome'],
                                     'provenance': terminal['provenance']['kind']}})
            entry = {'repository_id': work['repository_id'], 'work_item_id': work_id,
                     'revision': work['revision'], 'mode': work['mode'],
                     'work_item_sha256': digest(encoded(work)), 'event_count': len(events),
                     'attempts': sorted(attempts, key=lambda r: r['attempt_number']),
                     'last_sequence': events[-1]['sequence'] if events else 0,
                     'release_status': 'not_inferred'}
            if audience == 'operator':
                entry['objective'] = work['objective']
            answer.append(entry)
        return {'work_items': answer, 'next_offset': offset + len(answer),
                'has_more': offset + len(answer) < len(works)}

    def summary(self, work_id, *, audience='operator', after=0, limit=100):
        view = self.history(work_id, after=after, limit=limit, audience=audience)
        # Preserve all facts and corrections; do not turn publication or reported
        # deployment into an unqualified release claim.
        return {'work_item_id': work_id, 'repository_id': view['repository_id'],
                'mode': view['mode'], 'revision': view['revision'], 'release_status': 'not_inferred',
                'facts': [dict(event, stage=STAGES.get(event['event_type'], 'work_journal')) for event in view['events']],
                'next_after': view['next_after'], 'has_more': view['has_more']}

    def artifact(self, sha):
        exact_digest(sha)
        with self.connection() as db:
            row = db.execute('SELECT body FROM artifacts WHERE digest=?', (sha,)).fetchone()
            if row is None or digest(row[0]) != sha:
                raise ValueError('missing or inconsistent artifact')
            return row[0]

    def outbox(self, *, offset=0, limit=100):
        bounds(offset, limit)
        with self.connection() as db:
            rows = db.execute('SELECT record_digest FROM outbox ORDER BY rowid LIMIT ? OFFSET ?', (limit + 1, offset)).fetchall()
            return {'pending': [r[0] for r in rows[:limit]], 'next_offset': offset + min(len(rows), limit),
                    'has_more': len(rows) > limit, 'delivery': 'not_implemented'}

    def publish_jarvis(self, output, work_id, *, after=0, limit=100):
        # One snapshot for both views, so publication cannot mix concurrent commits.
        # history has all relevant event metadata; work identity itself is the query.
        view = {'schema_version': 1, 'audience': 'jarvis',
                'summary': self.summary(work_id, audience='jarvis', after=after, limit=limit)}
        raw = encoded(view)
        output = Path(output)
        private_root(output.parent)
        if output.name in {'workflow.sqlite3', 'workflow.sqlite3-journal'} or self.root in output.parents:
            raise ValueError('publish outside the private database directory')
        if output.is_symlink() or (output.exists() and not output.is_file()):
            raise ValueError('projection must be a regular file')
        if output.exists():
            info = output.stat()
            if info.st_uid != os.getuid() or info.st_nlink != 1:
                raise ValueError('caller-owned projection required')
            read_projection(output)  # Never replace an unrelated file.
        fd, temporary = tempfile.mkstemp(prefix='.projection-', dir=output.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o440)
            os.replace(temporary, output)
            directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {'projection_sha256': digest(raw), 'events': len(view['summary']['facts']),
                'has_more': view['summary']['has_more']}


def bounds(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('bounded pagination required')


def audience_check(audience):
    if audience not in {'operator', 'jarvis'}:
        raise ValueError('unknown audience')


def event_view(record, meta, audience):
    audience_check(audience)
    result = {key: record[key] for key in ('event_id', 'sequence', 'event_type', 'outcome',
              'occurred_at', 'recorded_at', 'attempt_id', 'corrects_event_id', 'decision_subject')}
    result.update(record_sha256=meta['digest'], provenance=record['provenance']['kind'],
                  ingestion=meta['ingest_kind'])
    result['artifacts'] = [{k: ref[k] for k in ('artifact_id', 'sha256', 'purpose')}
                           for ref in record['artifacts']
                           if audience == 'operator' or ref['visibility'] in {'operator_and_jarvis', 'public_review'}]
    if audience == 'operator':
        result.update(summary=record['summary'], references=record['references'], actor=record['actor'])
    return result


def read_projection(path):
    """Read only an explicitly exported allowlisted view; never open a journal."""
    view = load_json(path)
    if (not isinstance(view, dict) or set(view) != {'schema_version', 'audience', 'summary'} or
            type(view['schema_version']) is not int or view['schema_version'] != 1 or view['audience'] != 'jarvis'):
        raise ValueError('invalid projection envelope')
    summary = view['summary']
    if (not isinstance(summary, dict) or set(summary) != {'work_item_id', 'repository_id', 'mode', 'revision', 'release_status', 'facts', 'next_after', 'has_more'} or
            not re.fullmatch('wrk_[0-9a-f]{32}', summary['work_item_id']) or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', summary['repository_id']) or
            summary['mode'] not in {'interactive', 'approval_driven', 'delegated'} or
            type(summary['revision']) is not int or summary['revision'] < 1 or summary['release_status'] != 'not_inferred' or
            type(summary['next_after']) is not int or summary['next_after'] < 0 or type(summary['has_more']) is not bool or
            not isinstance(summary['facts'], list) or len(summary['facts']) > 100):
        raise ValueError('invalid projection summary')
    schema = json.loads(local('workflow_records').SCHEMA.read_text())
    event_properties = schema['$defs']['event']['properties']
    keys = {'event_id', 'sequence', 'event_type', 'outcome', 'occurred_at', 'recorded_at',
            'attempt_id', 'corrects_event_id', 'decision_subject', 'record_sha256', 'provenance',
            'ingestion', 'artifacts', 'stage'}
    previous = 0
    for fact in summary['facts']:
        if not isinstance(fact, dict) or set(fact) != keys:
            raise ValueError('invalid projection fact fields')
        if (not re.fullmatch('evt_[0-9a-f]{32}', fact['event_id']) or
                type(fact['sequence']) is not int or fact['sequence'] <= previous or
                fact['event_type'] not in event_properties['event_type']['enum'] or
                fact['outcome'] not in event_properties['outcome']['enum'] or
                fact['provenance'] not in {'observed', 'imported', 'human_reported'} or
                fact['ingestion'] not in {'operator_record', 'interactive_import'} or
                fact['stage'] != STAGES.get(fact['event_type'], 'work_journal') or
                not isinstance(fact['artifacts'], list) or len(fact['artifacts']) > 64):
            raise ValueError('invalid projection fact')
        exact_digest(fact['record_sha256'])
        for field, pattern in (('attempt_id', 'att_[0-9a-f]{32}'), ('corrects_event_id', 'evt_[0-9a-f]{32}')):
            if fact[field] is not None and not re.fullmatch(pattern, fact[field]):
                raise ValueError('invalid projection identity')
        subjects = {'scope_change', 'deliverable_acceptance', 'merge', 'deployment', 'other'}
        if fact['decision_subject'] is not None and fact['decision_subject'] not in subjects:
            raise ValueError('invalid decision subject')
        for field in ('occurred_at', 'recorded_at'):
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?Z', fact[field]):
                raise ValueError('invalid projection timestamp')
            datetime.fromisoformat(fact[field][:-1] + '+00:00')
        for artifact in fact['artifacts']:
            if (not isinstance(artifact, dict) or set(artifact) != {'artifact_id', 'sha256', 'purpose'} or
                    not re.fullmatch('art_[0-9a-f]{32}', artifact['artifact_id']) or
                    artifact['purpose'] not in {'request', 'review', 'approval', 'execution', 'validation', 'diff', 'publication', 'deployment', 'other'}):
                raise ValueError('invalid projection artifact')
            exact_digest(artifact['sha256'])
        previous = fact['sequence']
    if summary['facts'] and summary['next_after'] != previous:
        raise ValueError('projection cursor mismatch')
    return view


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('--store', required=True)
    append = sub.add_parser('append')
    append.add_argument('--store', required=True)
    append.add_argument('--records', required=True)
    append.add_argument('--artifact', action='append', default=[], metavar='SHA256=FILE')
    imported = sub.add_parser('import-interactive')
    imported.add_argument('--store', required=True)
    imported.add_argument('--records', required=True)
    imported.add_argument('--artifact', action='append', default=[], metavar='SHA256=FILE')
    for command in ('history', 'summary', 'publish-jarvis'):
        parser = sub.add_parser(command)
        parser.add_argument('--store', required=True)
        parser.add_argument('--work-id', required=True)
        parser.add_argument('--after', type=int, default=0)
        parser.add_argument('--limit', type=int, default=100)
        if command == 'publish-jarvis':
            parser.add_argument('--output', required=True)
    status = sub.add_parser('status')
    status.add_argument('--store', required=True)
    status.add_argument('--repository-id')
    for command, parser in (('status', status), ('outbox', sub.add_parser('outbox'))):
        if command == 'outbox':
            parser.add_argument('--store', required=True)
        parser.add_argument('--offset', type=int, default=0)
        parser.add_argument('--limit', type=int, default=100)
    artifact = sub.add_parser('artifact')
    artifact.add_argument('--store', required=True)
    artifact.add_argument('--sha256', required=True)
    artifact.add_argument('--output', required=True)
    read = sub.add_parser('jarvis-read')
    read.add_argument('--view', required=True)
    args = p.parse_args(argv)
    try:
        if args.command == 'jarvis-read':
            result = read_projection(args.view)
        else:
            journal = Journal(args.store, create=args.command == 'init')
            if args.command == 'init':
                result = {'initialized': True, 'execution_authorized': False}
            elif args.command in {'append', 'import-interactive'}:
                blobs = {}
                for value in getattr(args, 'artifact', []):
                    sha, name = value.split('=', 1)
                    path = Path(name)
                    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARTIFACT:
                        raise ValueError('bounded regular artifact required')
                    if sha in blobs:
                        raise ValueError('duplicate artifact argument')
                    blobs[sha] = path.read_bytes()
                result = journal.append(load_json(args.records), blobs, interactive_import=args.command == 'import-interactive')
            elif args.command == 'status':
                result = journal.status(repository_id=args.repository_id, offset=args.offset, limit=args.limit)
            elif args.command == 'outbox':
                result = journal.outbox(offset=args.offset, limit=args.limit)
            elif args.command == 'artifact':
                output = Path(args.output)
                private_root(output.parent)
                if output.parent == journal.root:
                    raise ValueError('export outside the private database directory')
                local('activity').absent(output, journal.artifact(args.sha256))
                result = {'sha256': args.sha256, 'written': True}
            elif args.command == 'publish-jarvis':
                result = journal.publish_jarvis(args.output, args.work_id, after=args.after, limit=args.limit)
            else:
                result = getattr(journal, args.command)(args.work_id, after=args.after, limit=args.limit)
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
        p.exit(1, 'Journal command refused; preserve the store and inspect input or permissions.\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
