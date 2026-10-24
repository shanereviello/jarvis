"""Generated root tooling refusal, inactive guarantees and mutation boundaries."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_engineering_history_local import module

builder=module('install_package');package=module('production_package')
SOURCE=Path(__file__).resolve().parents[2]


@pytest.fixture
def generated(tmp_path):
    helper=tmp_path/'install.py';builder.emit_helper(helper)
    spec=importlib.util.spec_from_file_location('generated_install',helper)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


@pytest.fixture
def candidate(tmp_path):
    vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'fixture.py').write_text('SYNTHETIC=True\n')
    dest=tmp_path/'candidate';result=package.build(SOURCE,vendor,dest,'a'*40)
    return dest,result


def test_generated_verifier_independently_verifies_candidate(generated,candidate):
    dest,result=candidate
    manifest,files=generated.verify(dest,result['manifest_sha256'])
    assert manifest['activation_authorized'] is False
    assert json.loads(files['deployment/install-plan.json'])['backup_status'].startswith('deferred-by-operator')
    (dest/'deployment/access-policy.json').write_text('{}')
    with pytest.raises(ValueError):generated.verify(dest,result['manifest_sha256'])


def test_unprivileged_install_refused_before_file_access(generated,monkeypatch,tmp_path):
    monkeypatch.setattr(generated.os,'getuid',lambda:1000)
    with pytest.raises(ValueError,match='administrator'):generated.install(tmp_path,'a'*64)


def test_check_only_never_creates_journal(generated,monkeypatch,tmp_path):
    journal=tmp_path/'journal'
    monkeypatch.setattr(generated,'preflight',lambda *_:({}, {}, journal))
    result=generated.install(tmp_path,'a'*64,check_only=True)
    assert result['mutations'] is False and not journal.exists()


def test_preflight_refuses_existing_identity_before_mutation(generated,candidate,monkeypatch):
    dest,result=candidate
    monkeypatch.setattr(generated.os,'getuid',lambda:0);monkeypatch.setattr(generated.os,'geteuid',lambda:0)
    monkeypatch.setattr(generated,'protected',lambda _:None)
    monkeypatch.setattr(generated,'absent',lambda _:None)
    monkeypatch.setattr(generated.pwd,'getpwnam',lambda _:object())
    with pytest.raises(ValueError,match='identity already exists'):generated.preflight(dest,result['manifest_sha256'])


def test_write_new_preserves_existing_file(generated,tmp_path):
    path=tmp_path/'retained';path.write_bytes(b'original')
    with pytest.raises(FileExistsError):generated.write_new(path,b'changed')
    assert path.read_bytes()==b'original'


def test_installer_control_commands_cannot_start_or_enable():
    # Audit every systemctl literal, not a mocked success result.
    import ast
    tree=ast.parse((SOURCE/'engineering/tools/rras_history/inactive_install.py').read_text())
    commands=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.List) and node.elts and isinstance(node.elts[0],ast.Constant) and node.elts[0].value=='/usr/bin/systemctl':
            commands.append(node.elts[1].value)
    assert sorted(commands)==['daemon-reload','show']


def test_failed_command_preserves_private_diagnostics(generated,tmp_path,monkeypatch):
    monkeypatch.setattr(generated,'command',lambda _:SimpleNamespace(returncode=1,stdout=b'',stderr=b'synthetic failure'))
    # Test as actual caller; override ownership only, never execute a host command.
    original=generated.write_new
    monkeypatch.setattr(generated,'write_new',lambda path,raw:original(path,raw,uid=os.getuid(),gid=os.getgid()))
    with pytest.raises(ValueError,match='preserve private diagnostic'):generated.Install(tmp_path).run(['synthetic'],'failure')
    assert (tmp_path/'01-failure-stderr').read_bytes()==b'synthetic failure'
    assert (tmp_path/'01-failure-stderr').stat().st_mode&0o777==0o600
