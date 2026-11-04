"""Protected dashboard startup. No installer, grant mutation or action transport."""
import argparse
from functools import lru_cache
import importlib.util
import ipaddress
import logging
import os
from pathlib import Path
import stat


@lru_cache(maxsize=4)
def local(name):
    spec=importlib.util.spec_from_file_location('history_web_entry_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def configuration(value):
    fields={'contract','uid','gid','history_uid','history_socket','repositories','issuer','audience','email','origin','bind','port'}
    if type(value) is not dict or set(value)!=fields or value['contract']!='engineering-history-web.v1':raise ValueError('configuration refused')
    for field in ('uid','gid','history_uid'):
        if type(value[field]) is not int or not 1<=value[field]<2**32-1:raise ValueError('identity refused')
    if value['uid'] in (994,995,996,997,1000) or value['gid'] in (994,995,996,997,1000) or value['uid']==value['history_uid']:
        raise ValueError('separate dedicated identity required')
    transport=local('history').local('unix');transport.uid(value['history_uid']);transport.endpoint(value['history_socket'])
    local('history').Reader(value['repositories'],None)
    local('access').AccessConfig(value['issuer'],value['audience'],value['email'],value['origin'])
    # Never infer wildcard, DNS, LAN or connector routing from the environment.
    if type(value['bind']) is not str:raise ValueError('explicit IPv4 origin required')
    address=ipaddress.IPv4Address(value['bind'])
    if not (address.is_loopback or any(address in ipaddress.IPv4Network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))):
        raise ValueError('explicit private origin required')
    if type(value['port']) is not int or not 1024<=value['port']<=65535:raise ValueError('unprivileged port required')
    return dict(value)


def protected_configuration(path):
    p=Path(path)
    if not p.is_absolute() or p.resolve(strict=True)!=p:raise ValueError('canonical configuration required')
    for parent in (p.parent,*p.parent.parents):
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('root-owned configuration ancestors required')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_gid!=os.getgid() or
                stat.S_IMODE(info.st_mode)!=0o640 or info.st_nlink!=1 or not 1<=info.st_size<=16384):
            raise ValueError('root-owned bounded configuration required')
        raw=stream.read(16385)
    if len(raw)>16384:raise ValueError('bounded configuration required')
    return configuration(local('access').strict_json(raw))


def identity(value,status_path='/proc/self/status'):
    if (os.getuid()!=value['uid'] or os.geteuid()!=value['uid'] or os.getgid()!=value['gid'] or os.getegid()!=value['gid'] or
            set(os.getgroups())-{value['gid']}):raise ValueError('dedicated identity required')
    status=dict(line.split(':',1) for line in Path(status_path).read_text().splitlines() if ':' in line)
    if status.get('NoNewPrivs','').strip()!='1':raise ValueError('no-new-privileges required')
    for name in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'):
        if name not in status or int(status[name].strip(),16)!=0:raise ValueError('zero capabilities required')


def application(value):
    history=local('history');transport=history.local('unix')
    def call(message):
        if type(message) is not dict or message.get('method') not in ('history','document'):raise ValueError('reads only')
        return transport.call(value['history_socket'],value['history_uid'],message)
    reader=history.Reader(value['repositories'],call)
    config=local('access').AccessConfig(value['issuer'],value['audience'],value['email'],value['origin'])
    return local('app').create_app(reader,local('access').Access(config))


def server_options(value):
    return dict(host=value['bind'],port=value['port'],loop='asyncio',http='h11',ws='none',lifespan='off',
        workers=1,reload=False,proxy_headers=False,forwarded_allow_ips=[],access_log=False,log_config=None,
        server_header=False,date_header=False,limit_concurrency=16,backlog=16,timeout_keep_alive=2,
        timeout_graceful_shutdown=10,h11_max_incomplete_event_size=32768)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    args=parser.parse_args(argv)
    # Clear inherited provider credentials, proxy configuration and Python paths.
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8')
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    try:
        value=protected_configuration(args.config);identity(value)
        import uvicorn
        uvicorn.run(application(value),**server_options(value))
    except Exception:parser.exit(1,'Dashboard stopped; preserve protected configuration and host evidence.\n')


if __name__=='__main__':main()
