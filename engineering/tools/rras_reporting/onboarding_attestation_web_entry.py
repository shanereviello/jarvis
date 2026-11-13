"""Protected entry point for an operator attestation browser, inactive by default."""
import argparse
import importlib.util
import ipaddress
import logging
import os
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('attestation_web_entry_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def web(name):
    path=Path(__file__).resolve().parent.parent/'rras_history_web'/(name+'.py')
    spec=importlib.util.spec_from_file_location('attestation_dashboard_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def configuration(value,uid,gid):
    fields={'browser_uid','browser_gid','operator_uid','operator_socket','bind','port','access'}
    if type(value) is not dict or not fields<=set(value) or set(value)-fields-{'path_prefix'}:raise ValueError('exact browser service configuration required')
    local('onboarding_attestation_web').path_prefix(value.get('path_prefix',''))
    u=local('onboarding_broker_unix').unix()
    for key in ('browser_uid','browser_gid','operator_uid'):u.uid(value[key])
    if value['browser_uid']!=uid or value['browser_gid']!=gid or value['operator_uid']==uid:
        raise ValueError('distinct dedicated browser identity required')
    u.endpoint(value['operator_socket'])
    try:address=ipaddress.ip_address(value['bind'])
    except ValueError:raise ValueError('fixed private browser bind required') from None
    private_networks=tuple(ipaddress.ip_network(x) for x in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
    if not isinstance(address,ipaddress.IPv4Address) or not (address.is_loopback or any(address in n for n in private_networks)):
        raise ValueError('fixed private browser bind required')
    if type(value['port']) is not int or not 1<=value['port']<=65535:raise ValueError('exact browser port required')
    a=value['access']
    if type(a) is not dict or set(a)!={'issuer','audience','email','origin'}:raise ValueError('exact browser access required')
    web('access').AccessConfig(**a)
    return value


def application(value):
    access_module=web('access');access=access_module.Access(access_module.AccessConfig(**value['access']))
    client=local('onboarding_operator_browser_unix').Client(value['operator_socket'],value['operator_uid'])
    return local('onboarding_attestation_web').create_app(client,access,value.get('path_prefix',''))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True);args=parser.parse_args()
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8');os.umask(0o077);logging.disable(logging.CRITICAL)
    try:
        value=configuration(local('protected_config').decode(args.config,require_root=True),os.getuid(),os.getgid())
        if os.geteuid()!=os.getuid() or os.getegid()!=os.getgid() or set(os.getgroups())-{os.getgid()}:
            raise ValueError('dedicated unprivileged browser identity required')
        import uvicorn
        uvicorn.run(application(value),**web('entry').server_options(value))
    except Exception:parser.exit(1,'Operator attestation browser refused; preserve protected configuration and host evidence.\n')


if __name__=='__main__':main()
