"""Explicit private managed-link preparation/delivery; never coding execution."""
import argparse
import importlib.util
from pathlib import Path
import sqlite3
from jsonschema import ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('managed_link_cli_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    prepare=sub.add_parser('prepare');prepare.add_argument('--state',required=True)
    prepare.add_argument('--work-request',required=True);prepare.add_argument('--packet',required=True);prepare.add_argument('--previous-state')
    deliver=sub.add_parser('deliver');deliver.add_argument('--state',required=True)
    deliver.add_argument('--socket',required=True);deliver.add_argument('--service-uid',required=True,type=int)
    args=parser.parse_args(argv)
    try:
        d=local('link_delivery')
        if args.operation=='prepare':
            result=d.prepare(Path(args.state),d.read(Path(args.work_request)),d.read(Path(args.packet)),previous=args.previous_state)
        else:
            import os
            transport=local('unix');transport.uid(args.service_uid);transport.endpoint(args.socket)
            result=d.deliver(Path(args.state),lambda request:transport.call(args.socket,args.service_uid,{'method':'submit','request':request}),
                             writer_uid=args.service_uid,peer_uid=os.getuid())
        print(local('contract').encoded(result).decode(),end='')
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):
        parser.exit(1,'Managed history link refused or pending. Preserve plan/receipts; no coding action was invoked.\n')


if __name__=='__main__':main()
