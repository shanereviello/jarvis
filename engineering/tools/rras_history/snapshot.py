"""Private consistent SQLite snapshot; inert staging only, never a live restore.

Encryption and key custody are external gates. This module never publishes a
plaintext snapshot or opens the operational journal. No network or action API.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time

MAX_BYTES=64*1024*1024


def private_file(path):
    path=Path(path)
    info=path.lstat()
    if (path.resolve(strict=True)!=path or not stat.S_ISREG(info.st_mode) or
            info.st_nlink!=1 or info.st_uid!=os.getuid() or info.st_mode&0o077):
        raise ValueError('private caller-owned regular file required')
    if info.st_size>MAX_BYTES:raise ValueError('snapshot input exceeds bound')
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(database,destination):
    """SQLite online backup into a new private directory, retaining failures.

    All current immutable documents, receipts and pending rows reside inside the
    database transaction. Deployment artifacts/grants still require a separate
    pinned bundle; this snapshot alone does not satisfy production backup gates.
    """
    if os.getuid()==0 or os.geteuid()!=os.getuid():raise ValueError('unprivileged snapshot owner required')
    database=private_file(database);destination=Path(destination)
    if not destination.is_absolute() or destination.parent.resolve(strict=True)!=destination.parent:
        raise ValueError('canonical snapshot parent required')
    parent=destination.parent.stat()
    if parent.st_uid!=os.getuid() or parent.st_mode&0o077:
        raise ValueError('private snapshot parent required')
    destination.mkdir(mode=0o700)
    target=destination/'history.sqlite3'
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(fd)
    deadline=time.monotonic()+30
    def progress(status,remaining,total):
        if total*page_size>MAX_BYTES or time.monotonic()>deadline:
            raise ValueError('snapshot size or deadline exceeded')
    source=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=5)
    backup=sqlite3.connect(target,timeout=5)
    try:
        source.execute('PRAGMA query_only=ON')
        page_size=source.execute('PRAGMA page_size').fetchone()[0]
        source.backup(backup,pages=128,progress=progress,sleep=0.05)
        if backup.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
            raise ValueError('snapshot integrity failed')
        if backup.execute('PRAGMA user_version').fetchone()[0]!=1:
            raise ValueError('unsupported snapshot schema')
    finally:
        backup.close();source.close()
    private_file(target)
    with target.open('rb') as stream:os.fsync(stream.fileno())
    manifest={'contract':'engineering-history-snapshot.v1','database_sha256':digest(target),
              'schema_version':1,'encrypted':False,'production_backup_ready':False,
              'action_execution_enabled':False}
    path=destination/'snapshot-manifest.json'
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(manifest,stream,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    fd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return manifest
