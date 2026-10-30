"""Prepare a bounded passive root-export proposal; never read root or submit history."""
import argparse
import importlib.util
import os
from pathlib import Path
from jsonschema import ValidationError


def local(name,native=False):
    path=Path(__file__).parents[1]/('rras_native' if native else 'rras_history')/(name+'.py')
    spec=importlib.util.spec_from_file_location('export_plan_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def build(operational,engineering,journal_id,capture_id):
    records=local('workflow_records',True);records.validate_record(operational)
    c=local('contract');engineering=c.validate(engineering)
    if operational['kind']!='work_item' or engineering['operation'] not in ('work.create','work.revise'):
        raise ValueError('explicit operational and engineering work required')
    body=engineering['body']
    if (operational['work_item_id']!=body['work_item_id'] or operational['repository_id']!=body['repository_id'] or
            operational['baseline']!=body['baseline'] or operational['requested_paths']!=body['allowed_paths']):
        raise ValueError('exact work repository baseline and ordered scope required')
    package=local('managed_export_package')
    return package.validate_plan({'contract':'engineering-production-export.v1',
        'scope':'one-work-revision-allowlisted-export-only','capture_id':capture_id,'journal_id':journal_id,
        'work_item_id':operational['work_item_id'],'repository_id':operational['repository_id'],
        'source_work_sha256':records.record_digest(operational),'baseline':operational['baseline'],
        'allowed_paths':operational['requested_paths'],'reader_uid':1000})


def inspect(plan):
    p=local('managed_export_package');plan=p.validate_plan(plan)
    import hashlib
    return {'plan_sha256':hashlib.sha256(p.encoded(plan)).hexdigest(),
        'capture_id':plan['capture_id'],'journal_id':plan['journal_id'],'repository_id':plan['repository_id'],
        'work_item_id':plan['work_item_id'],'source_work_sha256':plan['source_work_sha256'],
        'baseline':plan['baseline'],'allowed_paths':plan['allowed_paths'],'reader_uid':1000,
        'source_authenticated':False,'root_source_opened':False,'export_authorized':False,
        'history_records_written':False,'api_calls':0}


def prepare(destination,operational_path,engineering_path,journal_id,capture_id):
    d=local('link_delivery');destination=Path(destination)
    if os.getuid()==0 or os.geteuid()!=os.getuid():raise ValueError('unprivileged proposal preparation required')
    if not destination.is_absolute():raise ValueError('absolute private proposal directory required')
    d.guard(destination.parent)
    plan=build(d.read(Path(operational_path)),d.read(Path(engineering_path)),journal_id,capture_id)
    review=inspect(plan);destination.mkdir(mode=0o700);d.guard(destination)
    # Use the root exporter's canonical encoding, including for non-ASCII paths.
    raw=local('managed_export_package').encoded(plan)
    fd=os.open(destination/'plan.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        os.fchmod(stream.fileno(),0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())
    d.write(destination/'review.json',review)
    fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return dict(review,prepared=True,plan=str(destination/'plan.json'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare')
    for name in ('destination','operational-work','engineering-work','journal-id','capture-id'):prep.add_argument('--'+name,required=True)
    show=sub.add_parser('inspect');show.add_argument('--plan',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='prepare':result=prepare(args.destination,args.operational_work,args.engineering_work,args.journal_id,args.capture_id)
        else:result=inspect(local('link_delivery').read(Path(args.plan)))
        print(local('contract').encoded(result).decode(),end='')
    except (ValueError,KeyError,TypeError,OSError,ValidationError):
        parser.exit(1,'Export proposal refused. Preserve private inputs; no root export or history intake invoked.\n')


if __name__=='__main__':main()
