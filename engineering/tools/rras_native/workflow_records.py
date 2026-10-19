"""Validate passive workflow records/histories; no operational writes or authority.

Existing admission, root approval, launch and publication contracts are unchanged.
Hashing is deterministic JSON for these records, not a cross-language JCS claim.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

SCHEMA = Path(__file__).resolve().parents[2] / 'contracts/workflow-v1.schema.json'


def encoded(record):
    return (json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


def record_digest(record):
    return hashlib.sha256(encoded(record)).hexdigest()


def _path(value, absolute=False, root=False):
    p = PurePosixPath(value)
    if ('\x00' in value or '\\' in value or p.is_absolute() != absolute or str(p) != value
            or '..' in p.parts or (value == '.' and not root)):
        raise ValueError('normalized path required')


def _remote(value):
    if value is None:
        return
    if re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+:[A-Za-z0-9_./-]+', value):
        if '..' in value.split(':', 1)[1].split('/'):
            raise ValueError('unsafe remote path')
        return
    p = urlsplit(value)
    if (p.scheme not in {'https', 'ssh'} or not p.hostname or p.password or p.query
            or p.fragment or (p.scheme == 'https' and p.username)
            or (p.scheme == 'ssh' and p.username is not None and not re.fullmatch(r'[A-Za-z0-9_.-]+', p.username))
            or not p.path or any(c.isspace() for c in value)):
        raise ValueError('public credential-free Git remote required')


def validate_record(record):
    """Check structure/semantics only; does not authenticate a claimed actor."""
    from jsonschema import Draft202012Validator, FormatChecker
    schema = json.loads(SCHEMA.read_text())
    errors = Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record)
    if next(errors, None) is not None:
        # Never echo values or schema error payloads: records can contain private text.
        raise ValueError('invalid workflow record')
    # jsonschema's date-time checker is optional in minimal environments. Keep
    # UTC/calendar validation effective without extra format-checker packages.
    for key in ('created_at', 'occurred_at', 'recorded_at'):
        if key in record:
            value = record[key]
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,9})?Z', value):
                raise ValueError('UTC timestamp required')
            try:
                datetime.fromisoformat(value[:-1] + '+00:00')
            except ValueError:
                raise ValueError('valid UTC calendar timestamp required') from None
    def contains_nul(value):
        if isinstance(value, str):
            return chr(0) in value
        if isinstance(value, dict):
            return any(contains_nul(k) or contains_nul(v) for k, v in value.items())
        if isinstance(value, list):
            return any(contains_nul(v) for v in value)
        return False

    raw = encoded(record)
    if len(raw) > 128 * 1024 or contains_nul(record):
        raise ValueError('oversized or NUL-bearing workflow record')
    if 'revision' in record:
        if (record['revision'] == 1) != (record['supersedes_sha256'] is None):
            raise ValueError('revision parent required except for first revision')
    kind = record['kind']
    if kind == 'repository_registration':
        _path(record['source']['canonical_path'], absolute=True)
        _remote(record['source']['remote']); _remote(record['publication']['remote'])
        for key in ('allowed_roots', 'denied_roots'):
            for path in record['path_policy'][key]:
                _path(path, root=True)
        if '.git' not in record['path_policy']['denied_roots']:
            raise ValueError('Git metadata must be excluded')
        ids = [r['validation_id'] for r in record['validation_recipes']]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate validation recipe')
        for recipe in record['validation_recipes']:
            _path(recipe['argv'][0], absolute=True)
        if not re.fullmatch(r'codex/[A-Za-z0-9_/-]*', record['publication']['review_branch_prefix']):
            raise ValueError('dedicated review branch prefix required')
    if kind == 'work_item':
        for path in record['requested_paths']:
            _path(path)
    if kind == 'attempt':
        for key, namespace in (('authorization_reference', 'authorization'), ('delegation_reference', 'delegation')):
            value = record[key]
            if value is not None and value['namespace'] != namespace:
                raise ValueError('authorization/delegation reference namespace mismatch')
    if kind == 'event':
        if (record['event_type'] == 'decision.recorded') != (record['decision_subject'] is not None):
            raise ValueError('decision subject required only for a decision event')
        if (record['sequence'] == 1) != (record['previous_event_sha256'] is None):
            raise ValueError('event parent required except at stream start')
        if record['corrects_event_id'] == record['event_id']:
            raise ValueError('event cannot correct itself')
    return record


def validate_history(records):
    """Check a COMPLETE history, not a filtered query or trusted authorization.

    Input order is irrelevant. Event sequence is per work item across all attempts.
    Hash links detect inconsistency, not authenticity or external history truncation.
    """
    rows = list(records)
    by_digest, identities, artifacts = {}, set(), {}
    identity_fields = {'repository_registration': 'registration_id', 'work_item': 'work_item_id',
                       'attempt': 'attempt_id', 'event': 'event_id'}
    for r in rows:
        validate_record(r)
        identity = (r['kind'], r[identity_fields[r['kind']]], r.get('revision'))
        if identity in identities:
            raise ValueError('duplicate record identity/revision')
        identities.add(identity)
        by_digest[record_digest(r)] = r
        for artifact in r.get('artifacts', []):
            previous = artifacts.setdefault(artifact['artifact_id'], artifact)
            if previous != artifact:
                raise ValueError('artifact identity metadata changed')

    def linked(digest, kind):
        r = by_digest.get(digest)
        if r is None or r['kind'] != kind:
            raise ValueError('missing or mismatched linked record')
        return r

    attempts = {r['attempt_id']: r for r in rows if r['kind'] == 'attempt'}
    attempt_numbers, streams = set(), {}
    for r in rows:
        kind = r['kind']
        if kind in {'repository_registration', 'work_item'} and r['revision'] > 1:
            parent = linked(r['supersedes_sha256'], kind)
            field = identity_fields[kind]
            if parent[field] != r[field] or parent['revision'] + 1 != r['revision']:
                raise ValueError('revision chain mismatch')
            if parent['repository_id'] != r['repository_id']:
                raise ValueError('repository identity cannot change in a revision')
        if kind in {'work_item', 'attempt'}:
            repo = linked(r['registration_sha256'], 'repository_registration')
            if repo['repository_id'] != r['repository_id']:
                raise ValueError('repository registration mismatch')
            baseline = r['baseline']
            if baseline and len(baseline['commit']) != (40 if repo['source']['object_format'] == 'sha1' else 64):
                raise ValueError('Git object format mismatch')
            if kind == 'work_item' and r['validation_id'] is not None:
                if r['validation_id'] not in {v['validation_id'] for v in repo['validation_recipes']}:
                    raise ValueError('unknown validation recipe reference')
        if kind in {'attempt', 'event'}:
            work = linked(r['work_item_sha256'], 'work_item')
            if work['work_item_id'] != r['work_item_id']:
                raise ValueError('work item identity mismatch')
            if kind == 'attempt':
                if any(r[k] != work[k] for k in ('repository_id', 'registration_sha256', 'mode')):
                    raise ValueError('attempt snapshot mismatch')
                if work['baseline'] is not None and r['baseline'] != work['baseline']:
                    raise ValueError('attempt baseline snapshot mismatch')
                number = (r['work_item_id'], r['attempt_number'])
                if number in attempt_numbers:
                    raise ValueError('duplicate attempt number')
                attempt_numbers.add(number)
            else:
                if r['attempt_id'] is not None:
                    attempt = attempts.get(r['attempt_id'])
                    if attempt is None or attempt['work_item_sha256'] != r['work_item_sha256']:
                        raise ValueError('event attempt mismatch')
                streams.setdefault(r['work_item_id'], []).append(r)
    for stream in streams.values():
        stream.sort(key=lambda e: e['sequence'])
        previous, seen = None, set()
        for sequence, event in enumerate(stream, 1):
            if event['sequence'] != sequence or event['previous_event_sha256'] != previous:
                raise ValueError('event stream gap, duplicate or hash mismatch')
            correction = event['corrects_event_id']
            if correction is not None and correction not in seen:
                raise ValueError('correction must reference an earlier event in this work item')
            seen.add(event['event_id']); previous = record_digest(event)
    return {'records': len(rows), 'work_items': len({r['work_item_id'] for r in rows if r['kind'] == 'work_item'}),
            'attempts': len(attempts), 'event_streams': len(streams)}
