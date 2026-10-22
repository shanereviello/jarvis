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


def test_two_host_fixture_repositories_change_only_registration_and_objective(tmp_path):
    import json
    m=module('probe_workflow_host');a=m.local('activity');records=m.local('workflow_records')
    here=tmp_path/'payload';here.mkdir()
    example=Path(__file__).resolve().parents[1]/'contracts/examples/library-managed.json'
    (here/'library-managed.json').write_bytes(example.read_bytes())
    first=m.fixture_records(here,tmp_path/'repo-one','a'*40,'example_library')
    second=m.fixture_records(here,tmp_path/'repo-two','b'*40,'closeout_library_two')
    for registration,work in (first,second):
        records.validate_record(registration);records.validate_record(work)
        assert work['registration_sha256']==a.digest(a.encoded(registration))
    assert first[0]['repository_id']!=second[0]['repository_id']
    assert first[1]['objective']!=second[1]['objective']
    assert first[0]['validation_recipes']==second[0]['validation_recipes']
    assert first[1]['requested_paths']==second[1]['requested_paths']
    with pytest.raises(ValueError,match='known offline'):m.fixture_records(here,tmp_path/'unused','a'*40,'arbitrary')
