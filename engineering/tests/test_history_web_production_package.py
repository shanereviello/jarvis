"""Production payload derivation, dependency inventory and inactive-only artifacts."""
import hashlib
import json
from pathlib import Path
import pytest
from test_history_web import web

package=web('production_package')


def fixture(tmp_path):
    candidate=tmp_path/'candidate';candidate.mkdir()
    files={name:b'# synthetic source\n' for name in package.SOURCE_FILES}
    files['engineering/requirements-history-web-lock.txt']=b'example==1.0\n'
    files['vendor/example-1.0.dist-info/METADATA']=b'Metadata-Version: 2.1\nName: example\nVersion: 1.0\n\n'
    files['vendor/example.py']=b'pass\n'
    template=(Path(__file__).resolve().parents[1]/'config/history-web/rras-engineering-history-web.service.in').read_bytes()
    files['engineering/config/history-web/rras-engineering-history-web.service.in']=template
    digest=package.payload_identity(files);release='/opt/rras-engineering/releases/history-web-'+digest[:12]
    files.update(package.artifacts(release,digest,template,package.dependencies(files)))
    for name,raw in files.items():
        path=candidate/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest=dict(contract='engineering-history-web-runtime.v1',source_commit='a'*40,release=release,payload_sha256=digest,
        stage_authorized=False,activation_authorized=False,files={name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())})
    raw=package.encoded(manifest);(candidate/package.MANIFEST).write_bytes(raw)
    return candidate,hashlib.sha256(raw).hexdigest(),manifest


def rehash(candidate,manifest,name,raw):
    (candidate/name).write_bytes(raw);manifest['files'][name]=hashlib.sha256(raw).hexdigest()
    content=package.encoded(manifest);(candidate/package.MANIFEST).write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_inactive_unit_and_plan_are_derived_without_config_or_action(tmp_path):
    candidate,sha,manifest=fixture(tmp_path);actual,files=package.verify(candidate,sha)
    plan=json.loads(files['deployment/install-plan.json']);unit=files['deployment/rras-engineering-history-web.service'].decode()
    assert actual==manifest and plan['configuration_included'] is False
    assert plan['proposed_grant']=={'uid':993,'private_read':['jarvis'],'write':[]}
    for field in ('stage_authorized','activation_authorized','cloudflare_change_authorized','unit_enabled','unit_started','grant_applied'):assert plan[field] is False
    assert package.PYTHON in unit and 'runtime_entry.py --config' in unit and '@' not in unit
    assert not any('host_probe' in name or '/store.py' in name or '/production_entry.py' in name for name in files)
    assert not any(name.endswith('config.json') for name in files)


@pytest.mark.parametrize('name',['../escape','vendor/a.pth','vendor/bin/tool','engineering/tools/rras_history/store.py','engineering/tools/rras_history_web/host_probe.py'])
def test_runtime_cannot_include_fixture_database_or_executable_search_paths(name):
    with pytest.raises(ValueError):package.safe_name(name)


def test_changed_runtime_bytes_refused(tmp_path):
    candidate,sha,_=fixture(tmp_path);(candidate/'vendor/example.py').write_bytes(b'changed')
    with pytest.raises(ValueError):package.verify(candidate,sha)


def test_plan_cannot_add_authority_even_when_member_digest_is_updated(tmp_path):
    candidate,sha,manifest=fixture(tmp_path);name='deployment/install-plan.json'
    plan=json.loads((candidate/name).read_bytes());plan['activation_authorized']=True
    sha=rehash(candidate,manifest,name,package.encoded(plan))
    with pytest.raises(ValueError):package.verify(candidate,sha)


def test_template_artifact_cannot_add_commands(tmp_path):
    candidate,sha,manifest=fixture(tmp_path);name='deployment/rras-engineering-history-web.service'
    sha=rehash(candidate,manifest,name,(candidate/name).read_bytes()+b'ExecStartPost=/usr/bin/true\n')
    with pytest.raises(ValueError):package.verify(candidate,sha)


def test_dependency_version_mismatch_refused(tmp_path):
    candidate,sha,manifest=fixture(tmp_path)
    sha=rehash(candidate,manifest,'vendor/example-1.0.dist-info/METADATA',b'Name: example\nVersion: 2.0\n')
    with pytest.raises(ValueError,match='dependency inventory'):package.verify(candidate,sha)


def test_release_identity_cannot_be_redirected(tmp_path):
    candidate,sha,manifest=fixture(tmp_path);manifest['release']='/tmp/not-protected'
    raw=package.encoded(manifest);(candidate/package.MANIFEST).write_bytes(raw)
    with pytest.raises(ValueError):package.verify(candidate,hashlib.sha256(raw).hexdigest())


def test_bootstrap_refuses_different_interpreter_before_importing_payload(monkeypatch):
    bootstrap=web('runtime_entry');monkeypatch.setattr(bootstrap.sys,'version_info',(3,12,0))
    with pytest.raises(SystemExit,match='interpreter version refused'):bootstrap.main([])
