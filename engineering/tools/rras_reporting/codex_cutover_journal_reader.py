"""Read-only independent verification of a service-owned cutover journal."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import stat


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_journal_reader_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Reader:
    def __init__(self, directory, owner_uid):
        self.directory = Path(directory)
        if type(owner_uid) is not int or owner_uid <= 0:
            raise ValueError('dedicated journal owner required')
        self.owner = owner_uid

    def __call__(self, expected_policy_sha, expected_receipt_sha):
        root = self.directory
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError('canonical journal directory required')
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != self.owner or info.st_mode & 0o077:
            raise ValueError('private service-owned journal directory required')
        path = root / 'runtime.sqlite3'
        item = path.lstat()
        if (not stat.S_ISREG(item.st_mode) or item.st_uid != self.owner or item.st_nlink != 1 or
                item.st_mode & 0o077 or path.resolve() != path):
            raise ValueError('private service-owned journal required')
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3) as db:
            db.execute('BEGIN')
            rows = db.execute('SELECT body FROM policy').fetchall()
            if len(rows) != 1:
                raise ValueError('one retained journal policy required')
            runtime = local('codex_runtime')
            actual = hashlib.sha256(runtime.encoded(runtime.policy(json.loads(rows[0][0])))).hexdigest()
            if actual != expected_policy_sha:
                return False
            if expected_receipt_sha is None:
                return True
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='policy_issue_admissions'").fetchone():
                return False
            receipts = db.execute('SELECT plan_sha256 FROM policy_issue_admissions WHERE plan_sha256=?',
                                  (expected_receipt_sha,)).fetchall()
            return len(receipts) == 1
