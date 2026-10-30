"""Offline fixture packaging/roles only; real cross-UID acceptance requires sudo."""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import pytest
from test_engineering_history_local import module

p=module('curated_host_package');d=module('curated_host_driver');probe=module('curated_host_probe')


@pytest.fixture
def candidate(tmp_path):
    root=tmp_path/'candidate';root.mkdir()
    files={name:b'fixture\n' for name in p.SOURCE_FILES};files['vendor/dependency.py']=b'pass\n'
    for name,raw in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={'contract':'engineering-curated-read-host.v1','scope':'isolated-synthetic-only','source_commit':'a'*40,
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
    raw=p.encoded(manifest);(root/p.MANIFEST).write_bytes(raw)
    return root,hashlib.sha256(raw).hexdigest(),manifest


def test_exact_synthetic_package_and_fixed_identity_scope(candidate):
    root,sha,manifest=candidate
    assert p.verify(root,sha)[0]==manifest
    assert p.STATE==Path('/var/lib/rras-curated-read-acceptance-20261029')
    assert (p.SERVICE,p.CLIENT,p.UNKNOWN)==(61121,61122,61123)
    assert all('rras_native' not in name for name in p.SOURCE_FILES)


@pytest.mark.parametrize('kind',['changed','symlink','hardlink','fifo'])
def test_package_refuses_changed_and_nonregular_bytes(candidate,tmp_path,kind):
    root,sha,_=candidate;path=root/'vendor/dependency.py'
    if kind=='changed':path.write_text('changed')
    else:
        path.unlink();other=tmp_path/'outside';other.write_text('pass\n')
        if kind=='symlink':path.symlink_to(other)
        elif kind=='hardlink':os.link(other,path)
        else:os.mkfifo(path)
    with pytest.raises(ValueError):p.verify(root,sha)


def test_wrong_contract_and_unsafe_member_refused(candidate):
    root,_,manifest=candidate;manifest['scope']='production'
    raw=p.encoded(manifest);(root/p.MANIFEST).write_bytes(raw)
    with pytest.raises(ValueError):p.verify(root,hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):p.safe_name('vendor/../../escape')
    with pytest.raises(ValueError):p.safe_name('vendor/hook.pth')


def test_emitted_bootstrap_is_stdlib_and_verifies_before_stage(candidate,tmp_path):
    helper=tmp_path/'stage.py';sha=p.emit_helper(helper)
    assert hashlib.sha256(helper.read_bytes()).hexdigest()==sha
    spec=importlib.util.spec_from_file_location('fixture_bootstrap',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    root,expected,_=candidate;assert m.verify(root,expected)[0]['scope']=='isolated-synthetic-only'
    assert 'curated_host_driver.py' in helper.read_text()
    assert 'native.resolve(strict=True)' in helper.read_text()


def test_role_commands_fixed_uid_and_containment():
    for role,uid in d.ROLES.items():
        cmd=d.command(role)
        assert cmd[cmd.index('--reuid')+1]==str(uid) and '--clear-groups' in cmd and '--bounding-set=-all' in cmd
        assert cmd[:3]==['/usr/bin/unshare','--net','--']
    with pytest.raises(ValueError):d.command('read',0)
    with pytest.raises(ValueError):d.command('denial',0)
    with pytest.raises(ValueError):d.command('arbitrary')


def test_policy_revocation_keeps_only_internal_readiness_role():
    before=d.policy();after=d.policy(False)
    assert {entry['uid'] for entry in before['principals']}=={p.SERVICE,p.CLIENT}
    assert after['principals']==[{'uid':p.SERVICE,'repositories':['example_library']}]


def test_seed_adapter_real_storage_excludes_private_prose(tmp_path,monkeypatch):
    state=tmp_path/'fixture';state.mkdir(mode=0o700);(state/'private').mkdir(mode=0o700);(state/'private/history').mkdir(mode=0o700)
    monkeypatch.setattr(probe,'STATE',state);monkeypatch.setattr(probe,'CATALOG',state/'private/catalog')
    monkeypatch.setattr(probe,'SERVICE',os.getuid());denials=[];monkeypatch.setattr(probe,'denied',lambda path:denials.append(path))
    result=probe.seed();assert result['private_prose_excluded'] and denials==[state/'source/private.fixture']
    view=module('curated_publication').search(state/'private/catalog','example_library','')
    assert len(view['entries'])==1 and view['entries'][0]['source_authenticated'] is False
    assert b'SYNTHETIC PRIVATE' not in module('contract').encoded(view)
