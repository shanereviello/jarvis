"""Supported model-free checks. Run host modes only in a reviewed disposable unit."""
import argparse
import importlib.util
import json
from pathlib import Path


def module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True,choices=('manual','session-policy','live-session','git-boundary','credentials','waiter'))
    p.add_argument('--source',required=True)
    p.add_argument('--python',required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--profile')
    p.add_argument('--codex-config')
    p.add_argument('--binary')
    p.add_argument('--fixture-credential')
    p.add_argument('--protected-fixture-source')
    p.add_argument('--uid',type=int,default=996)
    p.add_argument('--dedicated-cgroup',action='store_true')
    return p


def run(args):
    # Acceptance is explicitly credential-free. Fixture delivery uses only the fixed sentinel.
    import os
    if any(k in os.environ for k in ('OPENAI_API_KEY','RRAS_OPENAI_API_KEY','ANTHROPIC_API_KEY')):
        raise ValueError('provider credential environment forbidden')
    if not args.work.is_dir() or args.work.is_symlink():raise ValueError('existing fixture root required')
    if args.case=='manual':
        if not args.profile or not args.codex_config:raise ValueError('reviewed profile/config required')
        return module('probe_manual_runner').run(args.source,args.python,args.profile,args.codex_config,args.work,args.dedicated_cgroup)
    if args.case=='session-policy':return module('probe_session_policy').probe(args.source,args.work/'session-policy.json')
    if args.case=='live-session':
        if not args.binary or not args.codex_config:raise ValueError('reviewed binary/config required')
        return module('probe_live_session').probe(args.source,args.binary,args.codex_config,args.work,args.uid)
    if args.case=='git-boundary':return module('probe_git_metadata').run(args.source,args.python,args.work)
    if args.case=='credentials':
        if not args.profile or not args.fixture_credential:raise ValueError('profile and harmless fixture required')
        return module('probe_cli_credentials').probe(args.source,args.profile,args.work,args.fixture_credential,args.uid,args.protected_fixture_source,args.codex_config)
    return module('probe_wait_worker').run(args.work,args.dedicated_cgroup)


if __name__=='__main__':
    result=run(parser().parse_args())
    print(json.dumps(result))
    raise SystemExit(0 if result.get('success') else 1)
