"""Root-run synthetic dashboard acceptance. Fixed fixture paths/IDs; no retry."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd,grp
import signal
import stat
import subprocess
import sys
import time
import traceback
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

STATE=Path('/var/lib/rras-history-web-acceptance-20261104')
RUNTIME=Path('/run/rras-history-web-acceptance-20261104')
PYTHON='/opt/rras-engineering/releases/cpython-3.13.16-ae7041461525/bin/python3.13'
HISTORY='rras-history-web-fixture-store-20261104.service'
WEB='rras-history-web-fixture-http-20261104.service'
ENV={'PATH':'/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8'}
OWNER=61160;READER=61161
WORK='wrk_'+'6'*32;DOC='doc_'+'7'*32


def command(argv,raw=None,timeout=30):return subprocess.run(argv,input=raw,capture_output=True,env=ENV,timeout=timeout)


def checked(argv,raw=None,timeout=30):
    result=command(argv,raw,timeout)
    if result.returncode:raise ValueError('fixture command failed')
    return result.stdout


def write(path,raw,gid=0,mode=0o600):
    with path.open('xb') as stream:os.fchmod(stream.fileno(),mode);os.fchown(stream.fileno(),0,gid);stream.write(raw)


def record(name,value):write(STATE/'private'/name,json.dumps(value,sort_keys=True).encode())


def status(unit):
    raw=checked(['/usr/bin/systemctl','show',unit,'--property=LoadState,ActiveState,MainPID'])
    return dict(line.split('=',1) for line in raw.decode().splitlines() if '=' in line)


def stop(unit):
    checked(['/usr/bin/systemctl','stop',unit])
    for _ in range(50):
        value=status(unit)
        if value.get('ActiveState') in ('inactive','failed') and value.get('MainPID')=='0':return
        time.sleep(0.1)
    raise ValueError('fixture unit not stopped')


def start(unit,properties,argv):
    result=command(['/usr/bin/systemd-run','--quiet','--collect','--unit='+unit,'--service-type=exec',
        *[part for item in properties for part in ('--property',item)],'--',*argv])
    write(STATE/'private'/('start-'+str(time.time_ns())+'.stderr'),result.stderr)
    if result.returncode:raise ValueError('fixture unit start refused')
    for _ in range(100):
        value=status(unit)
        if value.get('ActiveState')=='active' and int(value.get('MainPID','0')):return int(value['MainPID'])
        if value.get('ActiveState') in ('failed','inactive'):break
        time.sleep(0.1)
    raise ValueError('fixture unit unavailable')


def web_properties():
    text=(ROOT/'engineering/config/history-web/rras-engineering-history-web.service.in').read_text()
    text=text.replace('@UID@',str(READER)).replace('@GID@',str(READER)).replace('@RELEASE@',str(ROOT))
    properties=[]
    for line in text.split('[Service]\n',1)[1].split('[Install]',1)[0].splitlines():
        if not line or line.startswith('#'):continue
        key,value=line.split('=',1)
        if key in ('Type','ExecStart','StandardOutput','StandardError','ReadOnlyPaths','InaccessiblePaths'):continue
        properties.append(line)
    return properties+['PrivateNetwork=yes','RuntimeMaxSec=180',
        'ReadOnlyPaths='+str(ROOT)+' '+str(STATE/'config.json')+' '+str(RUNTIME),
        'InaccessiblePaths=-/var/lib/rras-engineering-history -/var/lib/rras-workflow -/var/lib/rras-coding-tasks -/srv/hermes -/etc/rras-engineering-history '+str(STATE/'history')+' '+str(STATE/'private'),
        'StandardOutput=null','StandardError=append:'+str(STATE/'private/web-stderr')]


def verify_process(pid):
    proc=Path('/proc')/str(pid)
    info=dict(line.split(':',1) for line in (proc/'status').read_text().splitlines() if ':' in line)
    if set(info['Uid'].split())!={str(READER)} or set(info['Gid'].split())!={str(READER)} or set(info['Groups'].split())-{str(READER)}:raise ValueError('web identity differs')
    if info['NoNewPrivs'].strip()!='1' or any(int(info[k].strip(),16) for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')):raise ValueError('web capabilities retained')
    if os.readlink(proc/'ns/net')==os.readlink('/proc/self/ns/net'):raise ValueError('web network not isolated')
    environment=(proc/'environ').read_bytes().split(b'\0')
    if any(item.split(b'=',1)[0] not in (b'PATH',b'HOME',b'LANG',b'') for item in environment):
        # /proc/environ exposes the initial exec environment, not Python's later
        # clear(). The launcher itself therefore starts with an empty env.
        raise ValueError('fixture initial environment unexpected')
    for path in (STATE/'history',STATE/'private',Path('/var/lib/rras-engineering-history')):
        target=proc/'root'/str(path).lstrip('/')
        if stat.S_IMODE(target.stat().st_mode)!=0:raise ValueError('private history not masked')
    if not os.statvfs(proc/'root'/str(ROOT).lstrip('/')).f_flag&os.ST_RDONLY:raise ValueError('release writable in unit')


def http(pid,path,token=None,method='GET',host='history.example.test'):
    # Request contents travel over stdin, never token-bearing argv or logs.
    script="""import http.client,json,sys
v=json.load(sys.stdin);c=http.client.HTTPConnection('127.0.0.1',18764,timeout=5)
h={'Host':v['host']}
if v['token'] is not None:h['Cf-Access-Jwt-Assertion']=v['token']
c.request(v['method'],v['path'],headers=h);r=c.getresponse();b=r.read(2097153)
print(json.dumps({'status':r.status,'headers':dict(r.getheaders()),'body':b.decode()}));c.close()
"""
    raw=json.dumps(dict(path=path,token=token,method=method,host=host)).encode()
    return json.loads(checked(['/usr/bin/nsenter','--target',str(pid),'--net','--',PYTHON,'-I','-B','-c',script],raw))


def policy(granted):return {'contract':'engineering-history-access.v1','principals':[{'uid':READER,'private_read':['fixture_library'],'write':[]}] if granted else []}


def service():
    return start(HISTORY,['User='+str(OWNER),'Group='+str(OWNER),'SupplementaryGroups=',
        'NoNewPrivileges=yes','CapabilityBoundingSet=','AmbientCapabilities=','PrivateNetwork=yes','ProtectSystem=strict',
        'ReadWritePaths='+str(STATE/'history')+' '+str(RUNTIME),'RuntimeMaxSec=180',
        'StandardOutput=null','StandardError=append:'+str(STATE/'private/history-stderr')],
        ['/usr/bin/env','-i',*['PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8'],PYTHON,'-I','-B',
         str(ROOT/'engineering/tools/rras_history/production_entry.py'),'serve','--account',str(OWNER),
         '--store',str(STATE/'history'),'--socket',str(RUNTIME/'service.sock'),'--policy',str(STATE/'policy.json')])


def run():
    if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('explicit sudo required')
    for uid in (OWNER,READER):
        try:pwd.getpwuid(uid)
        except KeyError:pass
        else:raise ValueError('fixture UID occupied')
        try:grp.getgrgid(uid)
        except KeyError:pass
        else:raise ValueError('fixture GID occupied')
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                if proc.stat().st_uid==uid:raise ValueError('fixture UID active')
            except FileNotFoundError:pass
    for unit in (HISTORY,WEB):
        if status(unit).get('LoadState')!='not-found':raise ValueError('existing fixture unit; preserve evidence')
    if STATE.exists() or RUNTIME.exists():raise ValueError('fixture already exists; no retry')
    os.umask(0o077);STATE.mkdir(mode=0o755);STATE.chmod(0o755);(STATE/'private').mkdir(mode=0o700)
    (STATE/'history').mkdir(mode=0o700);os.chown(STATE/'history',OWNER,OWNER)
    RUNTIME.mkdir(mode=0o700);os.chown(RUNTIME,OWNER,OWNER)
    write(STATE/'policy.json',json.dumps(policy(True)).encode(),OWNER,0o640)
    value=dict(contract='engineering-history-web.v1',uid=READER,gid=READER,history_uid=OWNER,
        history_socket=str(RUNTIME/'service.sock'),repositories=['fixture_library'],
        issuer='https://fixture.cloudflareaccess.com',audience='fixture-audience',email='owner@example.test',
        origin='https://history.example.test',bind='127.0.0.1',port=18764)
    write(STATE/'config.json',json.dumps(value).encode(),READER,0o640)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));public.update(kid='host-fixture',alg='RS256',use='sig')
    write(STATE/'public-keys.json',json.dumps({'keys':[public]}).encode(),READER,0o640)
    seed=checked(['/usr/bin/unshare','--net','--','/usr/bin/setpriv','--reuid',str(OWNER),'--regid',str(OWNER),
        '--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',PYTHON,'-I','-B',
        str(ROOT/'engineering/tools/rras_history_web/host_probe.py'),'seed'])
    record('seed.json',json.loads(seed))
    original_db=hashlib.sha256((STATE/'history/history.sqlite3').read_bytes()).hexdigest()
    def token(**changes):
        now=int(time.time());claims=dict(iss=value['issuer'],aud=[value['audience']],email=value['email'],sub='synthetic-operator',iat=now-1,nbf=now-1,exp=now+120)
        claims.update(changes);return jwt.encode(claims,key,algorithm='RS256',headers={'kid':'host-fixture'})
    try:
        service()
        for _ in range(100):
            if (RUNTIME/'service.sock').exists():break
            time.sleep(0.1)
        pid=start(WEB,web_properties(),['/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME=/nonexistent','LANG=C.UTF-8',PYTHON,'-I','-B',str(ROOT/'engineering/tools/rras_history_web/host_probe.py'),'serve'])
        for _ in range(100):
            try:
                result=http(pid,'/api/repositories',token())
                if result['status']==200:break
            except ValueError:pass
            time.sleep(0.1)
        else:raise ValueError('web readiness failed')
        verify_process(pid)
        for signed in (None,'invalid',token(email='other@example.test'),token(exp=1)):
            result=http(pid,'/api/works?repository_id=fixture_library',signed)
            if result['status']!=403 or 'Synthetic dashboard' in result['body']:raise ValueError('invalid access leaked')
        if http(pid,'/',token(),host='other.example.test')['status']!=403:raise ValueError('wrong host accepted')
        if http(pid,'/api/works?repository_id=fixture_library',token(),method='POST')['status']!=405:raise ValueError('write route accepted')
        result=http(pid,'/api/works?repository_id=fixture_library',token())
        if result['status']!=200 or 'Synthetic dashboard host acceptance' not in result['body'] or 'no-store' not in result['headers'].get('cache-control',''):raise ValueError('exact work read failed')
        result=http(pid,'/api/documents/'+DOC+'?repository_id=fixture_library&work_id='+WORK+'&version=1',token())
        doc=json.loads(result['body'])
        if result['status']!=200 or hashlib.sha256(doc['markdown'].encode()).hexdigest()!=doc['manifest']['markdown_sha256']:raise ValueError('document digest differs')
        if http(pid,'/api/works?repository_id=other_library',token())['status']!=503:raise ValueError('other repository accepted')
        # The actual reader UID cannot submit notes through the authorized socket.
        request=dict(contract='engineering-history.v1',operation='checkpoint.append',client_event_key='denied-reader-note',
            expected_head=doc['manifest']['work_revision_sha256'],source={'kind':'agent_reported','namespace':'fixture','id':None},occurred_at=None,
            body=dict(work_item_id=WORK,work_revision_sha256=doc['manifest']['work_revision_sha256'],checkpoint_type='progress',
                summary='Must not be written',decisions=[],next_action='None',references=[]))
        code="""import sys,importlib.util
sys.path.insert(0,VENDOR)
s=importlib.util.spec_from_file_location('u',UNIX);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
read=m.call(SOCKET,OWNER,{'method':'history','repository_id':'fixture_library','offset':0,'limit':10})
assert len(read['records'])==2
m.local('contract').validate(REQUEST)
try:m.call(SOCKET,OWNER,{'method':'submit','request':REQUEST})
except ValueError:raise SystemExit(0)
raise SystemExit(1)
""".replace('VENDOR',repr(str(ROOT/'vendor'))).replace('UNIX',repr(str(ROOT/'engineering/tools/rras_history/unix.py'))).replace('SOCKET',repr(str(RUNTIME/'service.sock'))).replace('OWNER',str(OWNER)).replace('REQUEST',repr(request))
        checked(['/usr/bin/setpriv','--reuid',str(READER),'--regid',str(READER),'--clear-groups','--no-new-privs',PYTHON,'-I','-B','-c',code])
        stop(HISTORY)
        if http(pid,'/api/works?repository_id=fixture_library',token())['status']!=503:raise ValueError('service outage reused history')
        (STATE/'policy.json').write_bytes(json.dumps(policy(False)).encode())
        service()
        for _ in range(100):
            if (RUNTIME/'service.sock').exists():break
            time.sleep(0.1)
        else:raise ValueError('revoked history socket absent')
        acl=checked(['/usr/bin/getfacl','--numeric','--omit-header',str(RUNTIME/'service.sock')])
        if ('user:'+str(READER)+':').encode() in acl:raise ValueError('revoked reader ACL retained')
        # No stale in-memory result after actual service policy revocation/restart.
        if http(pid,'/api/works?repository_id=fixture_library',token())['status']!=503:raise ValueError('revocation reused history')
        result=dict(phase='isolated_dashboard_host_verified',root=str(STATE),service_uid=OWNER,dashboard_uid=READER,
            cases=['actual_root_owned_config_and_hardened_numeric_uid_unit','no_extra_groups_capabilities_or_provider_environment',
                'private_network_and_masked_history_paths','signed_fixture_origin_tokens_and_invalid_access_denial',
                'exact_cross_uid_history_and_document_digest','other_repository_and_write_routes_denied',
                'actual_unix_reader_submission_denied','service_outage_and_restart_revocation_no_cached_history'],
            api_calls=0,real_credentials_used=False,production_services_mutated=False,production_history_changed=False,
            production_journal_changed=False,cloudflare_changed=False,fixture_units_stopped=True,permanent_accounts_created=False,
            real_cloudflare_key_fetch_tested=False,connector_route_tested=False,automatic_retry=False)
    finally:
        for unit in (WEB,HISTORY):
            if status(unit).get('LoadState')!='not-found':stop(unit)
    if (RUNTIME/'service.sock').exists():raise ValueError('fixture socket retained')
    if hashlib.sha256((STATE/'history/history.sqlite3').read_bytes()).hexdigest()!=original_db:raise ValueError('fixture source database changed')
    result['fixture_source_database_unchanged']=True
    record('result.json',result)
    return result


if __name__=='__main__':
    try:print(json.dumps(run(),indent=2))
    except Exception as error:
        if (STATE/'private').is_dir():
            path=STATE/'private'/('failure-'+str(time.time_ns())+'.txt');path.write_text(traceback.format_exc());path.chmod(0o600)
        print(json.dumps({'phase':'dashboard_host_acceptance_stopped','exception_type':type(error).__name__,
            'frames':[{'file':Path(frame.filename).name,'function':frame.name,'line':frame.lineno} for frame in traceback.extract_tb(error.__traceback__)],
            'protected_evidence':str(STATE),'automatic_retry':False}),file=sys.stderr)
        raise SystemExit(1)
