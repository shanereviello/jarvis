"""Offline candidate and snapshot publication checks; no install or services."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest
import test_workflow_records as fixtures

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/rras_native' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def committed_source(tmp_path):
    m = module('prepare_workflow_release')
    repo = tmp_path / 'source'
    repo.mkdir()
    names = ['engineering/tools/rras_native/' + name for name in m.MODULES] + [
        'engineering/contracts/workflow-v1.schema.json', 'engineering/config/workflow-dependency-lock.json',
        'engineering/config/jarvis-registration.candidate.json']
    for name in names:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT.parent / name, target)
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True).stdout.decode().strip()
    git('init', '-q')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=f@localhost', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
    return m, repo, git('rev-parse', 'HEAD'), git


def test_package_uses_committed_bytes_and_is_deterministic(committed_source, tmp_path):
    m, repo, commit, _ = committed_source
    first, second = tmp_path / 'one', tmp_path / 'two'
    answer = m.build(repo, commit, first)
    # Uncommitted changes must never silently enter a production payload.
    (repo / 'engineering/tools/rras_native/manual_runner.py').write_text('UNCOMMITTED_PRIVATE_FIXTURE')
    other = m.build(repo, commit, second)
    assert answer['release'] == other['release']
    assert (first / 'release-manifest.json').read_bytes() == (second / 'release-manifest.json').read_bytes()
    raw = (first / 'engineering/tools/rras_native/manual_runner.py').read_text()
    assert 'UNCOMMITTED_PRIVATE_FIXTURE' not in raw
    assert 'def _run(' in raw
    assert not list(first.rglob('direct_url.json'))
    assert not list(first.rglob('*.pyc'))
    assert not list(first.rglob('probe_*.py'))
    plan = json.loads((first / 'install-plan.json').read_text())
    assert not plan['activation_authorized'] and plan['journal_required']
    assert len(plan['hermes']['add_readonly_mounts']) == 2
    assert all(mount['read_only'] for mount in plan['hermes']['add_readonly_mounts'])
    assert plan['operator_config']['journal'] == '/var/lib/rras-workflow/journal'
    assert 'requires a journal' in (first / 'entrypoints/operator.py').read_text()


def test_package_refuses_existing_destination_and_wrong_commit(committed_source, tmp_path):
    m, repo, commit, _ = committed_source
    output = tmp_path / 'existing'
    output.mkdir()
    with pytest.raises(ValueError): m.build(repo, commit, output)
    with pytest.raises(ValueError): m.build(repo, '0' * 40, tmp_path / 'bad')


def test_package_refuses_acceptance_fake_worker(committed_source, tmp_path):
    m, repo, _, git = committed_source
    (repo / 'engineering/tools/rras_native/manual_runner.py').write_text('print("fake-ready.json")\n')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=f@localhost', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fake')
    with pytest.raises(ValueError, match='production coding runner'):
        m.build(repo, git('rev-parse', 'HEAD'), tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()


def test_offline_dependency_drift_refused(committed_source):
    m, _, _, _ = committed_source
    with pytest.raises(ValueError):
        m.offline_dependencies({'schema_version': 1, 'python': '0.0.0', 'distributions': {}})


@pytest.fixture
def publication(tmp_path):
    j, publisher = module('workflow_journal'), module('publish_workflow_views')
    store, views = tmp_path / 'store', tmp_path / 'views'
    store.mkdir(mode=0o700)
    views.mkdir(mode=0o750)
    journal = j.Journal(store, create=True)
    return j, publisher, journal, views


def test_empty_and_populated_publication_preserve_private_data(publication):
    j, p, store, views = publication
    assert p.publish(store.root, views, os.getgid())['pages'] == 0
    assert module('workflow_read_tools').pages(views) == []
    rows = fixtures.history()
    rows[-1]['summary'] = 'PRIVATE_NOT_SHARED'
    store.append(rows)
    result = p.publish(store.root, views, os.getgid())
    assert result['pages'] == 1
    entries = module('workflow_read_tools').pages(views)
    assert len(entries) == 1
    assert 'PRIVATE_NOT_SHARED' not in json.dumps(entries)
    assert (views / 'index.json').stat().st_mode & 0o777 == 0o440
    assert store.path.parent.stat().st_mode & 0o777 == 0o700


def test_failed_index_switch_retains_previous_complete_generation(publication):
    _, p, store, views = publication
    rows = fixtures.history()
    store.append(rows)
    p.publish(store.root, views, os.getgid())
    previous = (views / 'index.json').read_bytes()
    store.append([fixtures.next_event(rows)])
    replace = p.os.replace
    def fail_index(source, destination):
        if Path(destination) == views / 'index.json':
            raise OSError('fixture index switch failure')
        return replace(source, destination)
    with patch.object(p.os, 'replace', side_effect=fail_index):
        with pytest.raises(OSError): p.publish(store.root, views, os.getgid())
    assert (views / 'index.json').read_bytes() == previous
    assert len(module('workflow_read_tools').pages(views)[0][1]['summary']['facts']) == 1


def test_generation_uses_one_snapshot_despite_concurrent_append(publication):
    j, p, store, views = publication
    rows = fixtures.history()
    store.append(rows)
    original = p.local
    def modules(name):
        value = original(name)
        if name == 'workflow_journal':
            original_records = value.Journal.records
            def records(instance):
                snapshot = original_records(instance)
                store.append([fixtures.next_event(rows)])
                return snapshot
            value.Journal.records = records
        return value
    with patch.object(p, 'local', side_effect=modules):
        p.publish(store.root, views, os.getgid())
    assert len(module('workflow_read_tools').pages(views)[0][1]['summary']['facts']) == 1
    assert len(store.history(rows[1]['work_item_id'])['events']) == 2


def test_publisher_refuses_unrelated_index_and_shared_private_tree(publication):
    _, p, store, views = publication
    (views / 'index.json').write_text('PRESERVE_UNRELATED_FILE')
    with pytest.raises(ValueError): p.publish(store.root, views, os.getgid())
    assert (views / 'index.json').read_text() == 'PRESERVE_UNRELATED_FILE'
    with pytest.raises(ValueError): p.publish(store.root, store.root, os.getgid())


def test_inactive_stager_refuses_unprivileged_invocation():
    m = module('stage_workflow_review')
    with patch.object(m.os, 'getuid', return_value=1000), patch.object(m.os, 'geteuid', return_value=1000), \
         patch.object(m, 'command', side_effect=AssertionError('must not contact host')):
        with pytest.raises(ValueError, match='administrator'): m.stage('/unused', '0' * 64)
