"""Explicit selected-session collector jobs and replay, suitable for a timer.

No discovery, credentials, models, hook edits or production activation. Hermes
invokes its selected-reader adapter inside its existing trust boundary instead.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
from jsonschema import ValidationError

sys.path.insert(0,str(Path(__file__).parent))
import capture_collectors as collectors
import capture_intake as intake


def configuration(path):
    path=intake.private(path)
    if path.stat().st_size>1024*1024:raise ValueError('bounded private configuration required')
    return validate_configuration(intake.local('contract').decode(path.read_bytes()))


def validate_configuration(value):
    if (type(value) is not dict or set(value)!={'contract','spool','service_socket','service_uid','jobs'} or
            value['contract'] not in ('engineering-capture-jobs.v1','engineering-capture-jobs.v2') or type(value['service_uid']) is not int or
            value['service_uid']<0 or type(value['jobs']) is not list or not 1<=len(value['jobs'])<=32):
        raise ValueError('explicit bounded capture jobs required')
    ids=set();sources=set();identities=set()
    required={'id','source','session','binary','scope','context','authorization_reference'}
    if value['contract']=='engineering-capture-jobs.v2':required=required|{'source_segment'}
    for job in value['jobs']:
        if (type(job) is not dict or set(job)!=required or
                type(job['id']) is not str or not collectors.re.fullmatch('[A-Za-z0-9_.-]{1,96}',job['id']) or job['id'] in ids):
            raise ValueError('unique exact selected job required')
        ids.add(job['id']);collectors.authorization(job['authorization_reference'])
        if 'source_segment' in job and (type(job['source_segment']) is not str or not collectors.re.fullmatch('[A-Za-z0-9_.-]{1,64}',job['source_segment'])):
            raise ValueError('bounded explicit source segment required')
        if (type(job['session']) is not str or not collectors.re.fullmatch('[0-9a-f-]{36}',job['session']) or
                job['source'] in sources):raise ValueError('one explicit source per selected session required')
        sources.add(job['source'])
        identity=(job['session'],job.get('source_segment'))
        if identity in identities:raise ValueError('duplicate session segment identity')
        identities.add(identity)
        for name in ('source','binary'):
            p=Path(job[name])
            if not p.is_absolute() or p.resolve()!=p:raise ValueError('canonical exact source paths required')
        # Validate scope/context without reading a native source or starting work.
        intake.local('reporting_contract').validate(dict(contract='engineering-reporting.v1',operation='source.observe',
            client_event_key='configuration-validation',expected_head=None,scope=job['scope'],context=job['context'],
            source=dict(kind='imported',namespace='capture_intake',id=job['session']),occurred_at=None,
            body=dict(source=dict(namespace='codex',id=job['session']),source_observed_at=None,cursor=None,
                status='unknown',gaps=[],detail='Selected job configuration validation only.')))
    for name in ('spool','service_socket'):
        p=Path(value[name])
        if not p.is_absolute() or p.resolve()!=p:raise ValueError('canonical private transport paths required')
    return value


def run_once(value,*,send=None,collect=None):
    spool=intake.Spool(value['spool']);lock=spool.root/'collector.lock'
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        intake.private(lock);fcntl.flock(fd,fcntl.LOCK_EX)
        if send is None:
            unix=intake.local('unix')
            send=lambda message:unix.call(value['service_socket'],value['service_uid'],message)
        results=[]
        if collect is None:collect=collectors.collect_codex
        for job in value['jobs']:
            status_id=job['session']+('#'+job['source_segment'] if job.get('source_segment') else '')
            try:
                result=collect(spool,**{k:v for k,v in job.items() if k!='id'})
                with spool.connection() as db:
                    latest=db.execute("SELECT request,receipt FROM items WHERE kind='artifact' AND artifact=? ORDER BY sequence DESC LIMIT 1",(result.get('artifact_id',result.get('staged',{}).get('artifact_id')),)).fetchone()
                if latest:
                    request=spool.c.decode(latest['request']);known=job['context'] is not None
                    spool.source_status(scope=job['scope'],context=job['context'],session=dict(namespace='codex',id=status_id),
                        status=('current' if latest['receipt'] else 'pending') if known else 'unmapped',
                        detail='Selected source available; delivery state reflects its retained artifact receipt.',
                        cursor=request['body']['source_range']['end'],source_observed_at=request['body'].get('captured_at'))
                results.append(dict(id=job['id'],collection='changed' if result['changed'] else 'unchanged'))
            except (ValueError,OSError,TypeError,KeyError,collectors.subprocess.SubprocessError):
                # Never persist raw exception strings or credential-bearing stdout.
                detail='Selected source collection unconfirmed; retain native source and prior exports.'
                try:spool.source_status(scope=job['scope'],context=job['context'],session=dict(namespace='codex',id=status_id),
                    status='gap',detail=detail)
                except (ValueError,OSError):pass  # Capacity stop retains earlier queue/source.
                results.append(dict(id=job['id'],collection='gap'))
        return dict(contract='engineering-capture-pass.v1',jobs=results,delivery=spool.flush(send),models_started=0)
    finally:os.close(fd)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=('init','run-once','status'))
    parser.add_argument('--config',required=True);args=parser.parse_args(argv)
    try:
        value=configuration(args.config)
        if args.operation=='init':
            spool=intake.Spool(value['spool'],create=True);result=dict(initialized=True,collection_started=False)
        elif args.operation=='run-once':result=run_once(value)
        else:
            spool=intake.Spool(value['spool'])
            with spool.connection() as db:
                result=dict(items=db.execute('SELECT count(*) FROM items').fetchone()[0],
                    pending=db.execute('SELECT count(*) FROM items WHERE receipt IS NULL').fetchone()[0])
        print(json.dumps(result,allow_nan=False))
    except (ValueError,OSError,TypeError,KeyError,ValidationError):
        parser.exit(1,'Capture pass refused; retain native source, private queue and receipts.\n')


if __name__=='__main__':main()
