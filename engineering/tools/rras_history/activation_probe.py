"""Read-only first activation probes, executed only as explicit local clients."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys


def denied(path):
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except PermissionError:return
    else:os.close(fd);raise ValueError('private file unexpectedly accessible')


def main():
    release=Path(sys.argv[1]);service_uid=int(sys.argv[2]);role=sys.argv[3]
    caller=os.getuid()
    if caller!=os.geteuid() or caller not in (1000,996,997):raise ValueError('unexpected activation probe identity')
    if os.getgroups():raise ValueError('probe supplementary groups must be empty')
    for path in ('/var/lib/rras-engineering-history/history.sqlite3','/etc/rras-engineering-history/access-policy.json'):
        denied(path)
    endpoint='/run/rras-engineering-history/service.sock'
    if role=='worker-denial':
        if caller not in (996,997):raise ValueError('wrong worker probe identity')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(3)
            try:client.connect(endpoint)
            except PermissionError:pass
            else:raise ValueError('worker socket unexpectedly accessible')
        return {'uid':caller,'private_files_denied':True,'socket_denied':True}
    if role!='reader' or caller!=1000:raise ValueError('wrong reader probe identity')
    sys.path.insert(0,str(release/'vendor'))
    spec=importlib.util.spec_from_file_location('accepted_history_transport',release/'engineering/tools/rras_history/unix.py')
    transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
    for repo in ('jarvis','robot_ws'):
        answer=transport.call(endpoint,service_uid,{'method':'history','repository_id':repo,'offset':0,'limit':1})
        if answer.get('records')!=[]:raise ValueError('first activation expected empty history')
    for message in ({'method':'execute'},{'method':'history','repository_id':'ungranted_activation_probe','offset':0,'limit':1}):
        try:transport.call(endpoint,service_uid,message)
        except ValueError:pass
        else:raise ValueError('unexpected action or repository access')
    return {'uid':caller,'repositories':['jarvis','robot_ws'],'empty_history':True,
            'ungranted_repository_denied':True,'no_action_route':True,'private_files_denied':True}


if __name__=='__main__':print(json.dumps(main()))
