"""Offline package rejects unsafe, substituted and nonregular source bytes."""
import hashlib
import os
from pathlib import Path
import subprocess
import pytest
from test_engineering_history_local import module

p=module('review_tools_package')


@pytest.fixture
def candidate(tmp_path):
    root=tmp_path/'candidate';root.mkdir()
    files={name:b'fixture\n' for name in p.SOURCE_FILES};files['vendor/dependency.py']=b'pass\n'
    for name,raw in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={'contract':'engineering-review-tools.v1','scope':'passive-private-export-intake','source_commit':'a'*40,
        'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
    raw=p.encoded(manifest);(root/p.MANIFEST).write_bytes(raw)
    return root,hashlib.sha256(raw).hexdigest(),manifest


def rewrite(root,manifest):
    raw=p.encoded(manifest);(root/p.MANIFEST).write_bytes(raw);return hashlib.sha256(raw).hexdigest()


def test_exact_offline_package(candidate):
    root,sha,manifest=candidate
    found,files=p.verify(root,sha)
    assert found==manifest and set(files)==set(manifest['files'])


@pytest.mark.parametrize('name',['../escape','/absolute','vendor/../escape','vendor/hook.pth','vendor/cache.pyc','engineering/tools/rras_history/approval.py','vendor//duplicate.py'])
def test_unsafe_member_refused(candidate,name):
    root,_,manifest=candidate;manifest['files'][name]='f'*64
    with pytest.raises(ValueError):p.verify(root,rewrite(root,manifest))


def test_duplicate_manifest_members_refused(candidate):
    root,_,_=candidate;raw=b'{"files":{},"files":{}}\n';(root/p.MANIFEST).write_bytes(raw)
    with pytest.raises(ValueError,match='duplicate'):p.verify(root,hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('kind',['changed','symlink','hardlink','fifo'])
def test_nonregular_or_changed_member_refused(candidate,tmp_path,kind):
    root,sha,_=candidate;path=root/'vendor/dependency.py'
    if kind=='changed':path.write_text('changed')
    else:
        path.unlink();other=tmp_path/'outside';other.write_text('pass\n')
        if kind=='symlink':path.symlink_to(other)
        elif kind=='hardlink':os.link(other,path)
        else:os.mkfifo(path)
    with pytest.raises(ValueError):p.verify(root,sha)


def test_missing_core_and_wrong_scope_refused(candidate):
    root,_,manifest=candidate;manifest['scope']='run-worker'
    with pytest.raises(ValueError):p.verify(root,rewrite(root,manifest))
    manifest['scope']='passive-private-export-intake';manifest['files'].pop(next(iter(p.SOURCE_FILES)))
    with pytest.raises(ValueError):p.verify(root,rewrite(root,manifest))


def test_build_reads_committed_bytes_and_offline_vendor(tmp_path):
    source=tmp_path/'source';source.mkdir();vendor=tmp_path/'vendor';vendor.mkdir();(vendor/'library.py').write_text('pass\n')
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],stderr=subprocess.PIPE)
    git('init','-q')
    for name in p.SOURCE_FILES:
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('committed\n')
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','fixture')
    commit=git('rev-parse','HEAD').decode().strip()
    name=next(iter(p.SOURCE_FILES));(source/name).write_text('uncommitted\n')
    result=p.build(source,vendor,tmp_path/'output',commit)
    assert result['installed'] is False and (Path(result['candidate'])/name).read_text()=='committed\n'
    with pytest.raises(ValueError):p.build(source,vendor,tmp_path/'wrong','e'*40)
    assert not (tmp_path/'wrong').exists()


def test_entry_verifies_before_dispatch_and_forwards_help(candidate,monkeypatch,capsys):
    root,_,manifest=candidate;entry=module('review_tools_entry')
    path=root/'engineering/tools/rras_history/review_document_cli.py'
    path.write_text('def main(argv):\n print("dispatched", argv)\n')
    manifest['files'][path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    sha=rewrite(root,manifest)
    monkeypatch.setattr(entry,'__file__',str(root/'engineering/tools/rras_history/review_tools_entry.py'))
    entry.run(['--manifest-sha256',sha,'intake','--help'])
    assert "dispatched ['--help']" in capsys.readouterr().out
    path.write_text('raise AssertionError("changed code executed")')
    with pytest.raises(ValueError,match='payload changed'):entry.run(['--manifest-sha256',sha,'intake'])
    with pytest.raises(ValueError,match='manifest changed'):entry.run(['--manifest-sha256','f'*64,'export'])
