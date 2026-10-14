"""Acceptance payload for an explicitly provisioned low-privilege UID; no credentials."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat


def check_identity(expected_uid, expected_gid):
    if expected_uid in (0, 1000, 997, 65534) or os.getuid() != expected_uid or os.geteuid() != expected_uid:
        raise ValueError('dedicated worker identity required; operator/supervisor/nobody forbidden')
    if os.getgid() != expected_gid or set(os.getgroups()) - {expected_gid}:
        raise ValueError('unexpected worker group authority')


def run(args):
    check_identity(args.uid,args.gid)
    work=Path.cwd()
    info=work.stat()
    if info.st_uid!=args.uid or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('worker-owned private acceptance directory required')
    protected=args.protected_fixture
    # The operator creates a harmless root-owned sentinel; never target real secret contents.
    info=protected.stat()
    if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or os.access(protected,os.R_OK):
        raise ValueError('protected root fixture must be unreadable')
    if os.access('/var/run/docker.sock',os.R_OK|os.W_OK):
        raise ValueError('worker must not have Docker socket access')
    spec=importlib.util.spec_from_file_location('probe_codex',Path(__file__).with_name('probe_codex.py'))
    probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    result=probe.probe(args.binary,args.evidence,args.config_template)
    receipt={'schema_version':1,'scope':'dedicated-uid-native-sandbox','uid':os.getuid(),'gid':os.getgid(),
       'api_calls':0,'identity_checks_passed':True,'private_fixture_unreadable':True,
       'docker_socket_access_denied':True,'probe_evidence':str(args.evidence),'success':result['success'],
       'native_dispatcher_cgroup_tested':False,'real_session_callbacks_tested':False}
    with (work/'identity-evidence.json').open('x') as stream:
        json.dump(receipt,stream,indent=2);stream.write('\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uid',type=int,required=True);p.add_argument('--gid',type=int,required=True)
    p.add_argument('--protected-fixture',type=Path,required=True);p.add_argument('--binary',required=True)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--config-template')
    a=p.parse_args()
    try:e=run(a)
    except Exception as exc:
        e={'schema_version':1,'scope':'dedicated-uid-native-sandbox','success':False,
           'api_calls':0,'error_type':type(exc).__name__,'error':str(exc)}
    print(json.dumps(e));raise SystemExit(0 if e['success'] else 1)
