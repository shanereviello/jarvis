"""Extract only OPENAI_API_KEY from the existing private engineering .env.

This root-only provisioning helper makes no API call and never prints or returns
the secret. It writes one dedicated root-owned file for systemd LoadCredential;
the runtime adapter and Jarvis account do not receive it.
"""
import argparse
import os
from pathlib import Path
import secrets
import stat


def parse(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= 1024 * 1024:
        raise ValueError('bounded private dotenv input required')
    matches=[]
    for line in raw.decode('utf-8').splitlines():
        item=line.strip()
        if not item or item.startswith('#'):
            continue
        if item.startswith('export '):
            item=item[7:].lstrip()
        key,separator,value=item.partition('=')
        if separator and key.strip()=='OPENAI_API_KEY':
            value=value.strip()
            if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):
                value=value[1:-1]
            elif value.startswith(('"',"'")) or value.endswith(('"',"'")):
                raise ValueError('quoted API key syntax is incomplete')
            encoded=value.encode('utf-8')
            if not 32<=len(encoded)<=4096 or any(byte<33 or byte>126 for byte in encoded):
                raise ValueError('bounded printable API key required')
            matches.append(encoded)
    if len(matches)!=1:
        raise ValueError('exactly one OPENAI_API_KEY entry required')
    return matches[0]


def extract(source,destination,*,source_uid):
    if os.geteuid()!=0:
        raise PermissionError('root execution required')
    source=Path(source);destination=Path(destination)
    if (not source.is_absolute() or source.resolve()!=source or not destination.is_absolute() or
            destination.resolve(strict=False)!=destination):
        raise ValueError('canonical absolute paths required')
    info=source.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=source_uid or info.st_nlink!=1 or
            stat.S_IMODE(info.st_mode)!=0o600):
        raise ValueError('existing private engineering API source required')
    raw=bytearray()
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        if (opened.st_dev,opened.st_ino,opened.st_uid,opened.st_mode,opened.st_size)!=(
                info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_size):
            raise ValueError('API source changed during provisioning')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw.extend(stream.read(1024*1024+1))
    finally:os.close(fd)
    try:secret=parse(bytes(raw))
    finally:raw[:]=b'\0'*len(raw)
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError('preinstalled root-owned credential directory required')
    parent=destination.parent.stat()
    if parent.st_uid!=0 or parent.st_mode&0o022:
        raise ValueError('protected root-owned credential directory required')
    if destination.exists() or destination.is_symlink():
        previous=destination.lstat()
        if (not stat.S_ISREG(previous.st_mode) or previous.st_uid!=0 or previous.st_nlink!=1 or
                stat.S_IMODE(previous.st_mode)!=0o400):
            raise ValueError('existing dedicated credential is not safely replaceable')
    temporary=destination.with_name('.'+destination.name+'.'+secrets.token_hex(8)+'.next')
    try:
        fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC,0o400)
        try:
            with os.fdopen(fd,'wb',closefd=False) as stream:
                stream.write(secret);stream.flush();os.fsync(stream.fileno())
        finally:os.close(fd)
        os.replace(temporary,destination)
    finally:
        secret=b'\0'*len(secret)
        try:temporary.unlink()
        except FileNotFoundError:pass
    directory=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:os.fsync(directory)
    finally:os.close(directory)
    result=destination.lstat()
    if result.st_uid!=0 or stat.S_IMODE(result.st_mode)!=0o400 or result.st_nlink!=1:
        raise ValueError('dedicated root-only credential verification failed')
    return dict(prepared=True,models_started=0,api_calls=0,secret_printed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--source-uid',type=int,required=True)
    args=parser.parse_args()
    try:print(__import__('json').dumps(extract(args.source,args.destination,source_uid=args.source_uid)))
    except Exception:parser.exit(1,'Credential preparation refused; no API call was made.\n')


if __name__=='__main__':main()
