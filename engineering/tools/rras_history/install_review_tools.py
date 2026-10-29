"""Stdlib bootstrap appended to the fixed review tools package verifier.

Explicit first installation of two wrappers over an already host-verified release.
"""
import argparse
import os
import shlex
import sys

RELEASES=Path('/opt/rras-engineering/releases')
STAGING=Path('/var/lib/rras-history-tools-staging')
INSTALLATIONS=Path('/var/lib/rras-history-tools-installations')
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
TARGETS={'export':Path('/usr/local/sbin/rras-history-review-export'),
         'intake':Path('/usr/local/bin/rras-history-review-document')}
CASES=['actual_root_and_operator_dispatch','operator_and_worker_read_only_payload',
       'distinct_uids_private_network_no_groups_caps_provider_environment',
       'operator_and_worker_root_export_denied','changed_manifest_refused_before_dispatch']


def protected(path):
    if path.resolve(strict=True)!=path:raise ValueError('canonical protected install path required')
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected install path required')


def absent(path):
    if path.exists() or path.is_symlink():raise ValueError('preserve existing wrapper/evidence; no retry')


def wrapper(release,sha,mode):
    entry=release/'engineering/tools/rras_history/review_tools_entry.py'
    command=['/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',
             str(PYTHON),'-I','-B',str(entry),'--manifest-sha256',sha,mode]
    return ('#!/bin/sh\nexec '+shlex.join(command)+' "$@"\n').encode()


def preflight(expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit root installation required')
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('exact release digest required')
    release=RELEASES/('history-review-tools-'+expected[:12]);protected(release)
    manifest,files=verify(release,expected)
    for name in (*files,MANIFEST):
        path=release/name;protected(path)
        if stat.S_IMODE(path.stat().st_mode)!=0o444:raise ValueError('readonly staged payload required')
    for path in (PYTHON.parent,PYTHON.resolve(strict=True),Path('/usr/bin/env'),Path('/bin/sh').resolve(strict=True),INSTALLATIONS.parent):protected(path)
    evidence=STAGING/expected/'complete.json';protected(evidence)
    if stat.S_IMODE(evidence.stat().st_mode)!=0o600:raise ValueError('private host acceptance required')
    result=decode(regular(evidence,256*1024))
    if (result.get('phase')!='inactive_review_tools_staged_and_host_verified' or result.get('manifest_sha256')!=expected or
            result.get('release')!=str(release) or result.get('source_commit')!=manifest['source_commit'] or
            result.get('files')!=len(files) or result.get('cases')!=CASES or result.get('api_calls')!=0 or
            any(result.get(k) is not False for k in ('wrappers_installed','services_changed','production_history_changed',
                'production_journal_changed','production_source_opened','automatic_retry'))):raise ValueError('host acceptance differs')
    if INSTALLATIONS.exists():
        protected(INSTALLATIONS)
        if not INSTALLATIONS.is_dir() or stat.S_IMODE(INSTALLATIONS.stat().st_mode)!=0o700:raise ValueError('private install parent required')
    elif INSTALLATIONS.is_symlink():raise ValueError('install parent symlink refused')
    journal=INSTALLATIONS/expected;absent(journal)
    wrappers={}
    for mode,target in TARGETS.items():
        protected(target.parent);absent(target)
        pending=target.with_name('.'+target.name+'-'+expected[:12]+'.pending');absent(pending)
        wrappers[mode]=(target,pending,wrapper(release,expected,mode))
    return manifest,release,journal,wrappers


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def write(path,raw,mode):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sync(path.parent)


def install(expected,*,check_only=False,approve_installation=False):
    if not check_only and approve_installation is not True:raise ValueError('explicit wrapper installation approval required')
    manifest,release,journal,wrappers=preflight(expected)
    if check_only:return {'phase':'review_tools_wrapper_install_preflight_passed','mutations':False,'wrappers_installed':False}
    os.umask(0o077)
    if not INSTALLATIONS.exists():INSTALLATIONS.mkdir(mode=0o700);sync(INSTALLATIONS.parent)
    journal.mkdir(mode=0o700);sync(INSTALLATIONS)
    write(journal/'plan.json',encoded({'manifest_sha256':expected,'release':str(release),
        'targets':{mode:str(value[0]) for mode,value in wrappers.items()}}),0o600)
    installed=[]
    try:
        for mode,(target,pending,raw) in wrappers.items():
            write(pending,raw,0o755)
            # Exclusive atomic publication. Never replace an unexpected existing target.
            os.link(pending,target,follow_symlinks=False);sync(target.parent)
            pending.unlink();sync(target.parent);protected(target)
            info=target.stat()
            if info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o755 or regular(target)!=raw:raise ValueError('published wrapper differs')
            installed.append(mode);write(journal/(mode+'-installed.json'),encoded({'target':str(target),'sha256':hashlib.sha256(raw).hexdigest()}),0o600)
        result={'phase':'review_tools_wrappers_installed','release':str(release),'journal':str(journal),
            'manifest_sha256':expected,'wrappers':{mode:str(item[0]) for mode,item in wrappers.items()},
            'services_changed':False,'production_history_changed':False,'production_journal_changed':False,
            'api_calls':0,'automatic_retry':False}
        write(journal/'complete.json',encoded(result),0o600);return result
    except Exception as error:
        write(journal/'stopped.json',encoded({'exception_type':type(error).__name__,'completed_wrappers':installed,
            'automatic_retry':False,'automatic_rollback':False}),0o600)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--check-only',action='store_true');parser.add_argument('--approve-wrapper-installation',action='store_true')
    args=parser.parse_args()
    try:print(json.dumps(install(args.manifest_sha256,check_only=args.check_only,approve_installation=args.approve_wrapper_installation),indent=2))
    except Exception:
        sys.stderr.write('Review wrapper installation refused or stopped. Preserve protected evidence; no automatic retry or rollback.\n');raise SystemExit(1)
