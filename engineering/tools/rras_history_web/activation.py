"""Appended to pinned runtime verifier. Explicit grant/start; no Cloudflare edits."""
import argparse
import copy
import grp
import http.client
import pwd
import sys
import time
import traceback

WEB='rras-engineering-history-web.service'
HISTORY='rras-engineering-history.service'
ACCOUNT='rras-history-web'
CONFIG=Path('/etc/rras-engineering-history-web/config.json')
POLICY=Path('/etc/rras-engineering-history/access-policy.json')
JOURNALS=Path('/var/lib/rras-history-web-activations')
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}


def proposed_policy(value):
    if type(value) is not dict or set(value)!={'contract','principals'} or value['contract']!='engineering-history-access.v1' or type(value['principals']) is not list or len(value['principals'])>=128:raise ValueError('bounded existing policy required')
    seen=set()
    for row in value['principals']:
        if type(row) is not dict or set(row)!={'uid','private_read','write'} or type(row['uid']) is not int or not 1<=row['uid']<2**32-1 or row['uid'] in (993,996,997) or row['uid'] in seen:raise ValueError('existing principal differs or dashboard grant already present')
        seen.add(row['uid'])
        for field in ('private_read','write'):
            values=row[field]
            if type(values) is not list or len(values)>128 or any(type(repo) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',repo) for repo in values) or len(set(values))!=len(values):raise ValueError('existing repository scope invalid')
        if not set(row['write'])<=set(row['private_read']):raise ValueError('existing write scope invalid')
    result=copy.deepcopy(value);result['principals'].append(dict(uid=993,private_read=['jarvis'],write=[]))
    if len(encoded(result))>128*1024:raise ValueError('proposed policy exceeds bound')
    return result


def protected(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if item.is_symlink() or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected activation path required')


def command(argv):return subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,timeout=30,env=ENV,cwd='/')


def status(unit):
    result=command(['/usr/bin/systemctl','show',unit,'--property=LoadState,ActiveState,MainPID,UnitFileState'])
    if result.returncode:raise ValueError('unit state unavailable')
    return dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)


def no_listener(port):
    for file in ('/proc/net/tcp','/proc/net/tcp6'):
        if file.endswith('tcp6') and not Path(file).exists():continue
        for line in Path(file).read_text().splitlines()[1:]:
            fields=line.split()
            if fields[3]=='0A' and int(fields[1].split(':')[1],16)==port:raise ValueError('origin port already listening')


def preflight(release,expected,config_sha):
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit administrator activation review required')
    release=Path(release)
    if not re.fullmatch('/opt/rras-engineering/releases/history-web-[0-9a-f]{12}',str(release)):raise ValueError('exact installed release required')
    manifest,files=verify(release,expected)
    if manifest['release']!=str(release):raise ValueError('installed release identity differs')
    protected(release);protected(CONFIG);protected(POLICY);protected(JOURNALS.parent)
    for name in files:
        info=(release/name).lstat()
        if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o444:raise ValueError('installed payload custody differs')
    raw=regular(CONFIG,16384)
    if type(config_sha) is not str or not re.fullmatch('[0-9a-f]{64}',config_sha) or hashlib.sha256(raw).hexdigest()!=config_sha:raise ValueError('installed config changed')
    config=decode(raw)
    if (config.get('uid')!=993 or config.get('gid')!=993 or config.get('history_uid')!=995 or config.get('repositories')!=['jarvis'] or
            config.get('bind')!='172.19.0.1' or config.get('port')!=18764 or config.get('history_socket')!='/run/rras-engineering-history/service.sock'):raise ValueError('reviewed scope differs')
    info=CONFIG.lstat()
    if info.st_gid!=993 or stat.S_IMODE(info.st_mode)!=0o640:raise ValueError('protected configuration mode differs')
    user=pwd.getpwnam(ACCOUNT);group=grp.getgrnam(ACCOUNT)
    if (user.pw_uid!=993 or user.pw_gid!=993 or user.pw_dir!='/nonexistent' or user.pw_shell!='/usr/sbin/nologin' or group.gr_gid!=993 or group.gr_mem or
            set(os.getgrouplist(ACCOUNT,993))!={993} or any((item.pw_gid==993 or item.pw_uid==993) and item.pw_name!=ACCOUNT for item in pwd.getpwall())):raise ValueError('dashboard identity differs')
    unit=Path('/etc/systemd/system')/WEB;protected(unit)
    if regular(unit)!=files['deployment/rras-engineering-history-web.service']:raise ValueError('installed unit changed')
    state=status(WEB)
    if state.get('LoadState')!='loaded' or state.get('ActiveState')!='inactive' or state.get('MainPID')!='0' or state.get('UnitFileState')!='disabled':raise ValueError('dashboard baseline not inactive/disabled')
    history=status(HISTORY)
    if history.get('ActiveState')!='active' or int(history.get('MainPID','0'))<1:raise ValueError('history service unavailable')
    policy=regular(POLICY,128*1024);candidate=encoded(proposed_policy(decode(policy)))
    journal=JOURNALS/release.name/'activation-01'
    if JOURNALS.exists() or JOURNALS.is_symlink():protected(JOURNALS)
    if journal.parent.exists() or journal.parent.is_symlink():protected(journal.parent)
    if journal.exists() or journal.is_symlink():raise ValueError('preserve existing activation; no retry')
    temporary=POLICY.with_name('.rras-web-993-'+hashlib.sha256(candidate).hexdigest()[:12]+'.json')
    if temporary.exists() or temporary.is_symlink():raise ValueError('preserve existing policy preparation')
    no_listener(18764)
    network=command(['/usr/bin/docker','inspect','cloudflared','--format','{{.HostConfig.NetworkMode}}'])
    ipam=command(['/usr/bin/docker','network','inspect','jarvis-net','--format','{{json .IPAM.Config}}'])
    if network.returncode or network.stdout.strip()!=b'jarvis-net' or ipam.returncode or decode(ipam.stdout)!=[{'Subnet':'172.19.0.0/16','Gateway':'172.19.0.1'}]:raise ValueError('connector network baseline differs')
    review=dict(phase='dashboard_activation_preflight_passed',release=str(release),manifest_sha256=expected,config_sha256=config_sha,
        history_pid=history['MainPID'],policy_before_sha256=hashlib.sha256(policy).hexdigest(),policy_after_sha256=hashlib.sha256(candidate).hexdigest(),
        existing_principals=len(decode(policy)['principals']),proposed_reader_uid=993,private_read=['jarvis'],write=[],
        mutations=False,activation_authorized=False,cloudflare_changed=False)
    return review,policy,candidate,journal,temporary,config


def bind_review(review,before,after,pid):
    if (before!=review['policy_before_sha256'] or after!=review['policy_after_sha256'] or pid!=review['history_pid']):raise ValueError('reviewed activation baseline changed')


def write_new(path,raw,mode=0o600,gid=0):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),0,gid);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    sync(path.parent)


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


class Activation:
    def __init__(self,journal):self.journal=journal;self.step=0
    def run(self,argv,tag):
        self.step+=1;prefix=f'{self.step:02d}-{tag}'
        write_new(self.journal/(prefix+'-intent.json'),encoded({'argv':argv}))
        result=command(argv);write_new(self.journal/(prefix+'-stdout'),result.stdout);write_new(self.journal/(prefix+'-stderr'),result.stderr)
        if result.returncode:raise ValueError('activation command stopped; preserve evidence')
        return result


def activate(release,expected,config_sha,before,after,pid):
    review,policy,candidate,journal,temporary,config=preflight(release,expected,config_sha);bind_review(review,before,after,pid)
    os.umask(0o077)
    if not JOURNALS.exists():JOURNALS.mkdir(mode=0o700);sync(JOURNALS.parent)
    if not journal.parent.exists():journal.parent.mkdir(mode=0o700);sync(JOURNALS)
    journal.mkdir(mode=0o700);sync(journal.parent);engine=Activation(journal);web_attempted=False
    write_new(journal/'intent.json',encoded(review));write_new(journal/'policy-before.json',policy);write_new(journal/'policy-after.json',candidate)
    try:
        info=POLICY.lstat()
        if info.st_uid!=0 or info.st_gid!=995 or stat.S_IMODE(info.st_mode)!=0o640:raise ValueError('history policy custody differs')
        write_new(temporary,candidate,mode=0o640,gid=995)
        if hashlib.sha256(regular(POLICY,128*1024)).hexdigest()!=before:raise ValueError('policy changed before atomic replacement')
        os.replace(temporary,POLICY);sync(POLICY.parent)
        engine.run(['/usr/bin/systemctl','restart',HISTORY],'restart-history-load-grant')
        for _ in range(100):
            state=status(HISTORY)
            if state.get('ActiveState')=='active' and int(state.get('MainPID','0'))>0 and state['MainPID']!=pid and Path(config['history_socket']).exists():break
            time.sleep(0.1)
        else:raise ValueError('history restart not established')
        loaded_history_pid=state['MainPID']
        probe="""import importlib.util,sys,json
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'vendor'))
s=importlib.util.spec_from_file_location('active_entry',root/'engineering/tools/rras_history_web/entry.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
v=m.protected_configuration('/etc/rras-engineering-history-web/config.json');m.identity(v)
u=m.local('history').local('unix');r=u.call(v['history_socket'],995,dict(method='history',repository_id='jarvis',offset=0,limit=1))
assert r['audience']=='authorized_repository_private' and r['authority_granted'] is False
try:u.call(v['history_socket'],995,dict(method='history',repository_id='ungranted_repository',offset=0,limit=1))
except ValueError:pass
else:raise ValueError('other repository accessible')
a=m.local('access');cfg=a.AccessConfig(v['issuer'],v['audience'],v['email'],v['origin']);keys=a.Keys(cfg);public=keys.fetch();validator=a.Keys(cfg,loader=lambda:public);validator.get(public['keys'][0]['kid'])
print(json.dumps(dict(actual_uid993_read_verified=True,other_repository_denied=True,live_public_keys_verified=True,production_records_written=0)))
"""
        result=engine.run(['/usr/bin/setpriv','--reuid','993','--regid','993','--clear-groups','--no-new-privs','--bounding-set=-all',
            '--inh-caps=-all','--ambient-caps=-all',PYTHON,'-I','-S','-B','-c',probe,review['release']],'verify-reader-and-live-keys')
        if decode(result.stdout).get('actual_uid993_read_verified') is not True:raise ValueError('reader probe differs')
        web_attempted=True;engine.run(['/usr/bin/systemctl','start',WEB],'start-dashboard')
        for _ in range(100):
            state=status(WEB)
            if state.get('ActiveState')=='active' and int(state.get('MainPID','0'))>0:
                try:
                    connection=http.client.HTTPConnection('172.19.0.1',18764,timeout=2)
                    connection.request('GET','/api/repositories',headers={'Host':config['origin'].removeprefix('https://')})
                    response=connection.getresponse();body=response.read(4097);headers=dict(response.getheaders());connection.close()
                    if response.status==403 and len(body)<=4096 and 'no-store' in headers.get('cache-control',''):break
                except OSError:pass
            time.sleep(0.1)
        else:raise ValueError('unauthenticated origin refusal not verified')
        actual=dict(line.split(':',1) for line in (Path('/proc')/state['MainPID']/'status').read_text().splitlines() if ':' in line)
        if (set(actual['Uid'].split())!={'993'} or set(actual['Gid'].split())!={'993'} or set(actual['Groups'].split())-{'993'} or
                actual['NoNewPrivs'].strip()!='1' or any(int(actual[key].strip(),16) for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))):raise ValueError('actual dashboard identity differs')
        engine.run(['/usr/bin/systemctl','enable',WEB],'enable-dashboard-at-boot')
        final=status(WEB)
        if (final.get('UnitFileState')!='enabled' or final.get('ActiveState')!='active' or final.get('MainPID')!=state['MainPID'] or
                status(HISTORY).get('MainPID')!=loaded_history_pid or hashlib.sha256(regular(POLICY,128*1024)).hexdigest()!=after):raise ValueError('activation final state differs')
        value=dict(phase='dashboard_origin_activation_complete',release=review['release'],journal=str(journal),uid=993,
            service_running=True,enabled_at_boot=True,read_only_grant_loaded=True,history_service_restarted=True,
            unauthenticated_origin_denied=True,live_public_keys_verified=True,production_records_written=0,
            cloudflare_changed=False,authenticated_browser_verified=False,model_api_calls=0,automatic_retry=False)
        write_new(journal/'complete.json',encoded(value));return value
    except Exception:
        write_new(journal/'failure-private.txt',traceback.format_exc().encode())
        if web_attempted:
            for action in ('stop','disable'):
                result=command(['/usr/bin/systemctl',action,WEB]);write_new(journal/('failure-cleanup-'+action+'.json'),encoded({'returncode':result.returncode}))
        # Keep the current policy and all database/history bytes. Never restore
        # data or overwrite a concurrently changed policy as deployment recovery.
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('preflight','activate'))
    parser.add_argument('--release',required=True);parser.add_argument('--manifest-sha256',required=True);parser.add_argument('--config-sha256',required=True)
    parser.add_argument('--policy-before');parser.add_argument('--policy-after');parser.add_argument('--history-pid');args=parser.parse_args()
    try:
        result=preflight(args.release,args.manifest_sha256,args.config_sha256)[0] if args.operation=='preflight' else activate(args.release,args.manifest_sha256,args.config_sha256,args.policy_before,args.policy_after,args.history_pid)
        print(json.dumps(result,indent=2))
    except Exception as error:
        print(json.dumps(dict(phase='dashboard_activation_stopped',exception_type=type(error).__name__,
            frames=[dict(file=Path(frame.filename).name,line=frame.lineno,function=frame.name) for frame in traceback.extract_tb(error.__traceback__)],
            protected_evidence=str(JOURNALS),automatic_retry=False)),file=sys.stderr);raise SystemExit(1)
