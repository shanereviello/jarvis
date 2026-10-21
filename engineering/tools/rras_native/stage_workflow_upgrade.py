"""Dedicated root inactive upgrade staging and read-only evidence inspection.

Never drain, start/stop/rename a container, replace live wrappers/config, initialize
storage, open provider credential files or activate an upgrade. Interrupted roots persist.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import traceback

RELEASES=Path('/opt/rras-engineering/releases')
JOURNALS=Path('/var/lib/rras-workflow-upgrades')
SOURCE=Path('/srv/git/jarvis')
CONFIG=Path('/etc/rras-engineering/workflow/jarvis.json')
HERMES_CONFIG=Path('/srv/hermes/data/config.yaml')
COMPOSE=Path('/opt/hermes/releases/hermes-0c8b6be07ce8/deploy/hermes/compose.yaml')
PROFILE=RELEASES/'operator-project-trust-v1/profile.json'
CODEX=RELEASES/'operator-project-trust-v1/codex-config.toml'
PYTHON=RELEASES/'native-10/venv/bin/python'
IMAGE='sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432'
WRAPPERS={'rras-workflow':'operator.py','rras-workflow-journal':'journal.py','rras-workflow-publish':'publish.py'}
SBIN=Path('/usr/local/sbin')
JOURNAL_DB=Path('/var/lib/rras-workflow/journal/workflow.sqlite3')
HISTORY=Path('/var/lib/rras-workflow/history')
ROLE_DIRS={Path('/var/lib/rras-workflow/journal'):(0,0,0o700),
    HISTORY:(0,1000,0o750),Path('/var/lib/rras-coding-control'):(0,0,0o700),
    Path('/opt/rras-coding-jobs'):(0,0,0o755),Path('/var/lib/rras-coding-tasks'):(996,996,0o700)}


def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()

def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid JSON number')))

def administrator():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('administrator upgrade staging required')

def protected(path):
    path=Path(path)
    if not path.is_absolute():raise ValueError('absolute protected path required')
    for item in (path,*path.parents):
        s=item.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:raise ValueError('root-protected upgrade path required')
    return path

def user_role(path,info):
    # The installed Hermes config is owner/group1000 mode0640; acceptance may
    # use0600. No group write/public read is allowed, and drain markers keep0600.
    allowed=(0o600,0o640) if Path(path)==HERMES_CONFIG else (0o600,)
    if (info.st_uid,info.st_gid)!=(1000,1000) or stat.S_IMODE(info.st_mode) not in allowed:raise ValueError('private Hermes owner/group/mode changed')


def regular(path,limit=4*1024*1024,user=False):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('canonical regular upgrade input required')
    if not user:protected(path)
    else:
        for parent in path.parents:
            s=parent.lstat()
            if s.st_uid not in (0,1000) or s.st_mode&0o022:raise ValueError('unsafe private data ancestor')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>limit:raise ValueError('bounded regular upgrade input required')
        if user:user_role(path,s)
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('upgrade input exceeds bound')
        return raw
    finally:os.close(fd)

def role(path,uid,gid,mode):
    s=path.lstat()
    if not stat.S_ISDIR(s.st_mode) or (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=(uid,gid,mode):raise ValueError('state directory role changed')
    for parent in path.parents:protected(parent)

def command(argv,**kwargs):
    return subprocess.run(argv,env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'},
        stdin=subprocess.DEVNULL if 'input' not in kwargs else None,capture_output=True,check=True,timeout=60,**kwargs)

def idle():
    result=command(['/usr/bin/systemctl','show','rras-coding-task.service','-p','LoadState','--value'])
    if result.stdout.strip()!=b'not-found':raise ValueError('task slot exists; preserve')
    result=subprocess.run(['/usr/bin/pgrep','-u','996'],env={'PATH':'/usr/bin:/bin'},capture_output=True,timeout=10)
    if result.returncode!=1:raise ValueError('worker identity busy or ambiguous')

def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def write(path,raw,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),mode);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sync(path.parent)

def wrapper(release,entry):
    return ('#!/bin/sh\nexec '+str(PYTHON)+' -I -B '+str(release)+'/entrypoints/'+entry+' "$@"\n').encode()

def mounts(installed):
    return {'/opt/data':('/srv/hermes/data',True,'bind'),'/workspace/git/jarvis':('/srv/git/jarvis',False,'bind'),
        '/workspace/git/robot_ws':('/srv/git/robot_ws',False,'bind'),'/workspace/jarvis-artifacts':('/srv/notes/jarvis-artifacts',True,'bind'),
        '/workspace/shared':('/srv/shared/jarvis',True,'bind'),'/opt/rras-workflow':(str(installed),False,'bind'),
        '/opt/rras-workflow-history':(str(HISTORY),False,'bind')}

def validate_plan(plan,manifest):
    installed=plan['installed_release'];release=str(RELEASES/manifest['release_id'])
    if (plan['schema_version']!=2 or plan['scope']!='inactive_upgrade_candidate_only' or
        plan['release']!=release or plan['source_commit']!=manifest['source_commit'] or
        not re.fullmatch(re.escape(str(RELEASES))+r'/workflow-[0-9a-f]{12}',installed) or installed==release or
        plan['activation_authorized'] is not False or plan['journal_required'] is not True or
        plan['operator_config_action']!='preserve_existing_bytes' or plan['candidate_registration_applied'] is not False or
        plan['config_path']!=str(CONFIG) or plan['hermes']['image']!=IMAGE or plan['hermes']['compose']!=str(COMPOSE) or
        plan['hermes']['existing_history_entry_name']!='rras-workflow-history' or
        plan['hermes']['preserve_other_entries_and_mounts'] is not True):raise ValueError('unsupported upgrade plan')
    history={'command':'/opt/hermes/.venv/bin/python','args':['-I','-B','/opt/rras-workflow/engineering/tools/rras_native/workflow_read_stdio.py','--directory','/opt/rras-workflow-history']}
    if plan['hermes']['existing_history_entry']!=history:raise ValueError('unexpected history MCP entry')
    expected={'expected_source':installed,'source':release,'target':'/opt/rras-workflow','read_only':True}
    if plan['hermes']['replace_readonly_mount']!=expected:raise ValueError('unexpected upgrade mount')
    for value in (plan['expected_operator_config_sha256'],plan['hermes']['expected_config_sha256'],
                  plan['hermes']['expected_compose_sha256'],plan['profile_sha256'],plan['codex_config_sha256']):
        if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('exact current digests required')
    return Path(installed),Path(release)

def candidate(path,expected):
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('exact candidate and digest required')
    def read(name,limit):
        member=path/name
        if member.resolve(strict=True)!=member or member.is_symlink() or not member.is_file() or member.stat().st_size>limit:raise ValueError('unsafe candidate member')
        raw=member.read_bytes()
        if len(raw)>limit:raise ValueError('oversized candidate member')
        return raw
    raw=read('release-manifest.json',1024*1024)
    if sha(raw)!=expected:raise ValueError('manifest changed')
    manifest=decode(raw)
    if (manifest['schema_version']!=2 or manifest['kind']!='workflow_upgrade_candidate' or
        not re.fullmatch('workflow-[0-9a-f]{12}',manifest['release_id']) or
        not re.fullmatch('[0-9a-f]{40}',manifest['source_commit']) or not 1<=len(manifest['files'])<=512):raise ValueError('upgrade manifest required')
    identity={key:manifest[key] for key in ('source_commit','files','dependencies')}
    if 'workflow-'+sha(encoded(identity))[:12]!=manifest['release_id']:raise ValueError('release identity changed')
    payload={}
    for name,digest in manifest['files'].items():
        p=PurePosixPath(name)
        if p.is_absolute() or str(p)!=name or '..' in p.parts or not name.startswith(('engineering/','vendor/','config/','entrypoints/')):raise ValueError('unsafe payload name')
        data=read(name,4*1024*1024)
        if sha(data)!=digest:raise ValueError('payload changed')
        payload[name]=data
    if sum(map(len,payload.values()))>16*1024*1024:raise ValueError('oversized package')
    plan_raw=read('install-plan.json',1024*1024)
    if sha(plan_raw)!=manifest['plan_sha256']:raise ValueError('plan changed')
    plan=decode(plan_raw);validate_plan(plan,manifest)
    return manifest,raw,plan,plan_raw,payload

def observe(plan):
    idle()
    marker=HERMES_CONFIG.parent/'.drain_request.json'
    if marker.exists() or marker.is_symlink():raise ValueError('existing drain marker; preserve')
    for path,values in ROLE_DIRS.items():role(path,*values)
    for suffix in ('-journal','-wal','-shm'):
        path=Path(str(JOURNAL_DB)+suffix)
        if path.exists() or path.is_symlink():
            if regular(path,64*1024*1024):raise ValueError('journal sidecar present; defer staging')
    config=regular(CONFIG);parsed=decode(config)
    if (sha(config)!=plan['expected_operator_config_sha256'] or parsed['journal']!=str(JOURNAL_DB.parent) or
        parsed['profile']!=str(PROFILE) or parsed['codex_config']!=str(CODEX)):raise ValueError('operator configuration changed')
    hermes=regular(HERMES_CONFIG,2*1024*1024,user=True);compose=regular(COMPOSE)
    if sha(hermes)!=plan['hermes']['expected_config_sha256'] or sha(compose)!=plan['hermes']['expected_compose_sha256']:raise ValueError('Hermes inputs changed')
    if sha(regular(PROFILE))!=plan['profile_sha256'] or sha(regular(CODEX))!=plan['codex_config_sha256']:raise ValueError('session profile changed')
    protected(PYTHON.resolve(strict=True));protected(plan['installed_release'])
    originals={name:regular(SBIN/name) for name in WRAPPERS}
    if any(raw!=wrapper(plan['installed_release'],WRAPPERS[name]) for name,raw in originals.items()):raise ValueError('installed wrappers differ from expected release')
    current=decode(command(['/usr/bin/docker','inspect','hermes']).stdout)[0]
    targets={row['Destination']:(row['Source'],row['RW'],row['Type']) for row in current['Mounts']}
    if (not re.fullmatch('[0-9a-f]{64}',current['Id']) or current['Image']!=IMAGE or current['State']['Running'] is not True or
        current['Name']!='/hermes' or len(targets)!=len(current['Mounts']) or targets!=mounts(plan['installed_release'])):raise ValueError('live container identity/mounts changed')
    # Validate existing private YAML using the pinned running image's parser. No
    # transformation, config output, network request or gateway restart occurs.
    script="import json,sys,yaml;p=json.load(sys.stdin);d=yaml.safe_load(p['raw']);assert d['mcp_servers']['rras-workflow-history']==p['entry'];print('existing_history_entry_verified')"
    result=command(['/usr/bin/docker','exec','-i','--user','1000:1000','hermes','/opt/hermes/.venv/bin/python','-I','-B','-c',script],
        input=encoded({'raw':hermes.decode(),'entry':plan['hermes']['existing_history_entry']}))
    if result.stdout.strip()!=b'existing_history_entry_verified':raise ValueError('existing history entry not verified')
    metadata={}
    for path in (CONFIG,HERMES_CONFIG,COMPOSE,JOURNAL_DB,HISTORY/'index.json',*[SBIN/name for name in WRAPPERS]):
        info=path.lstat();metadata[str(path)]={'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),'device':info.st_dev,'inode':info.st_ino}
    fingerprint={'file_metadata':metadata,'operator_config_sha256':sha(config),'hermes_config_sha256':sha(hermes),'compose_sha256':sha(compose),
        'journal_db_sha256':sha(regular(JOURNAL_DB,64*1024*1024)),'history_index_sha256':sha(regular(HISTORY/'index.json')),
        'wrapper_sha256':{name:sha(raw) for name,raw in originals.items()},'container_id':current['Id'],
        'container_started_at':current['State']['StartedAt'],'container_restart_count':current['RestartCount']}
    return fingerprint,{'operator-config.original':config,'hermes-config.original':hermes,'compose.original':compose,
        'container.original.json':encoded(current),'filesystem.original.json':encoded(metadata),**{'wrappers/'+name+'.original':raw for name,raw in originals.items()}}

def source_ancestor(commit):
    if not isinstance(commit,str) or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('exact reviewed source commit required')
    command(['/usr/bin/git','--no-replace-objects','-c','safe.directory='+str(SOURCE),'-c','core.hooksPath=/dev/null','-C',str(SOURCE),
        'merge-base','--is-ancestor',commit,'main'])


def stage(path,expected):
    administrator();manifest,manifest_raw,plan,plan_raw,payload=candidate(path,expected)
    installed,release=validate_plan(plan,manifest)
    source_ancestor(manifest['source_commit'])
    protected(RELEASES);protected(JOURNALS.parent)
    if JOURNALS.exists():protected(JOURNALS);role(JOURNALS,0,0,0o700)
    journal=JOURNALS/manifest['release_id']
    if any(p.exists() or p.is_symlink() for p in (release,journal)):raise ValueError('upgrade roots exist; preserve and inspect, never adopt')
    before,originals=observe(plan)
    if not JOURNALS.exists():JOURNALS.mkdir(mode=0o700);sync(JOURNALS.parent)
    journal.mkdir(mode=0o700);sync(JOURNALS)
    try:
        write(journal/'started.json',encoded({'manifest_sha256':expected,'source_commit':manifest['source_commit'],'activation_authorized':False}))
        files={'release-manifest.json':manifest_raw,'install-plan.json':plan_raw,**originals}
        for name,entry in WRAPPERS.items():files['wrappers/'+name+'.candidate']=wrapper(release,entry)
        files['compose.override.json']=encoded({'services':{'hermes':{'volumes':[
            {'type':'bind','source':str(release),'target':'/opt/rras-workflow','read_only':True},
            {'type':'bind','source':str(HISTORY),'target':'/opt/rras-workflow-history','read_only':True}]}}})
        for name,raw in files.items():
            target=journal/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True);write(target,raw)
        release.mkdir(mode=0o755)
        for name,raw in payload.items():
            target=release/name;target.parent.mkdir(mode=0o755,parents=True,exist_ok=True);write(target,raw,0o644)
        write(release/'release-manifest.json',manifest_raw,0o444)
        for directory in sorted({release,*[p.parent for p in release.rglob('*')]},key=lambda p:len(p.parts),reverse=True):directory.chmod(0o755);sync(directory)
        after,_=observe(plan)
        if after!=before:raise ValueError('live state changed during inactive staging; preserve evidence')
        answer={'phase':'inactive_workflow_upgrade_staged','release':str(release),'journal':str(journal),
            'manifest_sha256':expected,'source_commit':manifest['source_commit'],'fingerprint':before,
            'private_files':{name:sha(raw) for name,raw in files.items()},'production_configuration_changed':False,
            'production_journal_changed':False,'services_changed':False,'activation_authorized':False,'api_calls':0}
        write(journal/'staged.json',encoded(answer));sync(RELEASES);return public(answer)
    except BaseException:
        try:write(journal/'staging-error.txt',traceback.format_exc().encode()[:65536])
        except OSError:pass
        raise


def public(answer):
    return {k:v for k,v in answer.items() if k not in ('fingerprint','private_files')}

def evidence(journal,verify_release=True):
    """Protected stage evidence without requiring production still uses old code.

    Rollback may skip the new code tree but still verifies every private original;
    a broken candidate must not prevent safe restoration of the retained container.
    """
    administrator();journal=protected(journal);role(journal,0,0,0o700)
    if journal.parent!=JOURNALS or not re.fullmatch('workflow-[0-9a-f]{12}',journal.name):raise ValueError('exact upgrade journal required')
    start=decode(regular(journal/'started.json'))
    answer=decode(regular(journal/'staged.json'));manifest_raw=regular(journal/'release-manifest.json');manifest=decode(manifest_raw)
    if sha(manifest_raw)!=answer['manifest_sha256'] or start['manifest_sha256']!=answer['manifest_sha256']:raise ValueError('upgrade journal identity changed')
    for name,digest in answer['private_files'].items():
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or str(p)!=name or sha(regular(journal/name))!=digest:raise ValueError('private rollback evidence changed')
    plan=decode(regular(journal/'install-plan.json'));installed,release=validate_plan(plan,manifest)
    if sha(encoded(plan))!=manifest['plan_sha256']:raise ValueError('staged plan/manifest changed')
    if verify_release:
        if regular(release/'release-manifest.json')!=manifest_raw:raise ValueError('staged manifest changed')
        for name,digest in manifest['files'].items():
            if sha(regular(release/name))!=digest:raise ValueError('staged release changed')
    return answer,manifest,plan

def inspect(journal):
    administrator();journal=protected(journal);role(journal,0,0,0o700)
    if journal.parent!=JOURNALS or not re.fullmatch('workflow-[0-9a-f]{12}',journal.name):raise ValueError('exact upgrade journal required')
    if not (journal/'started.json').exists() and not (journal/'started.json').is_symlink():
        return {'phase':'unidentified_stage_preserved','automatic_retry':False,'activation_authorized':False}
    start=decode(regular(journal/'started.json'))
    if not (journal/'staged.json').exists():return {'phase':'incomplete_stage_preserved','manifest_sha256':start['manifest_sha256'],'automatic_retry':False,'activation_authorized':False}
    answer,manifest,plan=evidence(journal)
    current,_=observe(plan)
    return dict(public(answer),phase='staged_inactive_verified' if current==answer['fingerprint'] else 'external_state_changed',automatic_retry=False)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    run=sub.add_parser('stage');run.add_argument('--candidate',required=True);run.add_argument('--manifest-sha256',required=True)
    check=sub.add_parser('inspect');check.add_argument('--journal',required=True);args=p.parse_args(argv)
    try:answer=stage(args.candidate,args.manifest_sha256) if args.action=='stage' else inspect(args.journal)
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError):p.exit(1,'Upgrade staging refused; preserve existing roots and private evidence. No automatic retry.\n')
    print(json.dumps(answer))

if __name__=='__main__':main()
