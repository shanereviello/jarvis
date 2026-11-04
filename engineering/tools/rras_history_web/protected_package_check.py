"""Emit the stdlib verifier/bootstrap and exact committed probe. No root action."""
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess


def emit(source,commit,destination):
    source=Path(source).resolve(strict=True)
    if type(commit) is not str or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact tooling commit required')
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(source),*args],stderr=subprocess.PIPE,
        env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'},timeout=30)
    if git('rev-parse','HEAD').decode().strip()!=commit:raise ValueError('tooling commit differs')
    folder='engineering/tools/rras_history_web/'
    verifier=git('show',commit+':'+folder+'production_package.py').decode().split('\ndef build(',1)[0]
    probe=git('show',commit+':'+folder+'protected_package_probe.py')
    stage=git('show',commit+':'+folder+'stage_protected_package_check.py').decode()
    raw=(verifier+'\nPROBE_BYTES='+repr(probe)+'\n'+stage).encode()
    compile(raw,str(destination),'exec')
    with Path(destination).open('xb') as stream:stream.write(raw)
    return dict(helper_sha256=hashlib.sha256(raw).hexdigest(),probe_sha256=hashlib.sha256(probe).hexdigest(),tooling_commit=commit)
