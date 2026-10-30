"""First-install wrapper gate, exclusive publication and partial-failure evidence."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import pytest
from test_engineering_history_local import module
from test_history_review_tools_package import candidate

package=module('review_tools_package')


@pytest.fixture
def ready(tmp_path,monkeypatch,candidate,request):
    helper=tmp_path/'install.py'
    emitter=package.emit_events_install_helper if getattr(request,'param',None)=='events' else package.emit_install_helper
    sha=emitter(helper)
    assert hashlib.sha256(helper.read_bytes()).hexdigest()==sha
    spec=importlib.util.spec_from_file_location('install_adapter',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    root,digest,manifest=candidate;releases=tmp_path/'releases';releases.mkdir()
    release=releases/('history-review-tools-'+digest[:12]);root.rename(release)
    for path in release.rglob('*'):
        if path.is_file():path.chmod(0o444)
    staging=tmp_path/'staging';evidence=staging/digest;evidence.mkdir(parents=True)
    result={'phase':'inactive_review_tools_staged_and_host_verified','release':str(release),'source_commit':manifest['source_commit'],
        'manifest_sha256':digest,'files':len(manifest['files']),'cases':m.CASES,'api_calls':0}
    result.update({k:False for k in ('wrappers_installed','services_changed','production_history_changed','production_journal_changed','production_source_opened','automatic_retry')})
    (evidence/'complete.json').write_bytes(m.encoded(result));(evidence/'complete.json').chmod(0o600)
    target=tmp_path/'bin';target.mkdir()
    monkeypatch.setattr(m,'RELEASES',releases);monkeypatch.setattr(m,'STAGING',staging);monkeypatch.setattr(m,'INSTALLATIONS',tmp_path/'installations')
    monkeypatch.setattr(m,'TARGETS',{mode:target/('review-'+mode) for mode in m.TARGETS})
    monkeypatch.setattr(m,'protected',lambda p:None)
    monkeypatch.setattr(m.os,'getuid',lambda:0);monkeypatch.setattr(m.os,'geteuid',lambda:0)
    return m,digest,release,result


def test_preflight_is_readonly(ready):
    m,sha,_,_=ready
    assert m.install(sha,check_only=True)['mutations'] is False
    assert not m.INSTALLATIONS.exists() and not any(path.exists() for path in m.TARGETS.values())


def test_approval_required_before_preflight(ready,monkeypatch):
    m,sha,_,_=ready
    monkeypatch.setattr(m,'preflight',lambda *_:pytest.fail('must not preflight without approval'))
    with pytest.raises(ValueError,match='approval'):m.install(sha)


@pytest.mark.parametrize('kind',['missing','wrong-source','missing-case','mutated-services'])
def test_host_evidence_must_match_exact_staged_release(ready,kind):
    m,sha,_,result=ready;path=m.STAGING/sha/'complete.json'
    if kind=='missing':path.unlink()
    else:
        if kind=='wrong-source':result['source_commit']='f'*40
        elif kind=='missing-case':result['cases']=[]
        else:result['services_changed']=True
        path.write_bytes(m.encoded(result))
    with pytest.raises((ValueError,OSError)):m.install(sha,check_only=True)
    assert not m.INSTALLATIONS.exists()


def test_existing_target_and_pending_refused_without_overwrite(ready):
    m,sha,_,_=ready;target=m.TARGETS['export'];target.write_text('existing')
    with pytest.raises(ValueError):m.install(sha,approve_installation=True)
    assert target.read_text()=='existing' and not m.INSTALLATIONS.exists()
    target.unlink();pending=target.with_name('.'+target.name+'-'+sha[:12]+'.pending');pending.write_text('retained')
    with pytest.raises(ValueError):m.install(sha,approve_installation=True)
    assert pending.read_text()=='retained'


def test_exact_wrapper_install_and_replay_refused(ready):
    m,sha,release,_=ready;result=m.install(sha,approve_installation=True)
    assert result['phase']=='review_tools_wrappers_installed' and result['services_changed'] is False
    for mode,target in m.TARGETS.items():
        assert target.read_bytes()==m.wrapper(release,sha,mode)
        assert target.stat().st_nlink==1 and target.stat().st_mode&0o777==0o755
        subprocess.run(['/bin/sh','-n',str(target)],check=True)
        text=target.read_text();assert 'env -i' in text and '-I -B' in text and '"$@"' in text
    with pytest.raises(ValueError):m.install(sha,approve_installation=True)


def test_partial_failure_preserves_first_wrapper_and_stops(ready,monkeypatch):
    m,sha,_,_=ready;real=m.os.link;calls=[]
    def link(source,target,**kwargs):
        calls.append(target)
        if len(calls)==2:raise OSError('synthetic publication failure')
        return real(source,target,**kwargs)
    monkeypatch.setattr(m.os,'link',link)
    with pytest.raises(OSError):m.install(sha,approve_installation=True)
    assert m.TARGETS['export'].exists() and not m.TARGETS['intake'].exists()
    stopped=m.decode((m.INSTALLATIONS/sha/'stopped.json').read_bytes())
    assert stopped['completed_wrappers']==['export'] and stopped['automatic_rollback'] is False
    assert not (m.INSTALLATIONS/sha/'complete.json').exists()


def test_publication_race_never_replaces_target(ready,monkeypatch):
    m,sha,_,_=ready;real=m.os.link
    def raced(source,target,**kwargs):
        target.write_text('unexpected concurrent target')
        return real(source,target,**kwargs)
    monkeypatch.setattr(m.os,'link',raced)
    with pytest.raises(FileExistsError):m.install(sha,approve_installation=True)
    assert m.TARGETS['export'].read_text()=='unexpected concurrent target'


def test_changed_or_writable_release_refused(ready):
    m,sha,release,_=ready;path=release/'engineering/tools/rras_history/review_tools_entry.py';path.chmod(0o644)
    with pytest.raises(ValueError,match='readonly'):m.install(sha,check_only=True)
    path.write_text('changed');path.chmod(0o444)
    with pytest.raises(ValueError):m.install(sha,check_only=True)


@pytest.mark.parametrize('ready',['events'],indirect=True)
def test_events_profile_installs_only_new_command(ready):
    m,sha,release,_=ready
    assert set(m.TARGETS)=={'events'}
    result=m.install(sha,approve_installation=True)
    assert set(result['wrappers'])=={'events'}
    text=m.TARGETS['events'].read_text()
    assert ' events "$@"' in text and sha in text
    assert not (m.TARGETS['events'].parent/'review-export').exists()
    assert not (m.TARGETS['events'].parent/'review-intake').exists()


def test_emitted_events_profile_has_fixed_target_and_separate_journal(tmp_path):
    path=tmp_path/'events.py';package.emit_events_install_helper(path)
    spec=importlib.util.spec_from_file_location('events_profile',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.TARGETS=={'events':Path('/usr/local/bin/rras-history-managed-sync')}
    assert m.INSTALLATIONS==Path('/var/lib/rras-history-managed-sync-installations')
