"""Offline candidate and snapshot publication checks; no install or services."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
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
    names = ['engineering/tools/rras_native/' + name for name in (*m.MODULES,*m.ASSETS)] + [
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


def upgrade_inputs():
    return {'installed_release':'/opt/rras-engineering/releases/workflow-421ce120c6da',
        'operator_config_sha256':'a'*64,'hermes_config_sha256':'b'*64,'hermes_compose_sha256':'c'*64}


def test_complete_finish_validation_publication_and_frontend_payload(committed_source,tmp_path):
    m,repo,commit,_=committed_source;out=tmp_path/'complete';m.build(repo,commit,out)
    for name in ('workflow_finish','validation_workspace','validation_execution','workflow_publication','draft_pr_connector','publication_transport'):
        assert (out/'engineering/tools/rras_native'/(name+'.py')).is_file()
    assert (out/'entrypoints/draft-pr-frontend.js').is_file()
    # Exercise the actual generated isolated Python entrypoint, not a text match.
    result=subprocess.run([sys.executable,'-I','-B',str(out/'entrypoints/draft-pr.py'),'--help'],capture_output=True,text=True,check=True)
    assert 'prepare' in result.stdout and 'unknown' in result.stdout


def test_missing_transitive_dependency_refused_before_candidate(committed_source,tmp_path):
    m,repo,_,git=committed_source
    path=repo/'engineering/tools/rras_native/operator_control.py'
    path.write_text(path.read_text()+"\ndef future_dependency():return local('missing_reviewed_module')\n")
    git('add','.');git('-c','user.name=Fixture','-c','user.email=f@localhost','commit','-qm','dependency')
    out=tmp_path/'refused'
    with pytest.raises(ValueError,match='unpackaged local dependency'):m.build(repo,git('rev-parse','HEAD'),out)
    assert not out.exists()


def test_upgrade_plan_preserves_state_and_is_rejected_by_first_install_stager(committed_source,tmp_path):
    m,repo,commit,_=committed_source;out=tmp_path/'upgrade'
    m.build(repo,commit,out,upgrade_inputs());plan=json.loads((out/'install-plan.json').read_bytes())
    manifest=json.loads((out/'release-manifest.json').read_bytes())
    assert manifest['schema_version']==2 and manifest['kind']=='workflow_upgrade_candidate'
    assert plan['scope']=='inactive_upgrade_candidate_only' and not plan['installer_implemented']
    assert plan['operator_config_action']=='preserve_existing_bytes' and 'operator_config' not in plan
    assert not plan['candidate_registration_applied'] and not plan['activation_authorized']
    assert '/var/lib/rras-workflow/journal' in plan['preserve_paths']
    assert '/var/lib/rras-coding-control' in plan['preserve_paths']
    assert plan['hermes']['replace_readonly_mount']['expected_source']==upgrade_inputs()['installed_release']
    assert plan['hermes']['preserve_other_entries_and_mounts']
    stager=module('stage_workflow_review')
    with patch.object(stager.os,'getuid',return_value=0),patch.object(stager.os,'geteuid',return_value=0),patch.object(stager,'command',side_effect=AssertionError('must refuse before contacting host')):
        with pytest.raises(ValueError,match='invalid production manifest'):
            stager.stage(out,m.activity().digest((out/'release-manifest.json').read_bytes()))


@pytest.mark.parametrize('key,value',[('installed_release','/tmp/source'),('operator_config_sha256','invalid'),('hermes_config_sha256',None),('hermes_compose_sha256',True)])
def test_upgrade_preconditions_refused_before_candidate(committed_source,tmp_path,key,value):
    m,repo,commit,_=committed_source;inputs=upgrade_inputs();inputs[key]=value;out=tmp_path/'bad-upgrade'
    with pytest.raises(ValueError):m.build(repo,commit,out,inputs)
    assert not out.exists()


def test_payload_modules_import_without_builder_site_packages(committed_source,tmp_path):
    m,repo,commit,_=committed_source;out=tmp_path/'isolated-imports';m.build(repo,commit,out)
    script="""import importlib.util,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'vendor'))
for path in sorted((root/'engineering/tools/rras_native').glob('*.py')):
 spec=importlib.util.spec_from_file_location(path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
import jsonschema
assert jsonschema.Draft202012Validator is not None
print('isolated_payload_imports_passed')
"""
    result=subprocess.run([sys.executable,'-I','-S','-B','-c',script,str(out)],capture_output=True,text=True,check=True)
    assert result.stdout.strip()=='isolated_payload_imports_passed'
