"""Real disposable Git staging; ownership readers mocked, no service/model/network."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
import pytest
import test_managed_events as managed
from test_workflow_finish import case
from test_workflow_publication import pubcase

def pytest_generate_tests(metafunc):
    if 'case' in metafunc.fixturenames:
        metafunc.parametrize('case',[{'publication_remote':'git@github.com:fixture/library.git'}],indirect=True)


@pytest.fixture
def staged(pubcase):
    x=pubcase;m=managed.module('validation_workspace');actual=m.local
    reader=SimpleNamespace(root_bytes=lambda path,limit:Path(path).read_bytes())
    modules={'workflow_finish':x.c.f,'workflow_publication':x.p,'approved_launch':x.c.x.l,'publication_custody':reader}
    with patch.object(m,'local',side_effect=lambda name:modules.get(name) or actual(name)),patch.object(m,'administrator'):
        root=x.root/'validation'
        def stage():
            with patch.object(m.os,'getuid',return_value=0),patch.object(m.os,'geteuid',return_value=0):
                return m.stage(x.c.custody,x.package,root)
        def verify():
            with patch.object(m.os,'getuid',return_value=0),patch.object(m.os,'geteuid',return_value=0):
                return m.verify(x.c.custody,x.package,root)
        yield SimpleNamespace(m=m,x=x,root=root,stage=stage,verify=verify)


def test_protected_stage_contains_exact_review_unstaged(staged):
    s=staged;r=s.stage();receipt=s.verify();repo=s.root/'repo'
    assert r['staged'] and not r['service_started'] and not r['worker_access_granted']
    assert s.root.stat().st_mode&0o777==0o700
    assert s.m.git(repo,'rev-parse','HEAD').decode().strip()==s.x.proof['baseline']
    assert s.m.git(repo,'diff','--name-only').decode().strip()=='src/library.py'
    assert (repo/'src/library.py').read_text()=='value = 2\n'
    assert receipt['plan']['identity']['commit']==s.x.proof['commit']
    assert not receipt['publication_authorized']
    with pytest.raises(ValueError):s.stage()


@pytest.mark.parametrize('mutation',['file','untracked','symlink','index','config','head','bundle','receipt'])
def test_changed_private_stage_refused(staged,mutation):
    s=staged;s.stage();repo=s.root/'repo'
    if mutation=='file':(repo/'src/library.py').write_text('tampered\n')
    elif mutation=='untracked':(repo/'extra.txt').write_text('extra\n')
    elif mutation=='symlink':(repo/'src/library.py').unlink();(repo/'src/library.py').symlink_to('/etc/passwd')
    elif mutation=='index':s.m.git(repo,'add','--','src/library.py')
    elif mutation=='config':s.m.git(repo,'config','core.filemode','false')
    elif mutation=='head':s.m.git(repo,'reset','--soft',s.x.proof['commit'])
    elif mutation=='bundle':(s.root/'review.bundle').write_bytes(b'corrupt')
    else:
        p=s.root/'validation-stage.json';d=json.loads(p.read_bytes());d['plan']['argv']=['/bin/true'];p.write_text(json.dumps(d))
    with pytest.raises(ValueError):s.verify()


def test_failed_stage_preserved_not_reused(staged):
    s=staged
    with patch.object(s.m,'reconstruct',side_effect=ValueError('fixture failure')),pytest.raises(ValueError):s.stage()
    assert (s.root/'review.bundle').exists() and not (s.root/'validation-stage.json').exists()
    with pytest.raises(ValueError):s.stage()


def test_administrator_boundary_is_explicit():
    m=managed.module('validation_workspace')
    with patch.object(m.os,'geteuid',return_value=996),pytest.raises(ValueError):m.administrator()


@pytest.fixture
def tree(tmp_path):
    m=managed.module('validation_workspace');repo=tmp_path/'repo';repo.mkdir();m.git(None,'init','--quiet',str(repo))
    def commit():
        m.git(repo,'add','--all');m.git(repo,'-c','user.name=fixture','-c','user.email=fixture@example.test','commit','--quiet','-m','fixture')
        return m.git(repo,'rev-parse','HEAD').decode().strip()
    (repo/'existing.txt').write_text('baseline\n');(repo/'.gitignore').write_text('ignored.txt\n');baseline=commit()
    actual=m.local;reader=SimpleNamespace(root_bytes=lambda path,limit:Path(path).read_bytes())
    with patch.object(m,'local',side_effect=lambda name:reader if name=='publication_custody' else actual(name)):
        yield SimpleNamespace(m=m,repo=repo,baseline=baseline,commit=commit)


@pytest.mark.parametrize('name',['new.txt','ignored.txt'])
def test_new_file_whitespace_is_actually_checked(tree,name):
    t=tree;(t.repo/name).write_text('bad trailing whitespace   \n');t.m.git(t.repo,'add','--force','--',name);commit=t.commit()
    files=t.m.reconstruct(t.repo,commit,t.baseline,[name]);assert name in files
    with pytest.raises(subprocess.CalledProcessError):t.m.git(t.repo,'diff','--check')
    assert t.m.git(t.repo,'diff','--name-only').decode().strip()==name
    assert t.m.git(t.repo,'diff','--cached','--name-only')==b''


def test_deleted_and_executable_files_preserve_tree(tree):
    t=tree;(t.repo/'existing.txt').unlink();p=t.repo/'run.sh';p.write_text('#!/bin/sh\nexit 0\n');p.chmod(0o755);commit=t.commit()
    result=t.m.reconstruct(t.repo,commit,t.baseline,['existing.txt','run.sh'])
    assert 'existing.txt' not in result and result['run.sh']['mode']=='100755'
    assert t.m.filesystem(t.repo)==result


def test_scope_is_rechecked_before_checkout(tree):
    t=tree;(t.repo/'existing.txt').write_text('changed\n');commit=t.commit()
    with pytest.raises(ValueError):t.m.reconstruct(t.repo,commit,t.baseline,['other.txt'])


def test_special_entries_refused_before_checkout(tree):
    t=tree;(t.repo/'link').symlink_to('/etc/passwd');commit=t.commit()
    with pytest.raises(ValueError):t.m.reconstruct(t.repo,commit,t.baseline,['link'])


def test_non_single_parent_review_refused(tree):
    t=tree;(t.repo/'existing.txt').write_text('second\n');t.commit();(t.repo/'existing.txt').write_text('third\n');commit=t.commit()
    with pytest.raises(ValueError):t.m.reconstruct(t.repo,commit,t.baseline,['existing.txt'])


def test_tree_bounds_are_enforced_without_large_fixture(tree):
    t=tree
    with patch.object(t.m,'MAX_FILES',1),pytest.raises(ValueError):t.m.inventory(t.repo,t.baseline)
    with patch.object(t.m,'MAX_TOTAL',1),pytest.raises(ValueError):t.m.inventory(t.repo,t.baseline)


def test_hardlinked_worktree_content_refused(tree):
    import os
    t=tree;os.link(t.repo/'existing.txt',t.repo/'linked.txt')
    with pytest.raises(ValueError):t.m.filesystem(t.repo)


def test_stage_permissions_must_remain_private(staged):
    s=staged;s.stage();s.root.chmod(0o750)
    with pytest.raises(ValueError):s.verify()


def test_changed_executable_mode_is_detected(staged):
    s=staged;s.stage();(s.root/'repo/src/library.py').chmod(0o755)
    with pytest.raises(ValueError):s.verify()
