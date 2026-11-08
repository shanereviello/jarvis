"""One passive handoff-state collection/delivery pass; no native execution route."""
import argparse
import fcntl
import http.client
import importlib.util
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('handoff_history_http_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def reader(url,token):
    parsed=urlsplit(url)
    if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or
            not parsed.path.startswith('/webhook/rras-native-handoff-events-prj_') or type(token) is not bytes or
            not 32<=len(token)<=256 or not all(33<=value<=126 for value in token)):raise ValueError('fixed selected history reader required')
    def query(after):
        if type(after) is not int or not 0<=after<2**53:raise ValueError('bounded source cursor required')
        connection=(http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection)(parsed.hostname,parsed.port,timeout=20)
        try:
            connection.request('POST',parsed.path,body=json.dumps(dict(after=after)).encode(),headers=dict(
                **{'Content-Type':'application/json','Authorization':'Bearer '+token.decode()}))
            response=connection.getresponse();raw=response.read(1024*1024+1)
            if response.status!=200 or len(raw)>1024*1024:raise ValueError('bounded selected history page unavailable')
            return local('capture_intake').local('contract').decode(raw,max_bytes=1024*1024)
        finally:connection.close()
    return query


def configuration(path):
    intake=local('capture_intake');path=intake.private(path)
    if path.stat().st_size>1024*1024:raise ValueError('bounded private handoff history job required')
    value=intake.local('contract').decode(path.read_bytes(),max_bytes=1024*1024)
    if (type(value) is not dict or set(value)!={'contract','spool','reader_url','reader_token_file','service_socket','service_uid','selected'} or
            value['contract']!='native-handoff-history-job.v1' or type(value['service_uid']) is not int or value['service_uid']<1):
        raise ValueError('exact private handoff history job required')
    selected=local('handoff_history').configuration(value['selected'])
    for field in ('spool','reader_token_file','service_socket'):
        p=Path(value[field])
        if not p.is_absolute() or p.resolve()!=p:raise ValueError('canonical private job paths required')
    token_file=intake.private(value['reader_token_file'])
    if token_file.stat().st_size>257:raise ValueError('bounded private reader credential required')
    token=token_file.read_bytes().strip();reader(value['reader_url'],token)
    project=next(iter(selected['contexts'].values()))[0]['context']['project_id']
    if urlsplit(value['reader_url']).path!='/webhook/rras-native-handoff-events-'+project:raise ValueError('exact configured project endpoint required')
    return value,token


def run_once(value,token,*,query=None,send=None):
    intake=local('capture_intake');spool=intake.Spool(value['spool']);source=local('handoff_history');selected=source.configuration(value['selected'])
    lock=spool.root/'collector.lock';fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        intake.private(lock);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if query is None:query=reader(value['reader_url'],token)
        if send is None:send=lambda message:intake.local('unix').call(value['service_socket'],value['service_uid'],message)
        try:result=source.poll(spool,selected,query)
        except (ValueError,OSError,TypeError,KeyError):
            context=dict(next(iter(selected['contexts'].values()))[0]['context'],work=None)
            try:spool.source_status(scope=selected['scope'],context=context,session=dict(namespace='n8n_native_handoff',id=source.source_prefix(selected)),
                status='gap',detail='Native handoff collection unconfirmed; retain immutable bridge events and pending queue.')
            except (ValueError,OSError):pass
            result=dict(events_staged=None,after=source.cursor(spool,selected),gap=True,models_started=0)
        return dict(collection=result,delivery=spool.flush(send),models_started=0)
    finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True);args=parser.parse_args()
    try:
        value,token=configuration(args.config);print(json.dumps(run_once(value,token),allow_nan=False))
    except (ValueError,OSError,KeyError,TypeError):parser.exit(1,'Native handoff history pass refused; retain bridge events and pending queue.\n')


if __name__=='__main__':main()
