"""Fixed-transition privileged file broker; transport and hosting are separate.

The protected host must instantiate this with a root-controlled transition,
independent verifiers, a held admission lock and restart exclusion. Calls may
select only an operation: they cannot supply paths, policies or authority.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location('fixed_cutover_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Broker:
    def __init__(self, *, peer_uid, transition, files, verify_stopped, verify_journal, verify_evidence):
        if type(peer_uid) is not int or peer_uid <= 0 or any(not callable(x) for x in
                (verify_stopped, verify_journal, verify_evidence)):
            raise ValueError('distinct peer and independent host verifiers required')
        if type(transition) is not dict or set(transition) != {'plan', 'old', 'new'}:
            raise ValueError('exact protected transition required')
        self.value = copy.deepcopy(transition)
        self.peer_uid = peer_uid
        self.files = files
        self.verify_stopped = verify_stopped
        self.verify_journal = verify_journal
        self.verify_evidence = verify_evidence
        runtime = local('codex_runtime')
        self.old = hashlib.sha256(runtime.encoded(runtime.policy(self.value['old']))).hexdigest()
        self.new = hashlib.sha256(runtime.encoded(runtime.policy(self.value['new']))).hexdigest()
        self.plan_sha = hashlib.sha256(runtime.encoded(self.value['plan'])).hexdigest()
        if self.old == self.new or (self.value['plan'].get('old_policy_sha256'),
                self.value['plan'].get('new_policy_sha256')) != (self.old, self.new):
            raise ValueError('exact distinct transition digests required')
        self.stage = 'new'

    def call(self, peer_uid, operation):
        if type(peer_uid) is not int or peer_uid != self.peer_uid or type(operation) is not str:
            raise ValueError('broker access refused')
        if self.verify_stopped() is not True:
            raise ValueError('restart exclusion or stopped runtime not verified')
        if operation == 'digest':
            return self.files.digest()
        if operation == 'intent' and self.stage == 'new':
            if self.files.digest() != self.old or self.verify_journal(self.old, None) is not True:
                raise ValueError('old policy state not verified')
            self.files.retain_intent(self.plan_sha, **copy.deepcopy(self.value))
            self.stage = 'intent'
            return {'retained': True}
        if operation == 'install' and self.stage == 'intent':
            if (self.files.digest() != self.old or self.verify_journal(self.new, self.plan_sha) is not True or
                    self.verify_evidence(copy.deepcopy(self.value['plan'])) is not True):
                raise ValueError('current journal and execution evidence required')
            self.files.install(self.old, copy.deepcopy(self.value['new']))
            if self.files.digest() != self.new:
                raise ValueError('installed policy outcome uncertain')
            self.stage = 'installed'
            return {'installed': True}
        if operation == 'complete' and self.stage == 'installed':
            if self.files.digest() != self.new or self.verify_journal(self.new, self.plan_sha) is not True:
                raise ValueError('completed transition not verified')
            self.files.retain_completion(self.plan_sha)
            self.stage = 'complete'
            return {'completed': True}
        raise ValueError('unexpected operation; inspect retained state')
