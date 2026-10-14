"""Sentinel-only native spawn; never accepts a production credential."""
import argparse
import importlib.util
from pathlib import Path
import json
import os
import sys


def module(name):
    s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','python','profile','codex-config','work','credential'):p.add_argument('--'+n,required=True)
    p.add_argument('--dedicated-cgroup',action='store_true')
    return p


if __name__=='__main__':
    x=parser().parse_args()
    # Check delivery before clearing only the credential-directory metadata.
    directory=os.environ.get('CREDENTIALS_DIRECTORY')
    if directory and Path(x.credential).resolve().parent!=Path(directory).resolve():
        raise ValueError('credential is outside systemd delivery directory')
    token=module('probe_cli_credentials').read_fixture(x.credential)
    if directory:
        token=module('manual_paid_canary').delivered_key(x.credential)
    os.environ.pop('CREDENTIALS_DIRECTORY',None)
    r=module('probe_integrated_runner').run(x.source,x.python,x.profile,x.work,'success',x.dedicated_cgroup,token,x.codex_config)
    with (Path(x.work)/'delivery.json').open('x') as f:
        json.dump({'systemd_delivery':bool(directory),'production_loader_validated':bool(directory)},f)
    print(json.dumps(r));sys.exit(0 if r['success'] else 1)
