"""Explicit root upgrade activation/rollback; no auto-retry, cleanup or DB restore.

Run only a protected reviewed bootstrap and pass the exact staged manifest digest.
Root private journals retain intent before every external or wrapper mutation.
"""
import argparse
import copy
import fcntl
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import time
import traceback
import uuid

STATUS="""import json
from gateway.status import read_runtime_status,runtime_status_is_stale,runtime_status_pid_is_live,is_gateway_running
r=read_runtime_status() or {}
print(json.dumps({'state':r.get('gateway_state'),'active_agents':r.get('active_agents'),'fresh':not runtime_status_is_stale(r),'live':runtime_status_pid_is_live(r) and is_gateway_running(cleanup_stale=False),'pid':r.get('pid'),'start_time':r.get('start_time')}))
"""
DRAIN="""import json,os,sys,hashlib
from datetime import datetime,timezone
from gateway.drain_control import current_instantiation_epoch,drain_request_path
epoch=current_instantiation_epoch();assert epoch
p=drain_request_path();raw=(json.dumps({'action':'drain','requested_at':datetime.now(timezone.utc).isoformat(),'principal':sys.argv[1],'epoch':epoch,'suppress_notification':True},sort_keys=True)+chr(10)).encode()
f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(f,'wb') as s:s.write(raw);s.flush();os.fsync(s.fileno())
print(json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'epoch':epoch}))
"""
DISCOVERY="""import asyncio,json,os,yaml
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
 d=yaml.safe_load(Path('/opt/data/config.yaml').read_text())
 assert set(d['mcp_servers'])=={'hindsight','jarvis-engineering','linear','linear-actions','rras-coding-preparation','rras-workflow-history','todoist'}
 for name,expected in [('rras-coding-preparation',['coding_task_proposal','prepare_coding_task']),('rras-workflow-history',['workflow_history','workflow_pages'])]:
  e=d['mcp_servers'][name];p=StdioServerParameters(command=e['command'],args=e['args'],env={'PATH':'/usr/bin:/bin','HOME':'/opt/data'})
  async with stdio_client(p) as (r,w):
   async with ClientSession(r,w) as c:
    await c.initialize();assert sorted(t.name for t in (await c.list_tools()).tools)==expected
    if name=='rras-workflow-history':
     response=await c.call_tool('workflow_pages',{});assert not response.is_error
     assert isinstance(json.loads(response.content[0].text)['pages'],list)
 assert os.getuid()==1000
 for p in ('/opt/rras-workflow/release-manifest.json','/opt/rras-workflow-history/index.json'):
  assert os.statvfs(p).f_flag & os.ST_RDONLY
 assert not Path('/var/lib/rras-workflow/journal/workflow.sqlite3').exists()
 print(json.dumps({'verified':True}))
asyncio.run(asyncio.wait_for(main(),25))
"""


def stage_module():
    # The bootstrap must copy both deployment tools into protected custody first.
    path=Path(__file__).with_name('stage_workflow_upgrade.py')
    for item in (Path(__file__),path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('protected deployment tools required')
    spec=importlib.util.spec_from_file_location('upgrade_staging',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class Connection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(self.timeout);self.sock.connect('/var/run/docker.sock')

def api(method,path,body=None):
    if method not in ('GET','POST') or not path.startswith('/containers/'):raise ValueError('unsupported Docker operation')
    conn=Connection('localhost',timeout=90)
    try:
        raw=None if body is None else json.dumps(body,allow_nan=False).encode()
        if raw is not None and len(raw)>8*1024*1024:raise ValueError('bounded Docker request required')
        conn.request(method,path,body=raw,headers={'Content-Type':'application/json'})
        response=conn.getresponse();raw=response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('bounded Docker response required')
        if method=='GET' and response.status==404:return None
        if response.status not in (200,201,204,304):raise ValueError('Docker operation failed; preserve private state')
        return json.loads(raw) if raw else None
    finally:conn.close()

def metadata(path):
    s=Path(path).lstat()
    return {'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'device':s.st_dev,'inode':s.st_ino}

def host_settings(value):
    result=copy.deepcopy(value);result.pop('Mounts',None)
    if result.get('OomKillDisable') is None:result['OomKillDisable']=False
    return result

class Upgrade:
    def __init__(self,journal,expected,stage=None):
        if os.getuid()!=0 or os.geteuid()!=0:raise ValueError('administrator upgrade invocation required')
        self.s=stage or stage_module();self.s.administrator();self.journal=self.s.protected(journal)
        self.expected=expected;self.directory=self.journal/'activation';self.state_path=self.directory/'state.json';self.state=None
        self.load(rollback=True)

    def load(self,rollback=False):
        self.proof,self.manifest,self.plan=self.s.evidence(self.journal,verify_release=not rollback)
        if not re.fullmatch('[0-9a-f]{64}',self.expected) or self.proof['manifest_sha256']!=self.expected:raise ValueError('exact staged manifest required')
        self.release=Path(self.plan['release']);self.old=self.s.decode(self.s.regular(self.journal/'container.original.json'))
        if self.old['Id']!=self.proof['fingerprint']['container_id']:raise ValueError('original container identity changed')
        self.marker=self.s.HERMES_CONFIG.parent/'.drain_request.json'
        self.candidate_name='hermes-candidate-'+self.release.name
        self.retained_name='hermes-rollback-'+self.release.name
        self.failed_name='hermes-failed-'+self.release.name

    def checkpoint(self,phase):
        self.state['phase']=phase
        raw=self.s.encoded(self.state);self.directory.mkdir(mode=0o700,exist_ok=True)
        previous=self.s.regular(self.state_path) if self.state_path.exists() else None
        temp=self.directory/('state-'+uuid.uuid4().hex+'.tmp');self.s.write(temp,raw)
        if previous is not None and self.s.regular(self.state_path)!=previous:raise ValueError('activation state changed')
        os.replace(temp,self.state_path);self.s.sync(self.directory)

    def container(self,ref,optional=False):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',ref):raise ValueError('literal container reference required')
        row=api('GET','/containers/'+ref+'/json')
        if row is None and not optional:raise ValueError('expected container absent')
        return row

    def rpc(self,ref,script,*args):
        return self.s.decode(self.s.command(['/usr/bin/docker','exec','--user','1000:1000',ref,
            '/opt/hermes/.venv/bin/python','-I','-B','-c',script,*args]).stdout)

    def status(self,ref):return self.rpc(ref,STATUS)

    def invariants(self):
        # Never roll back or rewrite journal/history: imports/publications may have
        # legitimately progressed since activation. Check their access roles only.
        for path,values in self.s.ROLE_DIRS.items():self.s.role(path,*values)
        for path,key in ((self.s.CONFIG,'operator_config_sha256'),(self.s.HERMES_CONFIG,'hermes_config_sha256'),(self.s.COMPOSE,'compose_sha256')):
            if self.s.sha(self.s.regular(path,user=path==self.s.HERMES_CONFIG))!=self.proof['fingerprint'][key]:raise ValueError('preserved configuration changed')
        if self.s.sha(self.s.regular(self.s.PROFILE))!=self.plan['profile_sha256'] or self.s.sha(self.s.regular(self.s.CODEX))!=self.plan['codex_config_sha256']:raise ValueError('session pins changed')

    def original(self):
        row=self.container(self.old['Id'])
        if row['Image']!=self.old['Image'] or row['Config']!=self.old['Config'] or host_settings(row['HostConfig'])!=host_settings(self.old['HostConfig']) or row['Mounts']!=self.old['Mounts']:raise ValueError('retained original descriptor changed')
        return row

    def clone_request(self):
        config=copy.deepcopy(self.old['Config']);config['Hostname']='';config['Image']=self.old['Image']
        labels=dict(config.get('Labels') or {});labels.update({'org.rras.workflow.release':self.release.name,
            'org.rras.workflow.upgrade':self.state['operation_id'],
            'com.docker.compose.project.config_files':str(self.s.COMPOSE)+','+str(self.journal/'compose.override.json')});config['Labels']=labels
        host=copy.deepcopy(self.old['HostConfig'])
        if host.get('AutoRemove') or host.get('Binds') or host.get('VolumesFrom'):raise ValueError('unsupported container storage/removal settings')
        found=[]
        for mount in host['Mounts']:
            if mount['Target']=='/opt/rras-workflow':
                if mount['Source']!=self.plan['installed_release'] or mount.get('ReadOnly') is not True:raise ValueError('unexpected original workflow mount')
                mount['Source']=str(self.release);found.append(mount)
        if len(found)!=1:raise ValueError('one existing workflow mount required')
        networks=self.old['NetworkSettings']['Networks']
        if set(networks)!={'jarvis-net'}:raise ValueError('unexpected container network')
        aliases=[a for a in (networks['jarvis-net'].get('Aliases') or []) if a not in (self.old['Id'],self.old['Id'][:12])]
        config['HostConfig']=host;config['NetworkingConfig']={'EndpointsConfig':{'jarvis-net':{'Aliases':aliases}}};return config

    def validate_candidate(self,row):
        expected=self.clone_request()
        actual={k:v for k,v in row['Config'].items() if k!='Hostname'}
        wanted={k:v for k,v in expected.items() if k not in ('Hostname','HostConfig','NetworkingConfig')}
        mounts={r['Destination']:(r['Source'],r['RW'],r['Type']) for r in row['Mounts']}
        if (row['Image']!=self.old['Image'] or actual!=wanted or host_settings(row['HostConfig'])!=host_settings(expected['HostConfig']) or
            mounts!=self.s.mounts(self.release) or len(mounts)!=len(row['Mounts']) or set(row['NetworkSettings']['Networks'])!={'jarvis-net'}):raise ValueError('candidate descriptor differs from reviewed replacement')
        aliases=set(row['NetworkSettings']['Networks']['jarvis-net'].get('Aliases') or [])
        wanted_aliases=set(expected['NetworkingConfig']['EndpointsConfig']['jarvis-net']['Aliases'])
        if not wanted_aliases.issubset(aliases) or aliases-wanted_aliases-{row['Id'],row['Id'][:12],row['Name'].lstrip('/')} :raise ValueError('candidate network aliases changed')
        return row

    def candidate(self):
        ref=self.state.get('candidate_id')
        row=self.container(ref,optional=True) if ref else self.container(self.candidate_name,optional=True)
        if row is None:return None
        if not self.state.get('create_intent'):raise ValueError('candidate exists without root create intent')
        self.validate_candidate(row)
        if ref and row['Id']!=ref:raise ValueError('candidate ID changed')
        if row['Name'] not in ('/'+self.candidate_name,'/hermes','/'+self.failed_name):raise ValueError('candidate name changed')
        if not ref:
            # Read-only reconciliation of an ambiguous create result; never POST again.
            self.state['candidate_id']=row['Id'];self.checkpoint('candidate_reconciled')
        return row

    def wrapper_state(self):
        result={};saved=self.s.decode(self.s.regular(self.journal/'filesystem.original.json'))
        for name in self.s.WRAPPERS:
            path=self.s.SBIN/name;raw=self.s.regular(path)
            if os.listxattr(path):raise ValueError('wrapper attributes require separate review')
            old=self.s.regular(self.journal/('wrappers/'+name+'.original'));new=self.s.regular(self.journal/('wrappers/'+name+'.candidate'))
            info=metadata(path);ops=(self.state or {}).get('wrapper_ops',{}).get(name,{})
            if raw==old:
                expected=ops.get('restore',{}).get('after',saved[str(path)])
                if info!=expected:raise ValueError('original wrapper metadata drift')
                result[name]='old'
            elif raw==new:
                if info!=ops.get('upgrade',{}).get('after'):raise ValueError('unrecorded candidate wrapper replacement')
                result[name]='new'
            else:raise ValueError('wrapper bytes changed')
        return result

    def switch_wrapper(self,name,direction):
        state=self.wrapper_state()[name];wanted='new' if direction=='upgrade' else 'old'
        if state==wanted:return
        path=self.s.SBIN/name;before=metadata(path);original=self.s.regular(path)
        raw=self.s.regular(self.journal/('wrappers/'+name+('.candidate' if direction=='upgrade' else '.original')))
        temp=path.with_name('.rras-'+self.state['operation_id']+'-'+name+'-'+direction)
        self.s.write(temp,raw,before['mode']);os.chown(temp,before['uid'],before['gid']);self.s.sync(path.parent)
        with temp.open('rb') as stream:os.fsync(stream.fileno())
        entry={'before':before,'after':metadata(temp),'temporary':str(temp)}
        self.state.setdefault('wrapper_ops',{}).setdefault(name,{})[direction]=entry
        self.checkpoint('wrapper_'+direction+'_intent')
        if metadata(path)!=before or self.s.regular(path)!=original:raise ValueError('wrapper changed before atomic switch')
        os.replace(temp,path);self.s.sync(path.parent);self.checkpoint('wrapper_'+direction+'_complete')

    def clear_drain(self):
        if not self.marker.exists() and not self.marker.is_symlink():return
        receipt=self.state.get('drain')
        if not receipt:raise ValueError('unowned drain marker; preserve')
        raw=self.s.regular(self.marker,user=True);info=metadata(self.marker)
        if (info['device'],info['inode'],self.s.sha(raw))!=(receipt['device'],receipt['inode'],receipt['sha256']):raise ValueError('drain marker ownership changed')
        self.state['clear_drain_intent']=True;self.checkpoint('clear_drain_intent')
        self.marker.unlink();self.s.sync(self.marker.parent);self.checkpoint('drain_cleared')

    def owned_drain(self,ref):
        receipt=self.state.get('drain')
        if not receipt or receipt['ref']!=ref:raise ValueError('unowned drain marker; preserve')
        raw=self.s.regular(self.marker,user=True);info=metadata(self.marker)
        if (info['device'],info['inode'],self.s.sha(raw))!=(receipt['device'],receipt['inode'],receipt['sha256']):raise ValueError('drain marker ownership changed')
        return receipt

    def stop_drained(self,row):
        ref=row['Id'];before=self.status(ref)
        if self.marker.exists() or self.marker.is_symlink():
            receipt=self.owned_drain(ref)
            if (before['pid'],before['start_time'])!=(receipt['pid'],receipt['start_time']):raise ValueError('gateway identity changed')
        else:
            if before['live'] is not True or before['fresh'] is not True or before['state']!='running':raise ValueError('fresh running gateway required')
            self.state['drain_intent']={'ref':ref,'principal':self.state['operation_id']+'/'+ref[:12], 'pid':before['pid'],'start_time':before['start_time']};self.checkpoint('drain_intent')
            response=self.rpc(ref,DRAIN,self.state['drain_intent']['principal'])
            raw=self.s.regular(self.marker,user=True);info=metadata(self.marker);payload=self.s.decode(raw)
            if info['uid']!=1000 or self.s.sha(raw)!=response['sha256'] or payload['principal']!=self.state['drain_intent']['principal'] or payload['epoch']!=response['epoch']:raise ValueError('uncertain drain receipt')
            self.state['drain']={'ref':ref,'device':info['device'],'inode':info['inode'],'sha256':self.s.sha(raw),'pid':before['pid'],'start_time':before['start_time']}
            self.checkpoint('drain_owned')
        deadline=time.monotonic()+120
        def acknowledged():
            self.owned_drain(ref);observed=self.status(ref)
            if (observed['pid'],observed['start_time'])!=(before['pid'],before['start_time']) or observed['live'] is not True:raise ValueError('gateway identity changed')
            return observed['fresh'] is True and observed['state']=='draining' and type(observed['active_agents']) is int and observed['active_agents']==0
        while not acknowledged():
            if time.monotonic()>=deadline:raise ValueError('fresh idle drain not acknowledged')
            time.sleep(1)
        self.s.idle();self.state['stop_intent']=ref;self.checkpoint('stop_intent')
        if not acknowledged():raise ValueError('idle drain changed before stop')
        api('POST','/containers/'+ref+'/stop?t=60')
        if self.container(ref)['State']['Running']:raise ValueError('stop not verified')
        self.checkpoint('container_stopped');self.clear_drain()

    def verify(self,row,new):
        if new:self.validate_candidate(row)
        else:self.original()
        if row['State']['Running'] is not True:raise ValueError('expected gateway not running')
        observed=self.status(row['Id'])
        if observed['live'] is not True or observed['fresh'] is not True or observed['state']!='running':raise ValueError('fresh healthy gateway required')
        if self.rpc(row['Id'],DISCOVERY)!={'verified':True}:raise ValueError('history/preparation MCP verification failed')
        self.invariants()

    def wait_verify(self,ref,new):
        deadline=time.monotonic()+90
        while True:
            try:self.verify(self.container(ref),new);return
            except (ValueError,OSError,KeyError,subprocess.SubprocessError):
                if time.monotonic()>=deadline:raise
                time.sleep(2)

    def preflight(self):
        self.load();self.s.idle()
        self.s.source_ancestor(self.manifest['source_commit'])
        if self.directory.exists() or self.directory.is_symlink():raise ValueError('activation already fenced; inspect or explicitly roll back')
        if self.s.inspect(self.journal)['phase']!='staged_inactive_verified':raise ValueError('stage preconditions changed')
        self.state={'operation_id':'preflight','wrapper_ops':{}}
        self.wrapper_state();self.clone_request()
        for name in (self.candidate_name,self.retained_name,self.failed_name):
            if self.container(name,optional=True) is not None:raise ValueError('retention name already exists; preserve')
        original=self.original()
        if original['Name']!='/hermes' or not original['State']['Running']:raise ValueError('original is not the live gateway')
        status=self.status(original['Id'])
        if status['live'] is not True or status['fresh'] is not True or status['state']!='running':raise ValueError('gateway unavailable')
        return {'phase':'upgrade_activation_preflight_passed','service_mutations':False,'activation_authorized':False}

    def activate(self,approved=False):
        if approved is not True:raise ValueError('separate activation approval required')
        with self.lock():
            self.preflight();self.directory.mkdir(mode=0o700);self.s.sync(self.journal)
            self.state={'operation_id':uuid.uuid4().hex,'manifest_sha256':self.expected,'original_id':self.old['Id'],'candidate_id':None,'wrapper_ops':{}}
            self.checkpoint('activation_started')
            try:
                self.stop_drained(self.original());self.state['rename_original_intent']=True;self.checkpoint('rename_original_intent')
                api('POST','/containers/'+self.old['Id']+'/rename?name='+self.retained_name)
                self.state['create_intent']=True;self.checkpoint('create_candidate_intent')
                reply=api('POST','/containers/create?name='+self.candidate_name,self.clone_request())
                if not isinstance(reply,dict) or not isinstance(reply.get('Id'),str) or not re.fullmatch('[0-9a-f]{64}',reply['Id']):raise ValueError('uncertain create response')
                self.state['candidate_id']=reply['Id'];self.checkpoint('candidate_created')
                row=self.candidate();self.state['start_candidate_intent']=True;self.checkpoint('start_candidate_intent')
                api('POST','/containers/'+row['Id']+'/start');self.wait_verify(row['Id'],True)
                self.state['rename_candidate_intent']=True;self.checkpoint('rename_candidate_intent')
                api('POST','/containers/'+row['Id']+'/rename?name=hermes')
                for name in self.s.WRAPPERS:self.switch_wrapper(name,'upgrade')
                self.s.idle();self.verify(self.container(row['Id']),True);self.checkpoint('complete')
                return self.public()
            except BaseException:
                self.diagnostic('activation');raise

    def rollback(self,approved=False):
        if approved is not True:raise ValueError('separate rollback approval required')
        with self.lock():
            self.load(rollback=True);self.s.protected(self.directory);self.s.role(self.directory,0,0,0o700)
            self.state=self.s.decode(self.s.regular(self.state_path));self.validate_state();self.invariants();self.s.idle();self.wrapper_state()
            try:
                original=self.original();candidate=self.candidate();live=self.container('hermes',optional=True)
                allowed={original['Id']}|({candidate['Id']} if candidate else set())
                if live is not None and live['Id'] not in allowed:raise ValueError('unrecorded live container; preserve')
                if candidate is not None:
                    if original['State']['Running']:raise ValueError('original unexpectedly running with candidate; preserve')
                    if candidate['State']['Running']:
                        self.stop_drained(candidate)
                    else:self.clear_drain()
                    candidate=self.container(candidate['Id'])
                    if candidate['Name']!='/'+self.failed_name:
                        self.state['retain_candidate_intent']=True;self.checkpoint('retain_candidate_intent')
                        api('POST','/containers/'+candidate['Id']+'/rename?name='+self.failed_name)
                else:
                    if self.state.get('create_intent'):raise ValueError('candidate create outcome unresolved; preserve')
                    if original['State']['Running'] and (self.marker.exists() or self.marker.is_symlink()):self.stop_drained(original)
                    else:self.clear_drain()
                if original['Name'] not in ('/hermes','/'+self.retained_name):raise ValueError('original retention name changed')
                if original['Name']!='/hermes':
                    self.state['restore_original_name_intent']=True;self.checkpoint('restore_original_name_intent')
                    api('POST','/containers/'+original['Id']+'/rename?name=hermes')
                for name in self.s.WRAPPERS:self.switch_wrapper(name,'restore')
                original=self.container(original['Id'])
                if not original['State']['Running']:
                    self.state['restart_original_intent']=True;self.checkpoint('restart_original_intent')
                    api('POST','/containers/'+original['Id']+'/start')
                self.wait_verify(original['Id'],False);self.s.idle();self.checkpoint('rolled_back');return self.public()
            except BaseException:
                self.diagnostic('rollback');raise

    def validate_state(self):
        if (self.state['manifest_sha256']!=self.expected or self.state['original_id']!=self.old['Id'] or
            not re.fullmatch('[0-9a-f]{32}',self.state['operation_id']) or
            self.state['candidate_id'] is not None and not re.fullmatch('[0-9a-f]{64}',self.state['candidate_id'])):raise ValueError('activation state identity changed')

    def diagnostic(self,action):
        try:self.s.write(self.directory/(action+'-error-'+uuid.uuid4().hex+'.txt'),traceback.format_exc().encode()[:65536])
        except OSError:pass

    def public(self):
        return {'phase':self.state['phase'],'release':str(self.release),'journal':str(self.journal),
            'original_container_retained':True,'containers_deleted':False,'configuration_unchanged':True,'journal_restored':False,'automatic_retry':False}

    def lock(self):
        return MaintenanceLock(self.s)

class MaintenanceLock:
    def __init__(self,stage):self.s=stage;self.fd=None
    def __enter__(self):
        path=self.s.JOURNALS/'maintenance.lock';self.s.protected(path.parent)
        self.fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            self.s.protected(path);info=os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_mode&0o077:raise ValueError('private maintenance lock required')
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:os.close(self.fd);self.fd=None;raise
        return self
    def __exit__(self,*args):os.close(self.fd)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('preflight','activate','rollback'))
    p.add_argument('--journal',required=True);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--approve-activation',action='store_true');p.add_argument('--approve-rollback',action='store_true');args=p.parse_args(argv)
    try:
        engine=Upgrade(args.journal,args.manifest_sha256)
        result=engine.preflight() if args.action=='preflight' else engine.activate(args.approve_activation) if args.action=='activate' else engine.rollback(args.approve_rollback)
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError):p.exit(1,'Upgrade stopped; preserve protected evidence. No automatic retry or rollback.\n')
    print(json.dumps(result))

if __name__=='__main__':main()
