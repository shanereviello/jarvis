"""Pinned stdlib staging: no early evaluation, exclusive release, retained failures."""
import importlib.util
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_engineering_history_local import module
from test_history_review_tools_package import candidate

p=module('review_tools_package')


@pytest.fixture
def bootstrap(tmp_path,monkeypatch):
    path=tmp_path/'stage.py';sha=p.emit_stage_helper(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
    spec=importlib.util.spec_from_file_location('stage_test',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    releases=tmp_path/'releases';releases.mkdir()
    monkeypatch.setattr(m,'RELEASES',releases);monkeypatch.setattr(m,'JOURNALS',tmp_path/'journals')
    monkeypatch.setattr(m,'protected',lambda path:None)
    monkeypatch.setattr(m.os,'getuid',lambda:0);monkeypatch.setattr(m.os,'geteuid',lambda:0)
    return m


def test_preflight_verifies_without_mutations(bootstrap,candidate):
    m=bootstrap;root,sha,_=candidate
    result=m.stage(root,sha,check_only=True)
    assert result['mutations'] is False and not list(m.RELEASES.iterdir()) and not m.JOURNALS.exists()


def test_bad_manifest_before_any_protected_mutation(bootstrap,candidate):
    m=bootstrap;root,_,_=candidate
    with pytest.raises(ValueError):m.stage(root,'f'*64)
    assert not list(m.RELEASES.iterdir()) and not m.JOURNALS.exists()


def test_existing_release_refused_before_journal_creation(bootstrap,candidate):
    m=bootstrap;root,sha,_=candidate;(m.RELEASES/('history-review-tools-'+sha[:12])).mkdir()
    with pytest.raises(ValueError,match='preserve existing'):m.stage(root,sha)
    assert not m.JOURNALS.exists()


def test_stage_readonly_bytes_no_wrappers_or_service_changes(bootstrap,candidate,monkeypatch):
    m=bootstrap;root,sha,manifest=candidate
    def accept(release,expected,journal):
        assert p.verify(release,expected)[0]==manifest
        assert all((release/name).stat().st_mode&0o777==0o444 for name in manifest['files'])
        assert all(x.stat().st_mode&0o777==0o755 for x in release.rglob('*') if x.is_dir())
        return ['synthetic-test-adapter']
    monkeypatch.setattr(m,'acceptance',accept)
    result=m.stage(root,sha)
    assert result['wrappers_installed'] is False and result['services_changed'] is False
    assert (Path(result['journal'])/'complete.json').exists()
    with pytest.raises(ValueError):m.stage(root,sha)


def test_failure_preserves_partial_release_and_diagnostic(bootstrap,candidate,monkeypatch):
    m=bootstrap;root,sha,_=candidate
    def fail(*args):raise ValueError('private error must not be exported')
    monkeypatch.setattr(m,'acceptance',fail)
    with pytest.raises(ValueError):m.stage(root,sha)
    journal=m.JOURNALS/sha
    assert m.decode((journal/'stopped.json').read_bytes())=={'exception_type':'ValueError','automatic_retry':False}
    assert not (journal/'complete.json').exists() and list(m.RELEASES.iterdir())


def test_preflight_protects_native_interpreter_before_execution(bootstrap,candidate,monkeypatch):
    m=bootstrap;root,sha,_=candidate;paths=[]
    monkeypatch.setattr(m,'protected',lambda path:paths.append(path));m.preflight(root,sha)
    assert m.PYTHON.parent in paths and m.PYTHON.resolve(strict=True) in paths


def test_probe_commands_drop_privileges_and_bound_execution(bootstrap,tmp_path,monkeypatch):
    m=bootstrap;seen=[]
    def run(command,**kwargs):
        seen.append((command,kwargs));return SimpleNamespace(returncode=0,stdout=b'usage:',stderr=b'')
    monkeypatch.setattr(m.subprocess,'run',run)
    journal=tmp_path/'probe';journal.mkdir()
    m.child(1000,['--help'],journal,'help')
    command,kwargs=seen[0]
    assert command[:3]==['/usr/bin/unshare','--net','--'] and '--clear-groups' in command and '--bounding-set=-all' in command
    assert kwargs['timeout']==30 and kwargs['env']==m.ENV


def test_probe_failure_retains_private_output(bootstrap,tmp_path,monkeypatch):
    m=bootstrap;journal=tmp_path/'probe';journal.mkdir()
    monkeypatch.setattr(m.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=1,stdout=b'',stderr=b'private fixture error'))
    with pytest.raises(ValueError):m.child(1000,['--help'],journal,'help')
    assert (journal/'help-stderr.txt').stat().st_mode&0o777==0o600
