"""Offline writer fixture and exact packaging; actual unit boundaries require sudo."""
import hashlib
import importlib.util
from pathlib import Path
import pytest
from test_engineering_history_local import module

p=module('curated_writer_package');d=module('curated_writer_driver')


@pytest.fixture
def candidate(tmp_path):
    root=tmp_path/'candidate';root.mkdir()
    files={name:b'fixture\n' for name in p.SOURCE_FILES};files['vendor/dependency.py']=b'pass\n'
    for name,raw in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={'contract':'engineering-curated-writer-host.v1','scope':'isolated-synthetic-only','source_commit':'a'*40,
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
    raw=p.encoded(manifest);(root/p.MANIFEST).write_bytes(raw)
    return root,hashlib.sha256(raw).hexdigest()


def test_pinned_fixture_and_production_scope_refusal(candidate):
    root,sha=candidate
    assert p.verify(root,sha)[0]['scope']=='isolated-synthetic-only'
    assert p.STATE==d.STATE==Path('/var/lib/rras-curated-writer-acceptance-attempt02-20261029')
    assert d.UID==61142 and d.UNIT!='rras-curated-publication.service'
    with pytest.raises(ValueError):p.verify(root,'0'*64)
    (root/'vendor/dependency.py').write_text('changed')
    with pytest.raises(ValueError):p.verify(root,sha)


def test_real_blueprint_retained_except_explicit_fixture_substitutions():
    argv=d.unit_command('publish')
    assert '--unit='+d.UNIT in argv and '--unit=rras-curated-publication.service' not in argv
    props=[argv[i+1] for i,value in enumerate(argv) if value=='--property']
    assert 'User=61142' in props and 'Group=61142' in props
    assert [value for value in props if value.startswith('ReadWritePaths=')]==['ReadWritePaths='+str(d.STATE/'private/catalog')]
    for value in ('ProtectSystem=strict','PrivateNetwork=yes','NoNewPrivileges=yes','CapabilityBoundingSet=','KillMode=control-group'):assert value in props
    assert argv[-1]=='publish' and 'curated_writer_probe.py' in argv[-2]
    assert 'RuntimeMaxSec=2s' in d.unit_command('timeout',True)
    with pytest.raises(ValueError):d.unit_command('arbitrary')


def test_root_driver_denies_operator_before_any_mutation():
    with pytest.raises(ValueError,match='sudo'):d.run()


def test_bootstrap_exact_bytes_before_root_import(candidate,tmp_path):
    helper=tmp_path/'bootstrap.py';sha=p.emit_helper(helper)
    assert hashlib.sha256(helper.read_bytes()).hexdigest()==sha
    spec=importlib.util.spec_from_file_location('writer_bootstrap',helper);boot=importlib.util.module_from_spec(spec);spec.loader.exec_module(boot)
    root,expected=candidate;assert boot.verify(root,expected)[0]['scope']=='isolated-synthetic-only'
    assert 'curated_writer_driver.py' in helper.read_text()
    assert 'history-curated-writer-host-' in helper.read_text()


def test_temporary_identity_is_locked_without_home_or_mail_override(monkeypatch):
    calls=[]
    monkeypatch.setattr(d,'identity_command',lambda argv,tag:calls.append((argv,tag)))
    monkeypatch.setattr(d,'verify_identity',lambda:None)
    d.create_identity()
    assert calls[0][0]==['/usr/sbin/groupadd','--gid','61142',d.ACCOUNT]
    user=calls[1][0]
    assert user[0]=='/usr/sbin/useradd' and user[-1]==d.ACCOUNT
    for flag in ('--no-create-home','--no-log-init','--no-user-group'):assert flag in user
    assert user[user.index('--shell')+1]=='/usr/sbin/nologin'
    assert user[user.index('--password')+1]=='!'
    assert '-K' not in user
