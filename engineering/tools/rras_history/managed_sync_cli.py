"""Explicit inspect/apply/resume for passive managed-history handoffs."""
import argparse
import importlib.util
import sqlite3
from pathlib import Path
from jsonschema import ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('sync_cli_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    for name in ('init','inspect','apply','resume','status'):
        p=sub.add_parser(name);p.add_argument('--state',required=True)
        if name=='init':
            p.add_argument('--work-request',required=True);p.add_argument('--packet',required=True)
            p.add_argument('--socket',required=True);p.add_argument('--service-uid',type=int,required=True)
        if name in ('inspect','apply'):p.add_argument('--handoff',required=True)
        if name in ('apply','resume'):p.add_argument('--capture-sha256',required=True)
    args=parser.parse_args(argv)
    try:
        sync=local('managed_sync');d=local('link_delivery');transport=local('unix')
        if args.operation=='init':
            call=lambda message:transport.call(args.socket,args.service_uid,message)
            result=sync.initialize(Path(args.state),d.read(Path(args.work_request)),d.read(Path(args.packet)),args.socket,args.service_uid,call)
        elif args.operation=='inspect':result=sync.inspect(Path(args.state),Path(args.handoff))
        elif args.operation=='status':result=sync.status(Path(args.state))
        else:
            config=sync.configuration(Path(args.state))
            call=lambda message:transport.call(config['service_socket'],config['service_uid'],message)
            if args.operation=='apply':result=sync.apply(Path(args.state),Path(args.handoff),args.capture_sha256,call)
            else:result=sync.resume(Path(args.state),args.capture_sha256,call)
        print(local('contract').encoded(result).decode(),end='')
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):
        parser.exit(1,'Managed sync refused or pending. Preserve private state/receipts; no coding action invoked.\n')


if __name__=='__main__':main()
