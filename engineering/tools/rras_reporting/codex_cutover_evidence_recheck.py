"""Bind independent admission and spending checks to a protected cutover plan."""
import copy
import hashlib
import importlib.util
from pathlib import Path


def runtime():
    spec = importlib.util.spec_from_file_location('cutover_evidence_runtime', Path(__file__).with_name('codex_runtime.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recheck:
    def __init__(self, request, verify, verify_authority):
        if type(request) is not dict or not callable(verify) or not callable(verify_authority):
            raise ValueError('fixed request and independent verifiers required')
        self.request = copy.deepcopy(request)
        self.verify = verify
        self.verify_authority = verify_authority

    def __call__(self, plan):
        if type(plan) is not dict or plan.get('evidence_sha256') != hashlib.sha256(runtime().encoded(self.request)).hexdigest():
            raise ValueError('protected request does not match cutover plan')
        if self.verify(copy.deepcopy(self.request)) is not True:
            raise ValueError('current admission evidence required')
        if self.verify_authority(copy.deepcopy(self.request)) != plan.get('authority'):
            raise ValueError('current scoped execution authority required')
        return True
