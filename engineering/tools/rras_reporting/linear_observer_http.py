"""Private n8n read transport and one passive collection/delivery pass."""
import argparse
import fcntl
import http.client
import importlib.util
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from jsonschema import ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('observer_http_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def reader(url,token):
    parsed=urlsplit(url)
    if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or
            parsed.query or parsed.fragment or not parsed.path.startswith('/webhook/rras-history-linear-read-') or
            type(token) is not bytes or not 32<=len(token)<=256 or not all(33<=x<=126 for x in token)):
        raise ValueError('fixed private authenticated reader endpoint required')
    def query(value):
        body=dict(operation=value['operation'],object_id=value['object_id'],after=value['variables'].get('after'))
        raw=json.dumps(body,separators=(',',':')).encode()
        kind=http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection
        connection=kind(parsed.hostname,parsed.port,timeout=20)
        try:
            connection.request('POST',parsed.path,body=raw,headers={'Content-Type':'application/json','Authorization':'Bearer '+token.decode()})
            response=connection.getresponse();payload=response.read(2*1024*1024+1)
            if response.status!=200 or len(payload)>2*1024*1024:raise ValueError('selected reader unavailable')
            return local('capture_intake').local('contract').decode(payload,max_bytes=2*1024*1024)
        finally:connection.close()
    return query


def configuration(path):
    intake=local('capture_intake');path=intake.private(path)
    if path.stat().st_size>1024*1024:raise ValueError('bounded private observer job required')
    value=intake.local('contract').decode(path.read_bytes(),max_bytes=1024*1024)
    if (type(value) is not dict or set(value)!={'contract','spool','reader_url','reader_token_file','service_socket','service_uid','selected'} or
            value['contract']!='engineering-linear-poll-job.v1' or type(value['service_uid']) is not int or value['service_uid']<0):
        raise ValueError('exact passive observer job required')
    local('linear_observer').configuration(value['selected'])
    for name in ('spool','service_socket','reader_token_file'):
        p=Path(value[name])
        if not p.is_absolute() or p.resolve()!=p:raise ValueError('canonical private job paths required')
    token_file=intake.private(value['reader_token_file'])
    if token_file.stat().st_size>257:raise ValueError('bounded private reader credential required')
    token=token_file.read_bytes().strip();reader(value['reader_url'],token)
    if urlsplit(value['reader_url']).path!='/webhook/rras-history-linear-read-'+value['selected']['project_id']:
        raise ValueError('endpoint must pin the selected project')
    return value,token


def run_once(value,token,*,query=None,send=None):
    intake=local('capture_intake');spool=intake.Spool(value['spool']);lock=spool.root/'collector.lock'
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        intake.private(lock);fcntl.flock(fd,fcntl.LOCK_EX)
        if query is None:query=reader(value['reader_url'],token)
        if send is None:send=lambda message:intake.local('unix').call(value['service_socket'],value['service_uid'],message)
        result=local('linear_observer').poll(spool,value['selected'],query)
        return dict(collection=result,delivery=spool.flush(send),models_started=0)
    finally:os.close(fd)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True);args=parser.parse_args(argv)
    try:
        value,token=configuration(args.config);print(json.dumps(run_once(value,token),allow_nan=False))
    except (ValueError,OSError,TypeError,KeyError,ValidationError):
        parser.exit(1,'Passive Linear pass refused; retain queue and request a fresh authorized configuration.\n')


if __name__=='__main__':main()
