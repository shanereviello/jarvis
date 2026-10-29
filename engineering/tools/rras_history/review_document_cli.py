"""Explicit private review-document intake into an existing engineering work item."""
import argparse
import importlib.util
import os
from pathlib import Path
import sqlite3
from jsonschema import ValidationError


def local(name):
    spec=importlib.util.spec_from_file_location('review_cli_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def prepare(state,packet_path,packet_sha256,socket,service_uid):
    """Freeze reviewed bytes and endpoint locally; make no service request."""
    d=local('link_delivery');link=local('review_document_link');transport=local('unix')
    transport.uid(service_uid)
    if service_uid in (0,996,997):raise ValueError('history service identity required')
    endpoint=transport.endpoint(socket);packet=d.read(Path(packet_path))
    review=link.inspect(packet)
    if review['packet_sha256']!=packet_sha256:raise ValueError('reviewed packet differs')
    state=Path(state)
    if not state.is_absolute() or state.parent.resolve(strict=True)!=state.parent or os.getuid()==0 or os.geteuid()!=os.getuid():
        raise ValueError('private unprivileged state required')
    state.mkdir(mode=0o700);d.guard(state)
    d.write(state/'configuration.json',{'contract':'engineering-review-document-client.v1',
        'caller_uid':os.getuid(),'service_uid':service_uid,'socket':str(endpoint),'packet_sha256':packet_sha256})
    link.prepare(state/'document',packet,packet_sha256)
    return dict(review,prepared=True,history_records_written=False)


def configuration(state):
    d=local('link_delivery');state=d.guard(Path(state));config=d.read(state/'configuration.json')
    if (type(config) is not dict or set(config)!={'contract','caller_uid','service_uid','socket','packet_sha256'} or
        config['contract']!='engineering-review-document-client.v1' or type(config['caller_uid']) is not int or
        config['caller_uid']!=os.getuid()):raise ValueError('fixed client configuration differs')
    local('unix').uid(config['service_uid']);local('unix').endpoint(config['socket'])
    if config['service_uid'] in (0,996,997):raise ValueError('history service identity required')
    d.guard(state/'document');saved=d.read(state/'document/packet.json')
    if type(saved) is not dict or set(saved)!={'packet','packet_sha256'}:raise ValueError('frozen packet differs')
    review=local('review_document_link').inspect(saved['packet'])
    if review['packet_sha256']!=saved['packet_sha256'] or review['packet_sha256']!=config['packet_sha256']:
        raise ValueError('frozen packet digest differs')
    return config,review


def status(state):
    config,review=configuration(state);root=Path(state)/'document'
    return dict(review,receipt_saved=(root/'receipt.json').exists(),completion_saved=(root/'complete.json').exists(),
                history_records_written=False,status_only=True)


def apply(state,packet_sha256,approve_document,call=None):
    config,review=configuration(state)
    if approve_document is not True or packet_sha256!=config['packet_sha256']:
        raise ValueError('explicit exact document approval required')
    if call is None:
        call=lambda message:local('unix').call(config['socket'],config['service_uid'],message)
    return local('review_document_link').deliver(Path(state)/'document',call,
        writer_uid=config['service_uid'],peer_uid=os.getuid())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    inspect=sub.add_parser('inspect');inspect.add_argument('--packet',required=True)
    prep=sub.add_parser('prepare')
    for name in ('state','packet','packet-sha256','socket'):prep.add_argument('--'+name,required=True)
    prep.add_argument('--service-uid',type=int,required=True)
    status_parser=sub.add_parser('status');status_parser.add_argument('--state',required=True)
    for name in ('apply','resume'):
        command=sub.add_parser(name)
        command.add_argument('--state',required=True);command.add_argument('--packet-sha256',required=True)
        command.add_argument('--approve-private-document',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.command=='inspect':result=local('review_document_link').inspect(local('link_delivery').read(Path(args.packet)))
        elif args.command=='prepare':result=prepare(args.state,args.packet,args.packet_sha256,args.socket,args.service_uid)
        elif args.command=='status':result=status(args.state)
        else:result=apply(args.state,args.packet_sha256,args.approve_private_document)
        print(local('contract').encoded(result).decode(),end='')
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):
        parser.exit(1,'Review document intake refused or pending. Preserve private state and receipts; no coding action invoked.\n')


if __name__=='__main__':main()
