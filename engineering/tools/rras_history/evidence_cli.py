"""Explicit bounded chunk custody and signed reads; migrations are store-owner only."""
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
from jsonschema import ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('evidence_cli_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('migration-plan','migrate','upload','read'))
    target=p.add_mutually_exclusive_group(required=True);target.add_argument('--store');target.add_argument('--service-socket')
    p.add_argument('--service-uid',type=int);p.add_argument('--request');p.add_argument('--expected-sha256');a=p.parse_args(argv)
    try:
        value=None
        if a.operation in ('upload','read'):
            value=local('project_cli').read_file(a.request)
            if a.operation=='upload':local('evidence').validate(value)
            elif type(value) is not dict or set(value)!={'scope','query'}:raise ValueError('scoped read required')
        if a.store:
            if a.service_uid is not None:raise ValueError('select one transport')
            custody=local('evidence').Evidence(local('store').Store(a.store))
            if a.operation=='migration-plan':result=custody.migration_plan()
            elif a.operation=='migrate':result=custody.migrate(a.expected_sha256)
            elif a.operation=='upload':result=custody.upload(value)
            else:result=custody.read(value['scope'],value['query'])
        else:
            if a.operation not in ('upload','read') or a.service_uid is None:raise ValueError('migration is local owner-only')
            message=dict(method='evidence_upload',request=value) if a.operation=='upload' else dict(method='evidence_read',**value)
            result=local('unix').call(a.service_socket,a.service_uid,message)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except (ValueError,KeyError,TypeError,AttributeError,OSError,sqlite3.Error,ValidationError):
        p.exit(1,'Evidence operation refused; retain exact private bytes, requests and receipts.\n')


if __name__=='__main__':main()
