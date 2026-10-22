"""Explicit local start/attach/checkpoint/handoff/finish with durable pending state."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
from jsonschema import ValidationError


def local(name):
    s=importlib.util.spec_from_file_location('interactive_cli_'+name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def read_json(path):
    c=local('contract')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>c.MAX_REQUEST:
            raise ValueError('bounded regular input required')
        return c.decode(stream.read(c.MAX_REQUEST+1))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('init','start','attach','checkpoint','pause','handoff','finish','status','flush','abandon'):
        p=sub.add_parser(command);p.add_argument('--state',required=True)
        if command=='init':
            choice=p.add_mutually_exclusive_group(required=True)
            choice.add_argument('--history-store');choice.add_argument('--service-socket')
            p.add_argument('--service-uid',type=int)
        if command in ('start','attach','checkpoint','pause','handoff','finish'):
            p.add_argument('--key',required=True);p.add_argument('--queue-only',action='store_true');p.add_argument('--occurred-at')
        if command=='start':p.add_argument('--request',required=True)
        if command in ('start','attach'):p.add_argument('--session-id')
        if command=='attach':
            p.add_argument('--work-id',required=True);p.add_argument('--revision-sha256',required=True)
        if command in ('checkpoint','pause','handoff','finish'):p.add_argument('--note',required=True)
        if command=='abandon':p.add_argument('--key',required=True);p.add_argument('--reason',required=True)
    args=parser.parse_args(argv)
    try:
        cls=local('interactive').Client
        if args.command=='init':
            client=cls(args.state,store=args.history_store,service_socket=args.service_socket,service_uid=args.service_uid,create=True);result=client.status()
        else:
            client=cls(args.state)
            if args.command=='status':result=client.status()
            elif args.command=='flush':result=client.flush()
            elif args.command=='abandon':
                reason=read_json(args.reason)
                if not isinstance(reason,dict) or set(reason)!={'reason'}:raise ValueError('explicit reason object required')
                result=client.abandon(args.key,reason['reason'])
            else:
                if args.command=='start':payload=read_json(args.request)
                elif args.command=='attach':payload={'work_item_id':args.work_id,'work_revision_sha256':args.revision_sha256}
                else:payload=read_json(args.note)
                queued=client.enqueue(args.command,args.key,payload,session_id=getattr(args,'session_id',None),occurred_at=args.occurred_at)
                result={'queue':queued,'status':client.status()} if args.queue_only else {'queue':queued,**client.flush()}
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):
        parser.exit(1,'Interactive history operation refused; preserve local queue and receipts.\n')


if __name__=='__main__':main()
