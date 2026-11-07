"""Explicit private scope authoring and fingerprint-bound owner-only migration."""
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
from jsonschema import ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('scope_cli_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('migration-plan','migrate','submit','read'))
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--store');target.add_argument('--service-socket')
    parser.add_argument('--service-uid',type=int);parser.add_argument('--request');parser.add_argument('--expected-sha256')
    args=parser.parse_args(argv)
    try:
        if args.store:
            if args.service_uid is not None:raise ValueError('select one transport')
            store=local('store').Store(args.store);scopes=local('scopes').Scopes(store)
            if args.operation=='migration-plan':result=scopes.migration_plan()
            elif args.operation=='migrate':result=scopes.migrate(args.expected_sha256)
            elif args.operation=='submit':result=scopes.submit(local('project_cli').read_file(args.request))
            else:
                query=local('project_cli').read_file(args.request)
                if set(query)!={'scope','query'} or query['query'].get('view')!='scope':raise ValueError('exact scope query required')
                result=local('projects').Projects(store).read(query['scope'],query['query'])
        else:
            if args.operation not in ('submit','read') or args.service_uid is None:raise ValueError('migration is owner-only')
            value=local('project_cli').read_file(args.request)
            message={'method':'scope_submit','request':value} if args.operation=='submit' else {'method':'project_read',**value}
            if args.operation=='read' and (set(value)!={'scope','query'} or value['query'].get('view')!='scope'):
                raise ValueError('exact scope query required')
            result=local('unix').call(args.service_socket,args.service_uid,message)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):
        parser.exit(1,'Scope operation refused; preserve requests, receipts and database.\n')


if __name__=='__main__':main()
