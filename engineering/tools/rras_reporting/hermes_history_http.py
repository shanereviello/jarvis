"""One passive selected Jarvis history pass; no native execution or OAuth route."""
import argparse
import fcntl
import http.client
import importlib.util
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_history_http_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def reader(url,token):
    parsed=urlsplit(url)
    if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or
            not parsed.path.startswith('/webhook/rras-hermes-engineering-history-prj_') or type(token) is not bytes or
            not 32<=len(token)<=256 or not all(33<=value<=126 for value in token)):raise ValueError('fixed private selected history reader required')
    def query(cursor):
        if (type(cursor) is not dict or set(cursor)!={'after_admission','after_run','after_checkpoint'} or
                any(type(value) is not int or not 0<=value<2**53 for value in cursor.values())):
            raise ValueError('bounded native cursors required')
        connection=(http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection)(parsed.hostname,parsed.port,timeout=20)
        try:
            connection.request('POST',parsed.path,body=json.dumps(cursor).encode(),headers={
                'Content-Type':'application/json','Authorization':'Bearer '+token.decode()})
            response=connection.getresponse();raw=response.read(1024*1024+1)
            if response.status!=200 or len(raw)>1024*1024:raise ValueError('bounded selected native page unavailable')
            return local('capture_intake').local('contract').decode(raw,max_bytes=1024*1024)
        finally:connection.close()
    return query


def configuration(path):
    protected=local('protected_config');value=protected.decode(path,maximum=1024*1024)
    if (type(value) is not dict or set(value)!={'contract','spool','reader_url','reader_token_file','service_socket','service_uid','selected'} or
            value['contract']!='hermes-runtime-history-job.v1'):raise ValueError('exact protected native history job required')
    source=local('hermes_history');selected=source.configuration(value['selected']);transport=local('codex_runtime').history_unix()
    transport.uid(value['service_uid']);transport.endpoint(value['service_socket'])
    local('capture_intake').private(value['spool'],True)
    token=protected.read(value['reader_token_file'],maximum=257).strip();reader(value['reader_url'],token)
    project=next(iter(selected['contexts'].values()))[0]['context']['project_id']
    if urlsplit(value['reader_url']).path!='/webhook/rras-hermes-engineering-history-'+project:raise ValueError('exact selected project route required')
    return value,token


def run_once(value,token,*,query=None,send=None):
    intake=local('capture_intake');source=local('hermes_history');selected=source.configuration(value['selected']);spool=intake.Spool(value['spool'])
    lock=spool.root/'hermes-history.lock';fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        intake.private(lock);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if query is None:query=reader(value['reader_url'],token)
        if send is None:send=lambda message:intake.local('unix').call(value['service_socket'],value['service_uid'],message)
        issue=next(iter(selected['policy']['issues']));pin=selected['policy']['issues'][issue]
        ctx=dict(next(entry['context'] for entry in selected['contexts'][issue] if entry['binding']==pin),work=None)
        session=dict(namespace='n8n_hermes_runtime',id=source.prefix(selected))
        try:
            result=source.poll(spool,selected,query)
            spool.source_status(scope=selected['scope'],context=ctx,session=session,status='current',
                detail='Selected retained Jarvis bridge evidence collected; this does not independently establish native-service liveness or model usage.')
        except (ValueError,OSError,KeyError,TypeError,http.client.HTTPException):
            try:spool.source_status(scope=selected['scope'],context=ctx,session=session,status='gap',
                detail='Native Jarvis history collection unconfirmed; retain transport evidence, native sources and pending queue. No work was rerun.')
            except (ValueError,OSError):pass
            result=dict(gap=True,models_started=0)
        return dict(collection=result,delivery=spool.flush(send),models_started=0)
    finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True);args=parser.parse_args()
    try:
        value,token=configuration(args.config);print(json.dumps(run_once(value,token),allow_nan=False))
    except Exception:parser.exit(1,'Native Jarvis history pass refused; retain transport records and pending queue.\n')


if __name__=='__main__':main()
