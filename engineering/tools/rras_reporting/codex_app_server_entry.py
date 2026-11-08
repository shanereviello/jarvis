"""Exec the pinned Codex App Server with one systemd-provided API credential."""
import argparse
import os
from pathlib import Path
import stat


def environment(credential_directory,credential_name,codex_home):
    directory=Path(credential_directory);home=Path(codex_home)
    if (not directory.is_absolute() or directory.resolve()!=directory or not home.is_absolute() or
            home.resolve()!=home or not home.is_dir() or home.is_symlink()):
        raise ValueError('fixed private systemd credential and Codex home required')
    path=directory/credential_name
    if (not credential_name or '/' in credential_name or credential_name in ('.','..') or path.is_symlink()):
        raise ValueError('one named systemd credential required')
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>4096:
        raise ValueError('bounded systemd credential required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        if (opened.st_dev,opened.st_ino,opened.st_mode,opened.st_size)!=(info.st_dev,info.st_ino,info.st_mode,info.st_size):
            raise ValueError('systemd credential changed')
        with os.fdopen(fd,'rb',closefd=False) as stream:value=stream.read(4097)
    finally:os.close(fd)
    if not 32<=len(value)<=4096 or any(byte<33 or byte>126 for byte in value):
        raise ValueError('bounded printable API credential required')
    return dict(PATH='/usr/bin:/bin',HOME=str(home),CODEX_HOME=str(home),LANG='C.UTF-8',
        RRAS_OPENAI_API_KEY=value.decode('ascii'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--codex-home',type=Path,required=True)
    parser.add_argument('--credential-name',default='openai-api-key')
    args=parser.parse_args()
    binary=args.binary
    if not binary.is_absolute() or binary.resolve()!=binary:parser.error('fixed installed executable required')
    info=binary.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or not os.access(binary,os.X_OK):
        parser.error('root-owned installed executable required')
    try:env=environment(os.environ.get('CREDENTIALS_DIRECTORY',''),args.credential_name,args.codex_home)
    except (OSError,ValueError):parser.error('private systemd credential unavailable')
    os.execve(binary,[str(binary),'app-server'],env)


if __name__=='__main__':main()
