"""Deliver frozen Codex handoff admissions; never starts or retries coding."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path


def local():
    spec=importlib.util.spec_from_file_location('passive_runtime_handoff',Path(__file__).with_name('runtime_handoff.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def run(path):
    m=local();intake=m.local('capture_intake');path=intake.private(path)
    if path.stat().st_size>8192:raise ValueError('bounded installed handoff delivery job required')
    configuration=intake.local('contract').decode(path.read_bytes())
    if (type(configuration) is not dict or set(configuration)!={'contract','queue','url','token_file'} or
            configuration['contract']!='native-handoff-delivery.v1'):raise ValueError('exact installed delivery job required')
    token_file=intake.private(configuration['token_file'])
    if token_file.stat().st_size>257:raise ValueError('bounded private admission credential required')
    send=m.sender(configuration['url'],token_file.read_bytes().strip());queue=m.Queue(configuration['queue'])
    fd=os.open(queue.path/'delivery.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        intake.private(queue.path/'delivery.lock');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return queue.flush(send)
    finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True);args=parser.parse_args()
    try:print(json.dumps(run(args.config)))
    except (ValueError,OSError,KeyError,TypeError):parser.exit(1,'Handoff delivery unconfirmed; retain immutable queue and source context.\n')


if __name__=='__main__':main()
