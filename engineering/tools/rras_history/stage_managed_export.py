"""Pinned one-work production read-only export; never history intake or execution."""
import argparse
import os
import subprocess
import sys
import traceback

ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('root-protected export path required')


def absent(path):
    if path.exists() or path.is_symlink():raise ValueError('preserve existing export; no automatic retry')


def write(path,raw,mode=0o600,uid=0,gid=0):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),uid,gid)
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def mkdir(path,mode):path.mkdir(mode=mode);os.chmod(path,mode)


def preflight(candidate,expected,plan_path,plan_sha):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator export invocation required')
    manifest,files=verify(candidate,expected);raw=regular(plan_path,32*1024)
    if type(plan_sha) is not str or not re.fullmatch('[0-9a-f]{64}',plan_sha) or hashlib.sha256(raw).hexdigest()!=plan_sha:
        raise ValueError('exact reviewed export plan required')
    plan=validate_plan(decode(raw))
    if encoded(plan)!=raw:raise ValueError('canonical reviewed export plan required')
    release=Path('/opt/rras-engineering/releases/history-link-tools-'+expected[:12])
    capture='export-'+plan['capture_id'];journal=JOURNALS/capture;handoff=HANDOFFS/capture
    for path in (release.parent,SOURCE,SOURCE/'workflow.sqlite3',JOURNALS.parent,HANDOFFS.parent,PYTHON.parent,PYTHON.resolve(strict=True),
                 Path('/usr/bin/unshare'),Path('/usr/bin/setpriv')):protected(path)
    info=(SOURCE/'workflow.sqlite3').lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:raise ValueError('private source journal required')
    for path,mode in ((JOURNALS,0o700),(HANDOFFS,0o711)):
        if path.exists():
            protected(path)
            if not path.is_dir() or stat.S_IMODE(path.stat().st_mode)!=mode:raise ValueError('existing export parent custody differs')
        elif path.is_symlink():raise ValueError('export parent symlink refused')
    if release.exists():
        protected(release);verify(release,expected)
        for name in files:protected(release/name)
    elif release.is_symlink():raise ValueError('export release symlink refused')
    absent(journal);absent(handoff)
    return manifest,files,plan,raw,release,journal,handoff


def export_command(release,journal):
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid','0','--regid','0','--clear-groups',
            '--pdeathsig=TERM','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',
            str(PYTHON),'-I','-B',str(release/'engineering/tools/rras_history/managed_export_entry.py'),str(journal)]


def stage(candidate,expected,plan_path,plan_sha,*,check_only=False):
    manifest,files,plan,raw,release,journal,handoff=preflight(candidate,expected,plan_path,plan_sha)
    if check_only:return {'phase':'production_history_export_preflight_passed','mutations':False,'history_import_authorized':False}
    os.umask(0o077)
    if not JOURNALS.exists():mkdir(JOURNALS,0o700)
    mkdir(journal,0o700);write(journal/'plan.json',raw)
    try:
        if not release.exists():
            mkdir(release,0o755)
            for name,content in files.items():
                path=release/name
                for relative in reversed(path.relative_to(release).parents):
                    if relative==Path('.'):continue
                    parent=release/relative
                    if not parent.exists():mkdir(parent,0o755)
                write(path,content,0o444)
            write(release/'export-tools-manifest.json',encoded(manifest),0o444)
        verify(release,expected)
        result=subprocess.run(export_command(release,journal),stdin=subprocess.DEVNULL,capture_output=True,env=ENV,timeout=120)
        write(journal/'reader-stdout.json',result.stdout);write(journal/'reader-stderr.txt',result.stderr)
        if result.returncode:raise ValueError('protected source export failed; preserve private diagnostics')
        answer=decode(result.stdout)
        if answer.get('exported') is not True or answer.get('source_rows_written') is not False or answer.get('history_records_written') is not False:
            raise ValueError('source export outcome differs')
        output=decode(regular(journal/'export-result.json',256*1024))
        packets=output['packets']
        if type(packets) is not list or not 1<=len(packets)<=101:raise ValueError('bounded export packets required')
        if not HANDOFFS.exists():mkdir(HANDOFFS,0o711)
        # Keep the receiver locked out until all new files are complete. No root
        # file writes occur inside this directory after ownership is transferred.
        mkdir(handoff,0o700)
        for index,item in enumerate(packets):
            name=f'packet-{index:03d}.json'
            if set(item)!={'file','sha256','events'} or item['file']!=name:raise ValueError('exact export packet name required')
            content=regular(journal/name,128*1024)
            if hashlib.sha256(content).hexdigest()!=item['sha256']:raise ValueError('export packet digest differs')
            write(handoff/name,content,uid=1000,gid=1000)
        write(handoff/'export-result.json',regular(journal/'export-result.json',256*1024),uid=1000,gid=1000)
        write(handoff/'plan.json',raw,uid=1000,gid=1000)
        fd=os.open(handoff,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        os.chown(handoff,1000,1000)
        result={'phase':'production_managed_history_export_complete','release':str(release),'journal':str(journal),
                'handoff':str(handoff),'work_item_id':plan['work_item_id'],'repository_id':plan['repository_id'],
                'source_work_sha256':plan['source_work_sha256'],'pages':len(packets),'events':sum(item['events'] for item in packets),
                'source_open_mode':'ro','source_rows_written':False,'history_records_written':False,
                'history_import_authorized':False,'services_changed':False,'api_calls':0}
        write(journal/'complete.json',encoded(result));return result
    except Exception as error:
        write(journal/'failure-private.txt',traceback.format_exc().encode())
        raise ValueError('production export stopped; preserve protected evidence') from error


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--plan',required=True);parser.add_argument('--plan-sha256',required=True);parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    try:print(json.dumps(stage(Path(args.candidate),args.manifest_sha256,Path(args.plan),args.plan_sha256,check_only=args.check_only),indent=2))
    except Exception:
        sys.stderr.write('Production managed-history export refused/stopped. Preserve evidence; no automatic retry or import.\n');raise SystemExit(1)
