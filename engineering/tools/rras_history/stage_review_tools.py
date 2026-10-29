"""Stdlib bootstrap appended to the fixed review tools package verifier.

Stages inactive protected bytes and runs isolated command/permission probes only.
"""
import argparse
import os
import subprocess
import sys

RELEASES=Path('/opt/rras-engineering/releases')
JOURNALS=Path('/var/lib/rras-history-tools-staging')
PYTHON=Path('/opt/rras-engineering/releases/native-10/venv/bin/python')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected staging path required')


def absent(path):
    if path.exists() or path.is_symlink():raise ValueError('preserve existing release/evidence; no retry')


def preflight(candidate,expected):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo staging required')
    manifest,files=verify(candidate,expected)
    for path in (RELEASES,JOURNALS.parent,PYTHON.parent,PYTHON.resolve(strict=True),
                 Path('/usr/bin/unshare'),Path('/usr/bin/setpriv')):protected(path)
    release=RELEASES/('history-review-tools-'+expected[:12]);journal=JOURNALS/expected
    if JOURNALS.exists():
        protected(JOURNALS)
        if not JOURNALS.is_dir() or stat.S_IMODE(JOURNALS.stat().st_mode)!=0o700:raise ValueError('private staging journal required')
    elif JOURNALS.is_symlink():raise ValueError('journal symlink refused')
    absent(release);absent(journal)
    return manifest,files,release,journal


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def write(path,raw,mode):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sync(path.parent)


def command(uid,args):
    return ['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(uid),'--regid',str(uid),
        '--clear-groups','--pdeathsig=TERM','--no-new-privs','--bounding-set=-all','--inh-caps=-all',
        '--ambient-caps=-all',str(PYTHON),'-I','-B',*args]


def child(uid,args,journal,name,expected_return=0):
    result=subprocess.run(command(uid,args),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          env=ENV,timeout=30)
    if len(result.stdout)>65536 or len(result.stderr)>65536:raise ValueError('probe output bound exceeded')
    write(journal/(name+'-stdout.txt'),result.stdout,0o600);write(journal/(name+'-stderr.txt'),result.stderr,0o600)
    if result.returncode!=expected_return:raise ValueError('isolated command probe refused')
    return result


def acceptance(release,expected,journal):
    entry=str(release/'engineering/tools/rras_history/review_tools_entry.py')
    for uid in (0,1000):
        for mode in ('export','intake'):
            result=child(uid,[entry,'--manifest-sha256',expected,mode,'--help'],journal,f'help-{uid}-{mode}')
            if b'usage:' not in result.stdout:raise ValueError('command dispatch absent')
    for uid in (1000,996):
        code="""import os,socket,json
from pathlib import Path
fields=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert os.getuid()==os.geteuid()==UID and os.getgroups()==[] and fields['NoNewPrivs'].strip()=='1'
assert all(int(fields[key].strip(),16)==0 for key in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb'))
assert [name for _,name in socket.if_nameindex()]==['lo']
assert not any(key in os.environ for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','GH_TOKEN','GITHUB_TOKEN'))
release=Path(RELEASE)
assert release.stat().st_uid==0 and not os.access(release,os.W_OK)
assert not os.access(release/'release-manifest.json',os.W_OK)
assert not os.access(release/'engineering/tools/rras_history/review_tools_entry.py',os.W_OK)
print(json.dumps({'uid':UID,'protected_read_only':True,'private_network':True,'no_capabilities':True}))
""".replace('UID',str(uid)).replace('RELEASE',repr(str(release)))
        child(uid,['-c',code],journal,f'boundary-{uid}')
        result=child(uid,[entry,'--manifest-sha256',expected,'export','inspect','--state','/nonexistent',
            '--review-id','a'*64,'--source-release','/nonexistent','--source-manifest-sha256','b'*64,
            '--approve-private-read'],journal,f'root-export-denied-{uid}',expected_return=1)
        if b'Private review export refused' not in result.stderr:raise ValueError('root-only export refusal absent')
    result=child(0,[entry,'--manifest-sha256','0'*64,'intake','--help'],journal,'wrong-manifest',expected_return=1)
    if b'Pinned review tools refused' not in result.stderr:raise ValueError('manifest gate refusal absent')
    return ['actual_root_and_operator_dispatch','operator_and_worker_read_only_payload',
            'distinct_uids_private_network_no_groups_caps_provider_environment',
            'operator_and_worker_root_export_denied','changed_manifest_refused_before_dispatch']


def stage(candidate,expected,*,check_only=False):
    manifest,files,release,journal=preflight(candidate,expected)
    if check_only:return {'phase':'inactive_review_tools_preflight_passed','mutations':False,'installation_authorized':False}
    os.umask(0o077)
    if not JOURNALS.exists():JOURNALS.mkdir(mode=0o700);sync(JOURNALS.parent)
    journal.mkdir(mode=0o700);sync(JOURNALS)
    write(journal/'plan.json',encoded({'manifest_sha256':expected,'source_commit':manifest['source_commit'],
        'release':str(release),'scope':'inactive-stage-and-isolated-permission-validation'}),0o600)
    try:
        release.mkdir(mode=0o755);release.chmod(0o755);sync(RELEASES)
        for name,raw in files.items():
            path=release/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            write(path,raw,0o444)
        write(release/MANIFEST,encoded(manifest),0o444)
        for directory in sorted([p for p in release.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True):
            directory.chmod(0o755);sync(directory)
        sync(release)
        # Reverify final protected bytes before evaluating any staged code.
        verify(release,expected)
        for name in (*files,MANIFEST):protected(release/name)
        cases=acceptance(release,expected,journal)
        result={'phase':'inactive_review_tools_staged_and_host_verified','release':str(release),'journal':str(journal),
            'manifest_sha256':expected,'source_commit':manifest['source_commit'],'files':len(files),'cases':cases,
            'wrappers_installed':False,'services_changed':False,'production_history_changed':False,
            'production_journal_changed':False,'production_source_opened':False,'api_calls':0,'automatic_retry':False}
        write(journal/'complete.json',encoded(result),0o600);return result
    except Exception as error:
        write(journal/'stopped.json',encoded({'exception_type':type(error).__name__,'automatic_retry':False}),0o600)
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True);parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    try:print(json.dumps(stage(Path(args.candidate),args.manifest_sha256,check_only=args.check_only),indent=2))
    except Exception:
        sys.stderr.write('Review tools staging stopped; preserve release/journal evidence. No automatic retry or installation.\n');raise SystemExit(1)
