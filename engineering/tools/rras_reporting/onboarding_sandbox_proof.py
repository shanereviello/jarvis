"""Verify a root-controlled, short-lived native sandbox isolation proof.

The producer must independently perform the actual model-free sandbox test.
This verifier cannot generate proof, authorize execution, or start work.
"""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import re


def protected():
    spec = importlib.util.spec_from_file_location('sandbox_proof_protected', Path(__file__).with_name('protected_config.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def utc(value):
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',value):
        raise ValueError('exact UTC timestamp required')
    return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


class Verifier:
    def __init__(self, path, *, clock=lambda:datetime.now(timezone.utc), loader=None):
        self.path = Path(path)
        if not self.path.is_absolute() or not callable(clock):raise ValueError('protected proof and clock required')
        self.clock = clock
        self.loader = loader or (lambda p:protected().decode(p, require_root=True, maximum=65536))

    def __call__(self, expected):
        proof = self.loader(self.path)
        fields = {'contract','issue_id','workspace','socket','service_name','socket_name','service_sha256',
                  'socket_sha256','native_release','issued_at','expires_at','native_identity_verified',
                  'sandbox_own_write_allowed','sandbox_sibling_write_denied','models_started'}
        if type(proof) is not dict or set(proof) != fields or proof['contract'] != 'codex-sandbox-isolation-proof.v1':
            raise ValueError('exact sandbox isolation proof required')
        keys = {'issue_id','workspace','socket','service_name','socket_name','service_sha256','socket_sha256','native_release'}
        if type(expected) is not dict or set(expected) != keys or any(proof[k] != expected[k] for k in keys):
            raise ValueError('sandbox proof does not bind exact issue units')
        issued, expires, now = utc(proof['issued_at']), utc(proof['expires_at']), self.clock()
        if (not isinstance(now,datetime) or now.tzinfo is None or not issued <= now < expires or
                (expires-issued).total_seconds() > 900):
            raise ValueError('fresh bounded sandbox proof required')
        if (any(proof[key] is not True for key in ('native_identity_verified','sandbox_own_write_allowed','sandbox_sibling_write_denied')) or
                type(proof['models_started']) is not int or proof['models_started'] != 0):
            raise ValueError('complete model-free isolation proof required')
        return True
