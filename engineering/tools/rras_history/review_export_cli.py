"""Root-only explicit historical review document inspection and private export."""
import argparse
import importlib.util
from pathlib import Path
from jsonschema import ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('review_export_cli_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(command,state,review_id,source_release,source_manifest_sha256,*,approve_private_read=False,
        packet_sha256=None,export_id=None,approve_private_export=False):
    if command not in ('inspect','export'):raise ValueError('known export operation required')
    if command=='inspect' and approve_private_read is not True:raise ValueError('explicit private read required')
    if command=='export':
        import re
        if (approve_private_export is not True or type(packet_sha256) is not str or
                not re.fullmatch('[0-9a-f]{64}',packet_sha256) or type(export_id) is not str or
                not re.fullmatch('[0-9a-f]{32}',export_id)):
            raise ValueError('explicit exact private export required')
    producer=local('review_document_export')
    packet=producer.snapshot(Path(state),review_id,Path(source_release),source_manifest_sha256,approve_private_export=True)
    review=local('review_document_link').inspect(packet)
    if command=='inspect':return dict(review,phase='protected_review_document_inspected',mutations=False)
    if packet_sha256!=review['packet_sha256']:raise ValueError('reviewed packet changed before handoff')
    return producer.handoff(export_id,packet,approve_private_export=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    for name in ('inspect','export'):
        command=sub.add_parser(name)
        for field in ('state','review-id','source-release','source-manifest-sha256'):command.add_argument('--'+field,required=True)
        if name=='inspect':command.add_argument('--approve-private-read',action='store_true')
        else:
            command.add_argument('--packet-sha256',required=True);command.add_argument('--export-id',required=True)
            command.add_argument('--approve-private-export',action='store_true')
    args=parser.parse_args(argv)
    try:
        result=run(**vars(args));print(local('contract').encoded(result).decode(),end='')
    except (ValueError,KeyError,TypeError,OSError,ValidationError):
        parser.exit(1,'Private review export refused or stopped. Preserve protected evidence; no automatic retry or history intake.\n')


if __name__=='__main__':main()
