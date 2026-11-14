"""Root-owned file adapter for one fixed issue-policy cutover."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re


def local(name):
    spec = importlib.util.spec_from_file_location('root_cutover_files_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Files:
    def __init__(self, policy, audit, *, owner=0):
        self.policy, self.audit, self.owner = Path(policy), Path(audit), owner
        local('codex_cutover_files').private_directory(self.audit, owner)

    def digest(self):
        protected = local('protected_config')
        runtime = local('codex_runtime')
        raw = protected.read(self.policy, maximum=8 * 1024 * 1024, require_root=self.owner == 0)
        if self.policy.lstat().st_uid != self.owner:
            raise ValueError('protected policy owner differs')
        return hashlib.sha256(runtime.encoded(runtime.policy(json.loads(raw)))).hexdigest()

    def name(self, sha, suffix):
        if type(sha) is not str or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('exact cutover digest required')
        return sha + '.' + suffix

    def retain_intent(self, sha, plan, old, new):
        return local('codex_cutover_files').retain(self.audit, self.name(sha, 'intent'),
            {'plan_sha256':sha, 'plan':plan, 'old':old, 'new':new}, owner=self.owner)

    def install(self, old_sha, new):
        return local('codex_cutover_files').install(self.policy, old_sha, new, owner=self.owner)

    def retain_completion(self, sha):
        return local('codex_cutover_files').retain(self.audit, self.name(sha, 'complete'),
            {'plan_sha256':sha}, owner=self.owner)
