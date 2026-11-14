"""Journal-owner half of a stopped-runtime issue cutover.

Protected file operations and evidence verification are independent injected
interfaces. This class does not provide a production IPC or service installer.
"""
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_journal_' + name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Adapter:
    def __init__(self, root, request, verify, verify_authority, files, admission_lock):
        if not callable(verify) or not callable(verify_authority) or not callable(admission_lock):
            raise ValueError('independent checks and operator lock required')
        self.root = Path(root)
        self.request = copy.deepcopy(request)
        self.verify = verify
        self.verify_authority = verify_authority
        self.files = files
        self.admission_lock = admission_lock
        self.db = None

    @contextmanager
    def exclusive_stopped(self):
        # The runtime lock is held across the SQLite commit and file install.
        # The surrounding operator lock must also exclude service restarts.
        with self.admission_lock():
            with local('codex_policy_migration').locked(self.root) as db:
                self.db = db
                try:
                    yield
                finally:
                    self.db = None

    def require_locked(self):
        if self.db is None:
            raise ValueError('cutover lock required')
        return self.db

    def revalidate(self):
        return local('codex_issue_admission_migration').snapshot(
            self.require_locked(), self.request, self.verify, self.verify_authority)

    def journal_digest(self):
        rows = self.require_locked().execute('SELECT body FROM policy').fetchall()
        if len(rows) != 1:
            raise ValueError('one journal policy required')
        runtime = local('codex_runtime')
        return hashlib.sha256(runtime.encoded(runtime.policy(json.loads(rows[0][0])))).hexdigest()

    def file_digest(self):
        self.require_locked()
        return self.files.digest()

    def retain_intent(self, plan_sha, plan, old, new):
        self.require_locked()
        self.files.retain_intent(plan_sha, plan, old, new)

    def update_journal(self, plan_sha):
        db = self.require_locked()
        local('codex_issue_admission_migration').apply_locked(
            db, self.request, self.verify, self.verify_authority, plan_sha)
        # Persist the journal while still holding runtime.lock. If the file
        # step fails, this deliberately remains a journal-ahead recovery case.
        db.commit()
        db.execute('BEGIN IMMEDIATE')

    def recheck_authority_and_evidence(self, plan, new):
        self.require_locked()
        if self.verify(copy.deepcopy(self.request)) is not True:
            raise ValueError('execution evidence revoked after journal update')
        if self.verify_authority(copy.deepcopy(self.request)) != plan['authority']:
            raise ValueError('execution authority changed after journal update')

    def install_policy_atomically(self, old_sha, new):
        self.require_locked()
        self.files.install(old_sha, new)

    def retain_completion(self, plan_sha):
        self.require_locked()
        self.files.retain_completion(plan_sha)
