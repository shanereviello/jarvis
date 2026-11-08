"""Bounded fair passes over runtime-registered exact native files; no discovery.

The installed reporting policy supplies all permitted work and transport context.
Registry entries cannot add a repository, source root, exporter or authorization.
An independent timer can run this while coding is active or the runtime is down.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).parent))
import runtime_reporting as reporting
import capture_jobs


def selected(reporter,limit=32):
    if type(limit) is not int or not 1<=limit<=32:raise ValueError('bounded registry pass required')
    config=reporter.configuration['capture']
    if config is None:raise ValueError('selected capture installation required')
    intake=reporter.intake;root=intake.private(config['jobs'],True);lock=root/'.registry.lock'
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        intake.private(lock);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        names=[]
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.name in ('.registry.lock','.cursor.json'):continue
                if not re.fullmatch('[0-9a-f]{64}\\.json',entry.name):raise ValueError('unexpected capture registry member')
                names.append(entry.name)
                if len(names)>4096:raise ValueError('capture registry capacity reached')
        names.sort();cursor=root/'.cursor.json';after=None
        if cursor.exists() or cursor.is_symlink():
            intake.private(cursor)
            if cursor.stat().st_size>256:raise ValueError('bounded registry cursor required')
            position=reporter.c.decode(cursor.read_bytes())
            if (type(position) is not dict or set(position)!={'after'} or
                    not re.fullmatch('[0-9a-f]{64}\\.json',position['after'])):raise ValueError('exact registry cursor required')
            after=position['after']
        ordered=[n for n in names if after is None or n>after]+[n for n in names if after is not None and n<=after]
        jobs=[]
        for name in ordered[:limit]:
            value=capture_jobs.configuration(root/name)
            if len(value['jobs'])!=1:raise ValueError('one registered source required')
            job=value['jobs'][0]
            if not job['id'].startswith('runtime-'):raise ValueError('actual runtime registration required')
            matches=[issue for issue,ctx in reporter.configuration['contexts'].items() if ctx==job['context']]
            if len(matches)!=1:raise ValueError('unique installed issue context required')
            expected,digest=reporter.capture_job(dict(session=job['id'][len('runtime-'):],thread=job['session'],issue=matches[0]),job['source'])
            if value!=expected or name!=digest+'.json':raise ValueError('registered source or installed policy changed')
            jobs.append(value)
        if jobs:
            # Advance before collection. A crash cannot starve later registered
            # sources; this source is retried on a later bounded rotation.
            temporary=root/'.cursor.next'
            out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                with os.fdopen(out,'wb') as f:f.write(reporter.c.encoded(dict(after=ordered[min(limit,len(ordered))-1])));f.flush();os.fsync(f.fileno())
                os.replace(temporary,cursor);intake.sync(root)
            finally:
                if temporary.exists():temporary.unlink()
        return jobs
    finally:os.close(fd)


def run_once(reporter,*,limit=32,send=None):
    jobs=selected(reporter,limit);results=[]
    for job in jobs:results.append(capture_jobs.run_once(job,send=send))
    # Lifecycle and agent checkpoints still flush when no native file exists yet.
    if send is None:
        selected_config=reporter.configuration['capture'];unix=reporter.intake.local('unix')
        send=lambda message:unix.call(selected_config['service_socket'],selected_config['service_uid'],message)
    return dict(contract='runtime-capture-pass.v1',sources=len(jobs),passes=results,
        delivery=reporter.spool.flush(send),models_started=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--policy',required=True)
    parser.add_argument('--reporting-policy',required=True);args=parser.parse_args();runtime=reporting.local('codex_runtime')
    try:
        policy=runtime.policy(json.loads(runtime.private(args.policy).read_bytes()))
        reporter=reporting.Reporter(json.loads(runtime.private(args.reporting_policy).read_bytes()),policy)
        print(json.dumps(run_once(reporter),allow_nan=False))
    except (ValueError,OSError,TypeError,KeyError):parser.exit(1,'Registered capture pass refused; retain native sources, registry and pending spool.\n')


if __name__=='__main__':main()
