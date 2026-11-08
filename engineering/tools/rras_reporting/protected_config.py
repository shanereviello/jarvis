"""Bounded root-controlled policy and private credential reads; no environment."""
import importlib.util
import os
from pathlib import Path
import stat


def read(path,*,maximum,require_root=False):
    p=Path(path);info=p.lstat();mode=stat.S_IMODE(info.st_mode)
    if (not p.is_absolute() or p.resolve()!=p or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or
            info.st_uid not in (0,os.getuid()) or (require_root and info.st_uid!=0) or
            mode not in (0o400,0o600,0o440,0o640) or (mode&0o040 and info.st_gid!=os.getgid()) or
            mode&0o007 or info.st_size>maximum):raise ValueError('protected bounded installed file required')
    owners=(0,) if info.st_uid==0 else (0,os.getuid())
    for parent in (p.parent,*p.parent.parents):
        value=parent.lstat()
        if not stat.S_ISDIR(value.st_mode) or value.st_uid not in owners:
            raise ValueError('protected installed file ancestry required')
        if value.st_mode&0o022 and not (value.st_uid==0 and value.st_mode&stat.S_ISVTX and parent!=p.parent):
            raise ValueError('installed file ancestry is writable')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        if (opened.st_dev,opened.st_ino,opened.st_uid,opened.st_gid,opened.st_mode,opened.st_size)!=(
                info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_size):raise ValueError('installed file changed')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(maximum+1)
        if len(raw)>maximum:raise ValueError('bounded installed file required')
        return raw
    finally:os.close(fd)


def decode(path,*,maximum=8*1024*1024,require_root=True):
    spec=importlib.util.spec_from_file_location('protected_config_contract',Path(__file__).resolve().parents[1]/'rras_history/contract.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.decode(read(path,maximum=maximum,require_root=require_root),max_bytes=maximum)
