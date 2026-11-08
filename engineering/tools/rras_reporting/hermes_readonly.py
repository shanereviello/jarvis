"""Selected capture inside Hermes, using its pinned SELECT-only native reader.

No database discovery, prefix resolution, writer, schema migration or checkpoint.
The caller supplies an explicitly authorized exact initialized database path and
one session. Full native exports still pass the native and owned redactors.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import stat

STATE_SOURCE_SHA256='cb91e4d0647fe058a9b63ecdc637a15d897cf9541e41578463ed34f427164787'


def collector():
    spec=importlib.util.spec_from_file_location('hermes_readonly_collectors',Path(__file__).with_name('capture_collectors.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def selected(database,session,authorization_reference):
    m=collector();m.authorization(authorization_reference)
    if type(session) is not str or not re.fullmatch(m.HERMES_SESSION,session):raise ValueError('exact selected native session required')
    path=Path(database);info=path.lstat()
    if (not path.is_absolute() or path.resolve()!=path or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or
            info.st_uid not in (0,os.getuid()) or info.st_mode&0o022):raise ValueError('exact initialized native database required')
    import hermes_state as native
    if hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()!=STATE_SOURCE_SHA256:
        raise ValueError('native reader changed; review compatibility')
    # The inspected read_only branch opens mode=ro and skips all DDL, schema
    # reconciliation, repair and token-writer startup. close skips checkpointing.
    db=native.SessionDB(db_path=path,read_only=True)
    try:
        if db.read_only is not True:raise ValueError('SELECT-only native reader required')
        # One owned reader instance, one SQLite read snapshot across metadata,
        # lineage and messages. No concurrent API writer lock is acquired.
        db._conn.execute('BEGIN')
        try:return m.selected_hermes(db,session,authorization_reference)
        finally:db._conn.execute('ROLLBACK')
    finally:db.close()
