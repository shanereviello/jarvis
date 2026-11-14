"""Retain a short-lived proof after independently verified isolation checks.

The protected caller must supply an actual native App Server probe and current
unit verifier. This writer never decides what was tested or starts a model.
"""
from datetime import datetime, timedelta, timezone
import copy
import importlib.util
from pathlib import Path
import re


def local(name):
    spec = importlib.util.spec_from_file_location('sandbox_writer_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def create(directory, name, expected, verify_units, probe, *, owner=0, clock=lambda:datetime.now(timezone.utc)):
    keys = {'issue_id','workspace','socket','service_name','socket_name','service_sha256','socket_sha256','native_release','native_binary_sha256'}
    if (type(expected) is not dict or set(expected) != keys or not callable(verify_units) or not callable(probe) or
            type(name) is not str or not re.fullmatch('[a-z0-9][a-z0-9.-]{0,127}', name)):
        raise ValueError('exact units and protected independent checks required')
    # Check both before and after the native test; mutable live unit state must
    # not be certified on the strength of an older observation.
    if verify_units(copy.deepcopy(expected)) is not True:raise ValueError('current units not verified')
    result = probe(copy.deepcopy(expected))
    required = {'native_identity_verified','sandbox_own_write_allowed','sandbox_sibling_write_denied','models_started'}
    if (type(result) is not dict or set(result) != required or
            any(result[k] is not True for k in required - {'models_started'}) or
            type(result['models_started']) is not int or result['models_started'] != 0):
        raise ValueError('exact model-free native isolation result required')
    if verify_units(copy.deepcopy(expected)) is not True:raise ValueError('units changed during sandbox test')
    now = clock()
    if not isinstance(now,datetime) or now.tzinfo is None:raise ValueError('trusted UTC clock required')
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    proof = dict(contract='codex-sandbox-isolation-proof.v1',**expected,
        issued_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'),expires_at=(now+timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%SZ'),**result)
    digest = local('codex_cutover_files').retain(Path(directory), name, proof, owner=owner)
    return {'proof_sha256':digest,'models_started':0,'execution_authorized':False}
