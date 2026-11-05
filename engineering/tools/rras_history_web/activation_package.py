"""Emit committed stdlib activation controller. No administrator actions here."""
import hashlib
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
    prefix=git('show',commit+':'+folder+'production_package.py').decode().split('\ndef build(',1)[0]
    suffix=git('show',commit+':'+folder+'activation.py').decode();raw=(prefix+'\n'+suffix).encode();compile(raw,str(destination),'exec')
    with Path(destination).open('xb') as stream:stream.write(raw)
    return dict(helper_sha256=hashlib.sha256(raw).hexdigest(),tooling_commit=commit)
