"""Synthetic catalog writer roles for the isolated numeric-UID systemd fixture."""
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
STATE=Path('/var/lib/rras-curated-writer-acceptance-attempt03-20261029')
UID=61143


def local(name):
    spec=importlib.util.spec_from_file_location('writer_probe_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def denied(path,write=False):
    try:fd=os.open(path,(os.O_WRONLY|os.O_CREAT if write else os.O_RDONLY)|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    except (PermissionError,OSError) as error:
        if error.errno not in (1,13,30):raise
    else:os.close(fd);raise ValueError('fixture boundary allowed forbidden file access')


def network_boundary(host_namespace,current_namespace,device_text,route_text):
    if (not isinstance(host_namespace,str) or not host_namespace.startswith('net:[') or
            current_namespace==host_namespace):raise ValueError('network namespace not isolated')
    devices={line.split(':',1)[0].strip() for line in device_text.splitlines() if ':' in line}
    routes=[line for line in route_text.splitlines()[1:] if line.strip()]
    if devices!={'lo'} or routes:raise ValueError('network boundary differs')
    return {'distinct_namespace':True,'interfaces':['lo'],'ipv4_routes':0}


def run(role):
    if os.getuid()!=UID or os.geteuid()!=UID or os.getgid()!=UID or not set(os.getgroups())<={UID}:raise ValueError('numeric fixture identity differs')
    catalog=STATE/'private/catalog';pub=local('curated_publication');c=local('contract')
    if role=='seed':
        pub.initialize(catalog,['example_library'])
        (STATE/'private/same-uid-private').write_bytes(b'SYNTHETIC SAME UID PRIVATE\n')
        os.chmod(STATE/'private/same-uid-private',0o600)
        return {'seeded':True}
    status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if status['NoNewPrivs'].strip()!='1':raise ValueError('new privileges allowed')
    for key in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb'):
        if int(status[key].strip(),16):raise ValueError('capabilities retained')
    host=STATE/'host-network.txt'
    info=host.lstat()
    if host.is_symlink() or info.st_uid!=0 or info.st_mode&0o022 or info.st_size>128:raise ValueError('protected host network reference differs')
    network_boundary(host.read_text().strip(),os.readlink('/proc/self/ns/net'),
                     Path('/proc/self/net/dev').read_text(),Path('/proc/self/net/route').read_text())
    if any(key not in ('PATH','HOME','LANG') for key in os.environ):raise ValueError('unexpected worker environment')
    denied(STATE/'root-private');denied(STATE/'private/same-uid-private')
    denied(STATE/'outside/write-attempt',write=True)
    for path in ('/var/lib/rras-engineering-history','/etc/rras-engineering-history','/run/rras-engineering-history'):
        denied(path)
    if role=='timeout':
        import time
        time.sleep(60);raise ValueError('timeout not enforced')
    if role!='publish':raise ValueError('unknown fixture role')
    raw=sys.stdin.buffer.read(2*1024*1024+1)
    receipt=local('curated_publication_entry').apply(catalog,raw,c.digest(raw))
    page=pub.search(catalog,'example_library','')
    if page['entries'] or page['generation_sha256']!=receipt['generation_sha256']:raise ValueError('catalog readback differs')
    if receipt['human_authenticated'] is not False or receipt['authority_granted'] is not False:raise ValueError('authority inferred')
    return {'boundary_verified':True,'catalog_readback':True,'replayed':receipt['replayed'],'generation_sha256':receipt['generation_sha256']}


if __name__=='__main__':print(json.dumps(run(sys.argv[1])))
