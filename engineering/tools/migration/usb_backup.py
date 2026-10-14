"""Encrypted, verified migration source/config backup. Never copies live PostgreSQL data."""
import getpass
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import tarfile
import uuid

USB_UUID='C0DE-2913'
MOUNT=Path('/mnt/rras-migration-usb')
ROOTS=('srv/git','srv/hermes-dev','srv/jarvis-codex','srv/jarvis-activity','opt/jarvis','opt/hermes',
       'opt/rras-engineering','opt/jarvis-codex','opt/jarvis-codex-review-v2','var/lib/rras-engineering',
       'var/lib/jarvis-codex','etc/rras-canary-credentials-20261012-01','etc/systemd/system',
       'etc/cron.d','etc/crontab','var/spool/cron/crontabs',
       'srv/n8n/backups/linear-replacement-2026-10-08/N8N_BRIDGE_SECRET.txt')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def inventory(base,roots):
    result={};volatile=[]
    def visit(p):
        s=p.lstat();name=str(p.relative_to(base))
        entry={'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid,'mtime_ns':s.st_mtime_ns,
               'xattrs':{k:base64.b64encode(os.getxattr(p,k,follow_symlinks=False)).decode() for k in os.listxattr(p,follow_symlinks=False)}}
        if stat.S_ISLNK(s.st_mode):entry.update(type='symlink',target=os.readlink(p))
        elif stat.S_ISDIR(s.st_mode):
            entry['type']='directory';result[name]=entry
            for child in sorted(p.iterdir()):visit(child)
            return
        elif stat.S_ISREG(s.st_mode):entry.update(type='file',size=s.st_size,sha256=digest(p))
        elif stat.S_ISSOCK(s.st_mode):volatile.append(name);return
        else:raise ValueError('special file requires review')
        result[name]=entry
    for name in roots:visit(base/name)
    return result,volatile


def compare_restored(expected,base):
    actual,_=inventory(base,tuple(n for n in expected if not any(str(parent) in expected for parent in Path(n).parents)))
    # tar preserves seconds at minimum; content, mode, ownership and link targets are essential.
    strip=lambda d:{k:{a:b for a,b in v.items() if a!='mtime_ns'} for k,v in d.items()}
    if strip(actual)!=strip(expected):raise ValueError('restored metadata/content mismatch')


def validate_archive(path):
    with tarfile.open(path) as t:
        symlinks=set()
        for m in t:
            p=Path(m.name)
            if p.is_absolute() or '..' in p.parts:raise ValueError('unsafe archive path')
            if any(str(x) in symlinks for x in p.parents):raise ValueError('archive descends through symlink')
            if m.issym():symlinks.add(str(p))
            elif m.islnk():
                link=Path(m.linkname)
                if link.is_absolute() or '..' in link.parts:raise ValueError('unsafe hardlink')
            elif not (m.isdir() or m.isfile()):raise ValueError('unsafe special member')


def main():
    if os.geteuid()!=0 or socket.gethostname().split('.')[0]!='server01':raise SystemExit('root on server01 required')
    mounts=json.loads(subprocess.check_output(['findmnt','-J','-M',str(MOUNT),'-o','TARGET,SOURCE,FSTYPE,UUID']))['filesystems']
    if len(mounts)!=1 or mounts[0]['uuid']!=USB_UUID or mounts[0]['fstype']!='vfat':raise SystemExit('exact mounted USB required')
    if MOUNT.is_symlink():raise SystemExit('mount symlink refused')
    ident=uuid.uuid4().hex;stage=Path('/var/lib/rras-migration-backups')/ident
    parent=stage.parent
    if parent.is_symlink():raise SystemExit('stage parent symlink refused')
    parent.mkdir(mode=0o700,exist_ok=True)
    if parent.stat().st_uid!=0 or parent.stat().st_mode & 0o077:raise SystemExit('private root-owned stage required')
    stage.mkdir(mode=0o700);destination=MOUNT/('rras-migration-'+ident);destination.mkdir()
    os.umask(0o077)
    print('SAVE BACKUP_ID='+ident+' STAGE='+str(stage)+' USB='+str(destination),flush=True)
    roots=[x for x in ROOTS if (Path('/')/x).exists() or (Path('/')/x).is_symlink()]
    if any(x not in roots for x in ROOTS[:12]):raise SystemExit('required source missing')
    print('Enter a NEW backup passphrase locally. Keep it outside this server; never paste it into chat.',flush=True)
    password=getpass.getpass('Backup passphrase: ')
    if len(password)<12 or '\n' in password or '\x00' in password or password!=getpass.getpass('Confirm passphrase: '):raise SystemExit('passphrase mismatch or shorter than 12 characters')
    before,volatile=inventory(Path('/'),roots)
    size=sum(v.get('size',0) for v in before.values())
    if os.statvfs(MOUNT).f_bavail*os.statvfs(MOUNT).f_frsize<size+256*1024*1024:raise SystemExit('insufficient USB space')
    if os.statvfs(stage).f_bavail*os.statvfs(stage).f_frsize<size*4+512*1024*1024:raise SystemExit('insufficient staging space')
    (stage/'source-manifest.json').write_text(json.dumps({'roots':roots,'files':before,'excluded_sockets':volatile},sort_keys=True))
    plain=stage/'snapshot.tar'
    subprocess.run(['tar','--format=pax','--acls','--xattrs','--numeric-owner','--sparse','-C','/','-cf',str(plain),'--',*roots],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    after,_=inventory(Path('/'),roots)
    if before!=after:raise SystemExit('sources changed during snapshot; preserve failed attempt, do not migrate')
    validate_archive(plain)
    # Confidential manifest travels inside the encrypted archive, never separately on FAT32.
    subprocess.run(['tar','--append','-f',str(plain),'-C',str(stage),'source-manifest.json'],check=True)
    home=stage/'gnupg';home.mkdir(mode=0o700)
    def gpg(args):
        subprocess.run(['gpg','--homedir',str(home),'--batch','--pinentry-mode','loopback','--no-symkey-cache','--passphrase-fd','0',*args],input=(password+'\n').encode(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    encrypted=stage/'snapshot.tar.gpg'
    gpg(['--symmetric','--cipher-algo','AES256','--output',str(encrypted),str(plain)])
    parts=[]
    with encrypted.open('rb') as stream:
        number=0
        while True:
            first=stream.read(1024*1024)
            if not first:break
            p=destination/f'snapshot.gpg.part{number:04d}'
            size_part=len(first)
            with p.open('xb') as f:
                f.write(first)
                while size_part<1024*1024*1024:
                    data=stream.read(min(1024*1024,1024*1024*1024-size_part))
                    if not data:break
                    f.write(data);size_part+=len(data)
                f.flush();os.fsync(f.fileno())
            parts.append({'name':p.name,'size':size_part,'sha256':digest(p)});number+=1
    subprocess.run(['sync','-f',str(MOUNT)],check=True)
    joined=stage/'usb-readback.gpg'
    with joined.open('xb') as out:
        for item in parts:
            p=destination/item['name']
            if digest(p)!=item['sha256']:raise SystemExit('USB part hash mismatch')
            with p.open('rb') as f:
                for b in iter(lambda:f.read(1024*1024),b''):out.write(b)
    if digest(joined)!=digest(encrypted):raise SystemExit('USB archive mismatch')
    decrypted=stage/'restored.tar';gpg(['--decrypt','--output',str(decrypted),str(joined)])
    if digest(decrypted)!=digest(plain):raise SystemExit('decrypted archive mismatch')
    validate_archive(decrypted)
    restore=stage/'restore-check';restore.mkdir(mode=0o700)
    subprocess.run(['tar','--acls','--xattrs','--xattrs-include=*','--numeric-owner','-xf',str(decrypted),'-C',str(restore)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    compare_restored(before,restore)
    report={'scope':'migration-source-config-rollback','backup_id':ident,'success':True,'encrypted':True,'parts':parts,
            'encrypted_archive_sha256':digest(encrypted),'restore_verified':True,'database_backup':False,
            'source_changed':False,'retention':'no automatic deletion; retain until operator authorizes cleanup'}
    (destination/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    subprocess.run(['sync','-f',str(MOUNT)],check=True)
    (stage/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));print('SUCCESS: keep the passphrase. Protected local staging retained; safely unmount USB before unplugging.',flush=True)

if __name__=='__main__':main()
