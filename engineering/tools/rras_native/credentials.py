"""Read only a private systemd-delivered task credential; never print it."""
import os
from pathlib import Path
import stat

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
