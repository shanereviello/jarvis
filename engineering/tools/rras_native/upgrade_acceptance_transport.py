"""Acceptance-only Docker namespace adapter; never use for production cutover.

The engine still performs its real verification and mutation protocol. Only its
logical names/network are mapped to a labelled isolated Docker namespace. Paths
must be separately remapped to synthetic root-owned fixture directories.
"""
import copy
from pathlib import Path
import re

LABEL='org.rras.upgrade.acceptance'
ENV={'PATH':'/opt/hermes/bin:/opt/hermes/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    'HOME':'/opt/data','HERMES_HOME':'/opt/data','XDG_CACHE_HOME':'/tmp/cache','PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1','LANG':'C.UTF-8',
    'PLAYWRIGHT_BROWSERS_PATH':'/opt/hermes/.playwright','npm_config_install_links':'false',
    'HERMES_WEB_DIST':'/opt/hermes/hermes_cli/web_dist','HERMES_TUI_DIR':'/opt/hermes/ui-tui',
    'HERMES_WRITE_SAFE_ROOT':'/opt/data','HERMES_DISABLE_LAZY_INSTALLS':'1','HERMES_LAZY_INSTALL_TARGET':'/opt/data/lazy-packages'}

class Transport:
    def __init__(self,api,root,token,image,names,network):
        if not re.fullmatch('[0-9a-f]{32}',token):raise ValueError('fixture token required')
        self.raw=api;self.root=Path(root);self.token=token;self.image=image
        self.prefix='rras-upgrade-test-'+token[:12]+'-';self.network=network
        if network!=self.prefix+'net':raise ValueError('isolated network name required')
        self.names=set(names);self.ids=set();self.calls=[]
        if 'hermes' not in self.names or any(not re.fullmatch('[a-zA-Z0-9_-]+',n) for n in self.names):raise ValueError('literal fixture names required')

    def physical(self,name):
        if name not in self.names:raise ValueError('unadmitted logical container name')
        return self.prefix+name

    def logical(self,name):
        if not name.startswith(self.prefix) or name[len(self.prefix):] not in self.names:raise ValueError('foreign container name; preserve')
        return name[len(self.prefix):]

    def ref(self,ref):
        if ref in self.names:return self.physical(ref)
        if ref in self.ids:return ref
        raise ValueError('unadmitted Docker reference')

    def safe_body(self,body):
        host=body['HostConfig']
        if (body['Image']!=self.image or body['Labels'].get(LABEL)!=self.token or body['User']!='1000:1000' or
            body.get('Entrypoint')!=['/opt/hermes/.venv/bin/python'] or body['Cmd']!=['-I','-B','/opt/hermes/gateway/run.py'] or
            host.get('NetworkMode')!=self.network or host.get('Privileged') is not False or host.get('ReadonlyRootfs') is not True or
            host.get('AutoRemove') is not False or host.get('Binds') or host.get('VolumesFrom') or host.get('PortBindings') or host.get('PublishAllPorts') or
            host.get('PidMode') or host.get('IpcMode') not in ('private','') or host.get('Devices') or host.get('DeviceRequests') or
            host.get('CapAdd') or set(host.get('CapDrop') or [])!={'ALL'} or host.get('SecurityOpt')!=['no-new-privileges']):raise ValueError('fixture container isolation changed')
        env=body.get('Env') or []
        if len(env)!=len(ENV) or dict(v.split('=',1) for v in env)!=ENV:raise ValueError('exact credential-free fixture environment required')
        if set(host.get('Tmpfs') or {})!={'/tmp'} or host.get('GroupAdd') or host.get('DeviceCgroupRules') or host.get('UsernsMode') or host.get('UTSMode'):raise ValueError('fixture namespace or tmpfs settings changed')
        mounts=host.get('Mounts') or []
        if len(mounts)!=7 or len({m['Target'] for m in mounts})!=7:raise ValueError('exact fixture mounts required')
        rw={'/opt/data','/workspace/jarvis-artifacts','/workspace/shared'}
        targets=rw|{'/workspace/git/jarvis','/workspace/git/robot_ws','/opt/rras-workflow','/opt/rras-workflow-history'}
        if {m['Target'] for m in mounts}!=targets:raise ValueError('fixture mount target changed')
        for mount in mounts:
            path=Path(mount['Source'])
            if not path.is_absolute() or path.resolve(strict=True)!=path or self.root not in path.parents or mount['Type']!='bind' or mount.get('ReadOnly') is not (mount['Target'] not in rw):raise ValueError('nonfixture or unsafe source mount')
        if set(body['NetworkingConfig']['EndpointsConfig'])!={self.network}:raise ValueError('fixture network endpoint required')

    def normalize(self,row):
        if row['Config'].get('Labels',{}).get(LABEL)!=self.token or row['Image']!=self.image:raise ValueError('unowned container; preserve')
        name=self.logical(row['Name'].lstrip('/'))
        networks=row['NetworkSettings']['Networks']
        if set(networks)!={self.network}:raise ValueError('nonfixture network; preserve')
        # Check actual descriptor boundaries before translating its namespace.
        body=copy.deepcopy(row['Config']);body['HostConfig']=row['HostConfig'];body['NetworkingConfig']={'EndpointsConfig':networks}
        self.safe_body(body)
        self.ids.add(row['Id']);result=copy.deepcopy(row);result['Name']='/'+name
        network=copy.deepcopy(networks[self.network]);aliases=network.get('Aliases') or []
        network['Aliases']=[self.logical(a) if a.startswith(self.prefix) else a for a in aliases]
        result['NetworkSettings']['Networks']={'jarvis-net':network}
        return result

    def call(self,method,path,body=None):
        self.calls.append((method,path))
        if method=='POST' and path.startswith('/containers/create?name='):
            name=path.removeprefix('/containers/create?name=');physical=self.physical(name)
            value=copy.deepcopy(body);endpoints=value['NetworkingConfig']['EndpointsConfig']
            if set(endpoints)!={'jarvis-net'}:raise ValueError('logical fixture network required')
            endpoint=endpoints['jarvis-net'];endpoint['Aliases']=[self.physical(a) if a in self.names else a for a in endpoint.get('Aliases',[])]
            value['NetworkingConfig']['EndpointsConfig']={self.network:endpoint};self.safe_body(value)
            result=self.raw('POST','/containers/create?name='+physical,value)
            if not isinstance(result,dict) or not re.fullmatch('[0-9a-f]{64}',result.get('Id','')):raise ValueError('ambiguous fixture create')
            self.ids.add(result['Id']);return result
        match=re.fullmatch('/containers/([a-zA-Z0-9_-]+)/(json|start|stop\\?t=60|rename\\?name=([a-zA-Z0-9_-]+))',path)
        if not match:raise ValueError('unadmitted Docker operation')
        ref,action,name=match.groups();actual=self.ref(ref)
        suffix='rename?name='+self.physical(name) if name else action
        if method=='GET' and action=='json':
            row=self.raw('GET','/containers/'+actual+'/json')
            return None if row is None else self.normalize(row)
        if method!='POST' or action=='json':raise ValueError('unadmitted Docker method')
        # Revalidate label, isolation and identity immediately before any mutation.
        row=self.raw('GET','/containers/'+actual+'/json')
        if row is None:raise ValueError('fixture disappeared')
        self.normalize(row)
        return self.raw('POST','/containers/'+actual+'/'+suffix,body)

    def exec_ref(self,ref):
        actual=self.ref(ref);row=self.raw('GET','/containers/'+actual+'/json')
        if row is None:raise ValueError('fixture unavailable')
        self.normalize(row);return actual
