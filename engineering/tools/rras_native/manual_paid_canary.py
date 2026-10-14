"""Explicitly authorized single paid task. Never run during source preparation."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys


def delivered_key(path):
    directory=os.environ.get('CREDENTIALS_DIRECTORY')
    if not directory or Path(path).resolve().parent!=Path(directory).resolve():
        raise ValueError('systemd delivered credential required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or not 1<=s.st_size<=16384 or s.st_uid!=os.getuid() or s.st_mode & 0o077:
            raise ValueError('private delivered credential required')
        token=os.read(fd,16385).decode().strip()
        if not token or any(c.isspace() for c in token) or '\x00' in token:
            raise ValueError('invalid credential bytes')
        return token
    finally:os.close(fd)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','python','profile','codex-config','work','credential'):p.add_argument('--'+n,required=True)
    p.add_argument('--authorize-one-paid-task',action='store_true')
    x=p.parse_args()
    if not x.authorize_one_paid_task or os.getuid()!=996:
        p.error('explicit paid authorization and UID996 required before reading credentials')
    token=delivered_key(x.credential)
    os.environ.pop('CREDENTIALS_DIRECTORY',None)
    s=importlib.util.spec_from_file_location('integrated',Path(__file__).with_name('probe_integrated_runner.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    try:
        r=m.run(x.source,x.python,x.profile,x.work,'paid',True,token,x.codex_config,paid=True)
    except Exception as exc:
        print(json.dumps({'success':False,'error_type':type(exc).__name__,'retain_work':x.work}));sys.exit(1)
    print(json.dumps(r));sys.exit(0 if r['success'] else 1)
