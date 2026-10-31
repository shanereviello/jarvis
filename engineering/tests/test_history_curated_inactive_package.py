"""Pinned inactive production package and approval boundaries; no installation."""
import hashlib
import importlib.util
import subprocess
from pathlib import Path
import pytest
from test_engineering_history_local import module
p=module('curated_install_package')


@pytest.fixture
def candidate(tmp_path):
    root=tmp_path/'candidate';root.mkdir()
    files={name:b'fixture\n' for name in p.SOURCE_FILES|p.DEPLOYMENT};files['vendor/dependency.py']=b'pass\n'
    files['deployment/read-policy.json']=p.encoded({'contract':'engineering-curated-read-access.v1','principals':[{'uid':994,'repositories':['jarvis']}]})
    for name,raw in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={'contract':'engineering-curated-inactive.v1','scope':'inactive-empty-only','source_commit':'a'*40,
              'release':'/opt/rras-engineering/releases/curated-history-'+'b'*12,'reader_uid':994,'owner_uid':995,
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
    raw=p.encoded(manifest);(root/p.MANIFEST).write_bytes(raw)
    return root,hashlib.sha256(raw).hexdigest(),manifest


def test_exact_package_and_minimal_reader_policy(candidate):
    root,sha,manifest=candidate
    assert p.verify(root,sha)[0]==manifest
    assert p.READER==994 and p.OWNER==995
    with pytest.raises(ValueError):p.verify(root,'0'*64)
    (root/'vendor/dependency.py').write_text('changed')
    with pytest.raises(ValueError):p.verify(root,sha)


@pytest.mark.parametrize('kind',['symlink','hardlink','fifo'])
def test_nonregular_or_linked_payload_refused(candidate,tmp_path,kind):
    import os
    root,sha,_=candidate;path=root/'vendor/dependency.py';path.unlink()
    outside=tmp_path/'outside';outside.write_text('pass\n')
    if kind=='symlink':path.symlink_to(outside)
    elif kind=='hardlink':os.link(outside,path)
    else:os.mkfifo(path)
    with pytest.raises(ValueError):p.verify(root,sha)


def test_private_role_or_changed_scope_refused_even_with_new_digest(candidate):
    root,_,manifest=candidate;manifest['scope']='activate'
    raw=p.encoded(manifest);(root/p.MANIFEST).write_bytes(raw)
    with pytest.raises(ValueError):p.verify(root,hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):p.safe_name('vendor/../../escape')
    with pytest.raises(ValueError):p.safe_name('vendor/hook.pth')


def test_wrapper_prevents_release_override_and_shell_injection(tmp_path):
    raw=p.writer_wrapper('/opt/rras-engineering/releases/curated-history-'+'a'*12)
    wrapper=tmp_path/'wrapper';wrapper.write_bytes(raw)
    assert b'--release /opt/rras-engineering/releases/curated-history-' in raw
    assert b'"$2"' in raw and b'"$@"' not in raw
    assert subprocess.run(['/bin/sh','-n',str(wrapper)]).returncode==0
    result=subprocess.run(['/bin/sh',str(wrapper),'--release','/tmp/evil'],capture_output=True)
    assert result.returncode==1 and result.stdout==b''
    with pytest.raises(ValueError):p.writer_wrapper('/tmp/code\nexec /bin/sh')


def test_bootstrap_verification_and_explicit_inactive_approval(candidate,tmp_path):
    helper=tmp_path/'bootstrap.py';sha=p.emit_helper(helper)
    assert hashlib.sha256(helper.read_bytes()).hexdigest()==sha
    spec=importlib.util.spec_from_file_location('inactive_bootstrap',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    root,expected,manifest=candidate;assert m.verify(root,expected)[0]==manifest
    with pytest.raises(ValueError,match='approval'):m.install(root,expected)
    with pytest.raises(ValueError,match='administrator'):m.install(root,expected,check_only=True)
    assert not (root/'installed').exists()
    assert 'service_started' in helper.read_text() and 'activation_authorized' in helper.read_text()
