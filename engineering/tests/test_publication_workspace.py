"""Operator path selection and early refusal, before importing source or pushing."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from test_rras_native_publication import fixture

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('handoff_paths',ROOT/'tools/rras_native/publication_handoff.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

@pytest.fixture
def home(tmp_path,monkeypatch):
    # Only system ancestors of the disposable fixture are emulated. Never change
    # real /tmp permissions; all tested workspace components use real metadata.
    original=Path.lstat
    system=set(tmp_path.parents)
    def metadata(p,*args,**kwargs):
        if p in system:return SimpleNamespace(st_mode=0o40755,st_uid=0)
        return original(p,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',metadata)
    monkeypatch.setattr(m.pwd,'getpwuid',lambda uid:SimpleNamespace(pw_dir=str(tmp_path)))
    return tmp_path


def record():return {'operator_uid':os.getuid(),'prepared':{'task_id':'task-one','commit':'a'*40}}


def test_default_uses_account_home_and_exact_handoff_not_home_environment(home,monkeypatch):
    monkeypatch.setenv('HOME','/tmp/attacker')
    first=m.workspace_path(record())
    assert first.parent==home and first.name.startswith('.rras-review-')
    assert first==m.workspace_path(record())
    other=record();other['prepared']['commit']='b'*40
    assert m.workspace_path(other)!=first
    assert not first.exists()  # selection creates/adopts nothing


@pytest.mark.parametrize('mode',[0o775,0o777,0o757])
def test_writable_ancestor_refused_before_import(home,mode):
    unsafe=home/'unsafe';unsafe.mkdir(mode=mode);unsafe.chmod(mode)
    with patch.object(m,'read',return_value=(record(),b'not a bundle')),patch.object(m,'git') as git:
        with pytest.raises(ValueError,match='ancestor'):m.import_review('/fixture',unsafe/'task')
        git.assert_not_called()
    assert not (unsafe/'task').exists()
    assert unsafe.stat().st_mode&0o777==mode  # no chmod repair


def test_symlink_ancestor_refused(home):
    target=home/'actual';target.mkdir(mode=0o700)
    link=home/'link';link.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='ancestor'):m.workspace_path(record(),link/'task')


def test_relative_path_and_worker_identity_refused(home):
    with pytest.raises(ValueError,match='absolute'):m.workspace_path(record(),'relative')
    with patch.object(m.os,'getuid',return_value=996):
        with pytest.raises(ValueError,match='operator'):m.workspace_path({'operator_uid':996})


def test_existing_default_workspace_is_never_adopted(home):
    path=m.workspace_path(record());path.mkdir(mode=0o700)
    (path/'sentinel').write_text('retain')
    with patch.object(m,'read',return_value=(record(),b'not a bundle')),patch.object(m,'git') as git:
        with pytest.raises(ValueError,match='fresh'):m.import_review('/fixture')
        git.assert_not_called()
    assert (path/'sentinel').read_text()=='retain'


def test_publish_rechecks_unsafe_parent_before_transport(home):
    unsafe=home/'unsafe';unsafe.mkdir(mode=0o700);task=unsafe/'task';task.mkdir(mode=0o700);unsafe.chmod(0o775)
    with patch.object(m,'read',return_value=(record(),b'')):
        with pytest.raises(ValueError,match='ancestor'):m.publish('/fixture',task)


def test_default_workspace_real_bundle_and_local_transport(home,fixture):
    from test_rras_native_publication_handoff import package
    item,source=package(fixture,home)
    data=(source/'review.bundle').read_bytes()
    with patch.object(m,'read',return_value=(item,data)):
        prepared=m.import_review(source)
        workspace=Path(prepared['checkout']).parent
        assert workspace==m.workspace_path(item)
        assert workspace.stat().st_mode&0o777==0o700
        result=m.publish(source)
        assert result['status']=='published'
        with pytest.raises(ValueError):m.publish(source)
