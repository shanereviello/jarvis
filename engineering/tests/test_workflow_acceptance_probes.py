"""Acceptance guard tests: never cross a privileged or container boundary."""
import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1] / 'tools/rras_native'


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_host_probe_refuses_unprivileged_execution():
    m = module('probe_workflow_host')
    with patch.object(m.os, 'getuid', return_value=1000), patch.object(m.os, 'geteuid', return_value=1000):
        with pytest.raises(ValueError, match='root acceptance'): m.run('/unused')


def test_host_probe_refuses_real_worker_even_as_root():
    m = module('probe_workflow_host')
    with patch.object(m.os, 'getuid', return_value=0), patch.object(m.os, 'geteuid', return_value=0), \
         patch.object(m.subprocess, 'run', side_effect=AssertionError('must not launch anything')):
        with pytest.raises(ValueError, match='model-free worker'): m.run('/unused')


def test_container_probe_rejects_incomplete_payload_before_running_stdio():
    m = module('probe_workflow_reader')
    with patch.object(m.os, 'getuid', return_value=1000):
        with pytest.raises(ValueError, match='exact UID1000'): asyncio.run(m.probe({'files': {}}))


def test_container_probe_rejects_bad_hash_before_loading_supplied_code():
    m = module('probe_workflow_reader')
    payload = {'files': {name: {'sha256': '0' * 64, 'base64': 'aGFybWxlc3M='} for name in m.ALLOWED}}
    with patch.object(m.os, 'getuid', return_value=1000):
        with pytest.raises(ValueError, match='digest mismatch'): asyncio.run(m.probe(payload))
