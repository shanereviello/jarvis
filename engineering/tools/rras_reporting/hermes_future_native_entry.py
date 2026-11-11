"""Bounded selected exporter intended to run inside the existing Hermes container.

Caller must validate the authenticated future-session registry page first. The
entry does not discover or authorize other sessions and starts no model.
"""
import json
from datetime import datetime, timezone
import hashlib
import math
import os
import re
import stat
import sys
import uuid
from pathlib import Path

sys.path.insert(0, '/opt/hermes')
sys.path.insert(0, '/opt/rras-engineering-reporting/engineering/tools/rras_reporting')
import capture_collectors
import capture_intake
import hermes_readonly
import hermes_state

SPOOL = '/opt/data/rras-engineering-capture/spool'


def exact_uuid(value):
    try:
        if str(uuid.UUID(value)) == value:
            return value
    except (ValueError, TypeError, AttributeError):
        pass
    raise ValueError('canonical identity required')


def main():
    if len(sys.argv) not in (7, 8):
        raise ValueError('exact selected native context required')
    _, organization, session, kind, identifier, cutoff, reference = sys.argv[:7]
    context = None
    if len(sys.argv) == 8:
        if len(sys.argv[7].encode()) > 4096:
            raise ValueError('bounded session context required')
        context = capture_intake.local('contract').decode(sys.argv[7].encode(), max_bytes=4096)
        if type(context) is not dict or type(context.get('work')) is not dict:
            raise ValueError('exact issue work context required')
    exact_uuid(organization); exact_uuid(session)
    if (kind not in ('repository', 'non_git') or not re.fullmatch('[a-zA-Z0-9_-]{1,128}', identifier) or
            (kind == 'non_git' and identifier != 'jarvis-non-git')):
        raise ValueError('exact destination scope required')
    if context is not None:
        capture_intake.local('reporting_contract').validate(dict(
            contract='engineering-reporting.v1', operation='source.observe',
            client_event_key='future-context-validation', expected_head=None,
            scope=dict(kind=kind, id=identifier), context=context,
            source=dict(kind='imported', namespace='hermes_capture', id=None),
            occurred_at=None, body=dict(source=dict(namespace='hermes', id=session),
                source_observed_at=None, cursor=None, status='unknown', gaps=[],
                detail='Validate explicit session-level work context.')))
    capture_collectors.authorization(reference)
    spool = capture_intake.Spool(SPOOL)
    alias = 'linear:' + organization + ':' + session
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', cutoff):
        raise ValueError('fixed UTC capture cutoff required')
    start = datetime.fromisoformat(cutoff[:-1] + '+00:00').astimezone(timezone.utc).timestamp()
    path = Path('/opt/data/state.db'); info = path.lstat()
    if (path.resolve() != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022 or
            hashlib.sha256(Path(hermes_state.__file__).read_bytes()).hexdigest() != hermes_readonly.STATE_SOURCE_SHA256):
        raise ValueError('pinned native reader and database required')
    db = hermes_state.SessionDB(db_path=path, read_only=True)
    try:
        if db.read_only is not True:
            raise ValueError('read-only native reader required')
        db._conn.execute('BEGIN')
        try:
            metadata = db.get_session(alias)
            created = metadata.get('started_at') if metadata else None
            if type(created) not in (int, float) or not math.isfinite(created) or created <= start:
                raise ValueError('native session predates the rollout cutoff')
            snapshot = capture_collectors.selected_hermes(db, alias, reference)
        finally:
            db._conn.execute('ROLLBACK')
    finally:
        db.close()
    result = capture_collectors.collect_hermes(spool, snapshot=snapshot,
        exporter='/opt/hermes/hermes_cli/session_export_md.py',
        scope=dict(kind=kind, id=identifier), context=context, authorization_reference=reference)
    print(json.dumps(dict(session_id=session, changed=result['changed'], models_started=0)))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        sys.exit('Selected Hermes capture refused; source and queued evidence retained.')
