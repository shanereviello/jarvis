"""Real bounded files and Git provenance; root protection explicitly faked here."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def fixture(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('bootstrap',ROOT/'tools/rras_native/workflow_upgrade_bootstrap.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    candidate=tmp_path/'candidate';candidate.mkdir();source=tmp_path/'source';source.mkdir();releases=tmp_path/'releases';releases.mkdir()
    for name in m.FILES:
        raw=(ROOT/'tools/rras_native'/name).read_bytes();(candidate/name).write_bytes(raw)
        target=source/m.SOURCE_PREFIX/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],stderr=subprocess.PIPE)
    git('init','-b','main');git('config','user.email','fixture@example.invalid');git('config','user.name','Fixture');git('add','.');git('commit','-m','fixture')
    manifest={'schema_version':1,'scope':'workflow-upgrade-tools-only','source_commit':git('rev-parse','HEAD').decode().strip(),
        'files':{name:m.sha((candidate/name).read_bytes()) for name in m.FILES}}
    def seal():
        raw=m.encoded(manifest);(candidate/'deployment-tools-manifest.json').write_bytes(raw);return m.sha(raw)
    digest=seal();monkeypatch.setattr(m,'SOURCE',source);monkeypatch.setattr(m,'RELEASES',releases)
    monkeypatch.setattr(m,'administrator',lambda:None);monkeypatch.setattr(m,'protected',lambda path:Path(path))
    return SimpleNamespace(m=m,candidate=candidate,source=source,releases=releases,manifest=manifest,digest=digest,seal=seal)


def test_roundtrip_installs_protected_code_only_and_inspects_read_only(fixture):
    f=fixture;m=f.m;answer=m.stage(f.candidate,f.digest);target=Path(answer['release'])
    assert answer['phase']=='workflow_upgrade_tools_staged' and answer['api_calls']==0
    assert answer['services_changed'] is False and answer['activation_authorized'] is False
    for name in m.FILES:
        assert (target/name).read_bytes()==(f.candidate/name).read_bytes()
        assert (target/name).stat().st_mode&0o777==0o444
    before={p:p.read_bytes() for p in target.iterdir()}
    assert m.inspect(target,f.digest)['phase']=='workflow_upgrade_tools_verified'
    assert before=={p:p.read_bytes() for p in target.iterdir()}
    with pytest.raises(ValueError,match='exists'):m.stage(f.candidate,f.digest)

@pytest.mark.parametrize('kind',['digest','payload','scope','extra_file','bad_source','traversal'])
def test_bad_candidate_refused_before_any_destination(fixture,kind):
    f=fixture
    if kind=='digest':f.digest='0'*64
    elif kind=='payload':(f.candidate/f.m.FILES[0]).write_bytes(b'changed')
    elif kind=='scope':f.manifest['scope']='activate';f.digest=f.seal()
    elif kind=='extra_file':f.manifest['files']['extra.py']='0'*64;f.digest=f.seal()
    elif kind=='bad_source':f.manifest['source_commit']='main';f.digest=f.seal()
    else:f.manifest['files']['../escape.py']=f.manifest['files'].pop(f.m.FILES[0]);f.digest=f.seal()
    with pytest.raises(ValueError):f.m.stage(f.candidate,f.digest)
    assert not list(f.releases.iterdir())


def test_verified_candidate_is_never_imported_or_evaluated(fixture):
    f=fixture;sentinel=f.releases/'SHOULD-NOT-EXIST';name=f.m.FILES[0]
    raw=('from pathlib import Path\nPath('+repr(str(sentinel))+').write_text("executed")\n').encode()
    (f.candidate/name).write_bytes(raw);f.manifest['files'][name]=f.m.sha(raw);f.digest=f.seal()
    assert f.m.verify(f.candidate,f.digest)[2][name]==raw
    with pytest.raises(ValueError,match='reviewed commit'):f.m.stage(f.candidate,f.digest)
    assert not sentinel.exists() and not list(f.releases.iterdir())


def test_source_must_be_ancestor_of_canonical_main(fixture):
    f=fixture;f.manifest['source_commit']='f'*40;f.digest=f.seal()
    with pytest.raises(subprocess.CalledProcessError):f.m.stage(f.candidate,f.digest)
    assert not list(f.releases.iterdir())

@pytest.mark.parametrize('kind',['symlink','hardlink','fifo','oversize'])
def test_special_or_unbounded_inputs_refused(fixture,kind):
    f=fixture;path=f.candidate/f.m.FILES[0];raw=path.read_bytes();path.unlink()
    if kind=='symlink':path.symlink_to(f.source/f.m.SOURCE_PREFIX/f.m.FILES[0])
    elif kind=='hardlink':os.link(f.source/f.m.SOURCE_PREFIX/f.m.FILES[0],path)
    elif kind=='fifo':os.mkfifo(path)
    else:path.write_bytes(b'x'*(f.m.LIMIT+1))
    with pytest.raises(ValueError):f.m.verify(f.candidate,f.digest)


def test_incomplete_copy_is_preserved_and_not_adopted(fixture,monkeypatch):
    f=fixture;actual=f.m.write
    def write(path,raw,mode):
        if path.name==f.m.FILES[1]:raise OSError('interrupted copy')
        return actual(path,raw,mode)
    monkeypatch.setattr(f.m,'write',write)
    with pytest.raises(OSError):f.m.stage(f.candidate,f.digest)
    target=next(f.releases.iterdir());assert (target/'started.json').exists() and (target/'staging-error.txt').exists()
    with pytest.raises(FileNotFoundError):f.m.inspect(target,f.digest)
    with pytest.raises(ValueError,match='exists'):f.m.stage(f.candidate,f.digest)

@pytest.mark.parametrize('kind',['bytes','mode','receipt'])
def test_inspection_refuses_changed_tools(fixture,kind):
    f=fixture;target=Path(f.m.stage(f.candidate,f.digest)['release'])
    if kind=='bytes':(target/f.m.FILES[0]).chmod(0o644);(target/f.m.FILES[0]).write_bytes(b'changed')
    elif kind=='mode':(target/f.m.FILES[0]).chmod(0o644)
    else:
        path=target/'complete.json';path.chmod(0o644);value=json.loads(path.read_bytes());value['manifest_sha256']='0'*64;path.write_bytes(f.m.encoded(value))
    with pytest.raises(ValueError):f.m.inspect(target,f.digest)


def test_git_trust_is_explicit_and_no_hooks_or_replace_objects(fixture,monkeypatch):
    f=fixture;calls=[];actual=subprocess.run
    def run(argv,**kwargs):calls.append(argv);return actual(argv,**kwargs)
    monkeypatch.setattr(f.m.subprocess,'run',run);f.m.stage(f.candidate,f.digest)
    assert len(calls)==3
    for argv in calls:
        assert '--no-replace-objects' in argv and 'safe.directory='+str(f.source) in argv and 'core.hooksPath=/dev/null' in argv

@pytest.mark.parametrize('raw',[b'{"schema_version":1,"schema_version":1}',b'{"value":NaN}'])
def test_ambiguous_manifest_json_refused(fixture,raw):
    f=fixture;(f.candidate/'deployment-tools-manifest.json').write_bytes(raw)
    with pytest.raises(ValueError):f.m.verify(f.candidate,f.m.sha(raw))
    assert not list(f.releases.iterdir())


def test_candidate_syntax_failure_is_not_executed_or_copied(fixture):
    f=fixture;name=f.m.FILES[0];raw=b'this is invalid Python syntax!\n';(f.candidate/name).write_bytes(raw)
    f.manifest['files'][name]=f.m.sha(raw);f.digest=f.seal()
    with pytest.raises(SyntaxError):f.m.stage(f.candidate,f.digest)
    assert not list(f.releases.iterdir())


def test_destination_protection_failure_precedes_mutation(fixture,monkeypatch):
    f=fixture
    def refuse(path):raise ValueError('unsafe destination')
    monkeypatch.setattr(f.m,'protected',refuse)
    with pytest.raises(ValueError,match='unsafe'):f.m.stage(f.candidate,f.digest)
    assert not list(f.releases.iterdir())
