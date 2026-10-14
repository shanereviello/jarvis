"""Explicit per-run context bridge to native Hermes show/complete; no lifecycle owner."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

TRUSTED_PYTHON="/opt/rras-engineering/releases/native-10/venv/bin/python"


def write_context(path, task, run_id, home, board, python):
    data={'schema_version':1,'task':task,'run_id':run_id,'home':str(home),
          'board':str(board),'python':str(python)}
    path=Path(path)
    fd,tmp=tempfile.mkstemp(prefix='.task-context-',dir=path.parent)
    try:
        os.fchmod(fd,0o400)
        with os.fdopen(fd,'w') as f:
            json.dump(data,f);f.flush();os.fsync(f.fileno())
        os.link(tmp,path)  # No overwrite; publish complete context atomically.
    finally:os.unlink(tmp)


def read_context(path):
    path=Path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o400 or not 0<s.st_size<=8192:
            raise ValueError('private read-only task context required')
        c=json.loads(os.read(fd,8193))
    finally:os.close(fd)
    if (set(c)!={'schema_version','task','run_id','home','board','python'} or c['schema_version']!=1
            or not isinstance(c['task'],str) or not re.fullmatch(r't_[a-zA-Z0-9]+',c['task'])
            or type(c['run_id']) is not int or c['run_id']<1):
        raise ValueError('invalid task/run context')
    root=path.parent.resolve(strict=True)
    for key in ('home','board'):
        p=Path(c[key])
        if not p.is_absolute() or p.resolve()!=p or not p.is_relative_to(root):
            raise ValueError('context path outside assigned root')
    # Installation preflight owns release verification; never accept a context-selected runtime.
    if c['python']!=TRUSTED_PYTHON:raise ValueError('unreviewed Python path')
    return c


def invoke(path, operation, result=None):
    if operation not in ('show','complete'):raise ValueError('native operation not admitted')
    c=read_context(path)
    env={'PATH':'/usr/bin:/bin','HOME':c['home'],'HERMES_HOME':c['home'],
         'HERMES_KANBAN_DB':c['board'],'HERMES_KANBAN_TASK':c['task'],
         'HERMES_KANBAN_RUN_ID':str(c['run_id']),'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'}
    args=[c['python'],'-B','-m','hermes_cli.main','kanban',operation,c['task']]
    if operation=='show':args+=['--json']
    else:
        if not isinstance(result,str) or not result or len(result)>2048:raise ValueError('bounded result required')
        args+=['--result',result]
    return subprocess.run(args,env=env,stdin=subprocess.DEVNULL,timeout=20).returncode

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--context',required=True)
    p.add_argument('operation',choices=['show','complete']);p.add_argument('--result')
    a=p.parse_args();raise SystemExit(invoke(a.context,a.operation,a.result))
