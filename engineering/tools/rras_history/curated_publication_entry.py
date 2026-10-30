"""Bounded stdin publication entry for a separately sandboxed catalog owner.

No listener, private history reads, elevation, catalog creation or path selection.
"""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))
LIMIT=2*1024*1024
CATALOG='/var/lib/rras-curated-history/catalog'


def local(name):
    spec=importlib.util.spec_from_file_location('curated_writer_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def apply(root,raw,reviewed_request_sha256):
    c=local('contract')
    if type(raw) is not bytes or len(raw)>LIMIT:raise ValueError('bounded request bytes required')
    # Bind the entire exact packet, including approval, operation and expected head.
    if c.digest(raw)!=reviewed_request_sha256:raise ValueError('reviewed request bytes differ')
    packet=c.decode(raw,max_bytes=LIMIT)
    common={'contract','operation','client_key','expected_head','approved'}
    if type(packet) is not dict or packet.get('contract')!='engineering-curated-publication-request.v1' or packet.get('approved') is not True:
        raise ValueError('explicit publication request required')
    pub=local('curated_publication')
    if packet.get('operation')=='publish' and set(packet)==common|{'preview','reviewed_preview_sha256'}:
        return pub.publish(root,packet['preview'],packet['reviewed_preview_sha256'],packet['expected_head'],packet['client_key'],approve_publication=True)
    if packet.get('operation')=='withdraw' and set(packet)==common|{'entry_ids'}:
        return pub.withdraw(root,packet['entry_ids'],packet['expected_head'],packet['client_key'],approve_withdrawal=True)
    raise ValueError('exact supported publication request required')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviewed-request-sha256',required=True)
    args=parser.parse_args(argv)
    try:
        prod=local('production_entry');prod.service_environment();prod.require_account('995')
        result=apply(CATALOG,sys.stdin.buffer.read(LIMIT+1),args.reviewed_request_sha256)
        sys.stdout.buffer.write(local('contract').encoded(result)+b'\n')
    except (ValueError,KeyError,TypeError,OSError):
        parser.exit(1,'Curated publication refused; preserve request and catalog evidence. No automatic retry.\n')


if __name__=='__main__':main()
