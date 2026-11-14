"""Exclusive private state for create-once Jarvis issue proposals."""
from contextlib import contextmanager
import fcntl
import importlib.util
import os
from pathlib import Path
import sqlite3
import stat


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_journal_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def initialize(root):
    root=Path(root)
    if not root.is_absolute() or root.resolve()!=root or root.exists():raise ValueError('new private journal required')
    root.mkdir(mode=0o700,parents=False,exist_ok=False);local('codex_runtime').private(root,True)
    path=root/'issues.sqlite3';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
    with sqlite3.connect(path) as db:local('onboarding_issue_journal').IssueJournal.initialize(db)
    return dict(initialized=True,models_started=0,listener_started=False)


@contextmanager
def open_journal(root):
    runtime=local('codex_runtime');root=runtime.private(root,True);path=runtime.private(root/'issues.sqlite3')
    fd=os.open(root/'issues.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077:
            raise ValueError('private issue lock required')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        @contextmanager
        def connection():
            runtime.private(path);db=sqlite3.connect(path,timeout=5)
            db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA foreign_keys=ON')
            try:yield db
            except BaseException:db.rollback();raise
            finally:db.close()
        local('onboarding_issue_journal').IssueJournal(connection).recover_after_exclusive_start()
        yield connection
    finally:os.close(fd)
