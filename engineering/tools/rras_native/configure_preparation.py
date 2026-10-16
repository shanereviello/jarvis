"""Operator-only additive Hermes config update with exact-byte backup and rollback.

No gateway reload, worker launch, credentials, Docker, model calls or migrations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import yaml

NAME='rras-coding-preparation'

def digest(data): return hashlib.sha256(data).hexdigest()

def regular(path):
    path=Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):raise ValueError('regular file required')
    return path

def absent(path,data,mode=0o600):
    with Path(path).open('xb') as f:
        os.fchmod(f.fileno(),mode);f.write(data);f.flush();os.fsync(f.fileno())

def plan(bundle): return json.loads(regular(Path(bundle)/'plan.json').read_bytes())

def prepare(config,fragment,bundle,state,uid=1000,gid=1000):
    config=regular(config);fragment=regular(fragment);bundle=Path(bundle);state=Path(state)
    if not config.is_absolute() or config.resolve()!=config:raise ValueError('canonical config required')
    if state.exists() or state.is_symlink():raise ValueError('proposal state already exists; preserve it')
    before=config.read_bytes();current=yaml.safe_load(before);addition=yaml.safe_load(fragment.read_bytes())
    entry=addition['mcp_servers'][NAME]
    if set(addition)!= {'mcp_servers'} or set(addition['mcp_servers'])!={NAME}:raise ValueError('one additive entry required')
    if NAME in current.get('mcp_servers',{}):raise ValueError('entry already exists; preserve config')
    if not isinstance(current.get('mcp_servers'),dict):raise ValueError('existing MCP mapping required')
    current['mcp_servers'][NAME]=entry
    after=yaml.safe_dump(current,sort_keys=False,allow_unicode=True).encode()
    check=yaml.safe_load(after);del check['mcp_servers'][NAME]
    if check!=yaml.safe_load(before):raise ValueError('unrelated config change')
    bundle.mkdir(mode=0o700);bundle.chmod(0o700)
    absent(bundle/'config.original',before)
    absent(bundle/'config.candidate',after)
    s=config.stat()
    record={'config':str(config),'before_sha256':digest(before),'after_sha256':digest(after),
            'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),
            'state':str(state),'state_uid':uid,'state_gid':gid}
    absent(bundle/'plan.json',(json.dumps(record,sort_keys=True,indent=2)+'\n').encode())
    return {'status':'prepared','entry':NAME,'existing_entries_preserved':True}

def stage(bundle):
    b=Path(bundle);p=plan(b);target=Path(p['state'])
    if target.exists() or target.is_symlink():raise ValueError('state exists; do not adopt it')
    # Exact new allocation only, never change ownership of a parent/application.
    target.mkdir(mode=0o700);target.chmod(0o700);os.chown(target,p['state_uid'],p['state_gid'])
    s=target.stat()
    absent(b/'state-created.json',(json.dumps({'device':s.st_dev,'inode':s.st_ino})+'\n').encode())
    return {'status':'state_staged','configuration_changed':False}

def replace(config,data,p):
    # Temporary file is private and created next to the destination for atomic replace.
    fd,name=tempfile.mkstemp(prefix='.rras-config-',dir=config.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),p['mode']);os.fchown(f.fileno(),p['uid'],p['gid'])
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(name,config)
    finally:
        if Path(name).exists():Path(name).unlink()

def apply(bundle):
    b=Path(bundle);p=plan(b);config=regular(p['config']);target=Path(p['state'])
    if digest(config.read_bytes())!=p['before_sha256']:raise ValueError('config changed since backup; preserve it')
    original=regular(b/'config.original').read_bytes();candidate=regular(b/'config.candidate').read_bytes()
    if digest(original)!=p['before_sha256'] or digest(candidate)!=p['after_sha256']:raise ValueError('review bytes changed')
    if target.is_symlink():raise ValueError('state symlink refused')
    s=target.stat();created=json.loads(regular(b/'state-created.json').read_bytes())
    if not target.is_dir() or (s.st_dev,s.st_ino)!=(created['device'],created['inode']):raise ValueError('state allocation changed')
    if (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(p['state_uid'],p['state_gid'],0o700):raise ValueError('state metadata changed')
    replace(config,candidate,p)
    return {'status':'configured','gateway_reload_performed':False,'worker_execution_enabled':False}

def rollback(bundle):
    b=Path(bundle);p=plan(b);config=regular(p['config']);original=regular(b/'config.original').read_bytes()
    if digest(original)!=p['before_sha256']:raise ValueError('backup changed')
    now=digest(config.read_bytes())
    if now not in (p['before_sha256'],p['after_sha256']):raise ValueError('later config changes present; do not overwrite')
    if now!=p['before_sha256']:replace(config,original,p)
    return {'status':'original_config_restored','state_and_evidence_retained':True,'gateway_reload_performed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action',choices=['prepare','stage','apply','rollback'],required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--fragment',type=Path)
    parser.add_argument('--state',type=Path)
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error('administrator execution required')
    if args.action=='prepare':
        if not all((args.config,args.fragment,args.state)):parser.error('config, fragment, state required')
        result=prepare(args.config,args.fragment,args.bundle,args.state)
    else:result={'stage':stage,'apply':apply,'rollback':rollback}[args.action](args.bundle)
    print(json.dumps(result))
