"""Journal-side file adapter for the protected fixed-transition broker."""
import hashlib
import importlib.util
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_client_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Files:
    def __init__(self, socket_path, *, request=None):
        self.socket_path = socket_path
        self.request = request or local('codex_cutover_broker_transport').call
        self.transition = None

    def invoke(self, operation):
        return self.request(self.socket_path, operation)

    def digest(self):
        result = self.invoke('digest')
        if type(result) is not str or len(result) != 64 or any(c not in '0123456789abcdef' for c in result):
            raise ValueError('exact broker policy digest required')
        return result

    def retain_intent(self, plan_sha, plan, old, new):
        runtime = local('codex_runtime')
        digest = lambda x: hashlib.sha256(runtime.encoded(x)).hexdigest()
        expected = {'plan_sha256': plan_sha, 'old_sha256': digest(old), 'new_sha256': digest(new)}
        if digest(plan) != plan_sha or self.invoke('transition') != expected:
            raise ValueError('broker transition differs from independently verified journal plan')
        if self.invoke('intent') != {'retained': True}:
            raise ValueError('broker intent outcome uncertain')
        self.transition = expected

    def install(self, old_sha, new):
        runtime = local('codex_runtime')
        if (self.transition is None or old_sha != self.transition['old_sha256'] or
                hashlib.sha256(runtime.encoded(new)).hexdigest() != self.transition['new_sha256']):
            raise ValueError('installation differs from retained transition')
        if self.invoke('install') != {'installed': True}:
            raise ValueError('broker installation outcome uncertain')

    def retain_completion(self, plan_sha):
        if self.transition is None or plan_sha != self.transition['plan_sha256']:
            raise ValueError('completion differs from retained transition')
        if self.invoke('complete') != {'completed': True}:
            raise ValueError('broker completion outcome uncertain')
