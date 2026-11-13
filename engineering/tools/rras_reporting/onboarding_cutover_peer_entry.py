"""Journal-owner half of one root-coordinated issue cutover; never starts work."""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_peer_' + name,Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run(config):
    account = pwd.getpwnam('rras-codex-adapter')
    if (os.getuid() != account.pw_uid or os.geteuid() != account.pw_uid or os.getgid() != account.pw_gid or
            os.getegid() != account.pw_gid or set(os.getgroups()) - {account.pw_gid}):
        raise ValueError('dedicated journal owner required')
    fields = {'contract','request','transition','operator_socket','operator_uid','workspace_root','native_release',
              'sandbox_proof','execution_grants','audit_directory','broker_socket'}
    if type(config) is not dict or set(config) != fields or config['contract'] != 'codex-issue-cutover-host.v1':
        raise ValueError('exact protected cutover configuration required')
    c = config
    transition = c['transition']
    if type(transition) is not dict or set(transition) != {'plan','old','new'}:
        raise ValueError('exact protected transition required')
    runtime = local('codex_runtime')
    plan = transition['plan']
    digest = hashlib.sha256(runtime.encoded(c['request'])).hexdigest()
    if type(plan) is not dict or plan.get('evidence_sha256') != digest or type(plan.get('authority')) is not dict:
        raise ValueError('protected request and authority binding required')
    plan_sha = hashlib.sha256(runtime.encoded(plan)).hexdigest()
    files = local('codex_cutover_broker_client').Files(c['broker_socket'])
    def verify(request):
        if hashlib.sha256(runtime.encoded(request)).hexdigest() != digest:
            raise ValueError('request changed')
        return files.verify()
    def authority(request):
        if not verify(request):raise ValueError('protected execution authority unavailable')
        return plan['authority']
    @contextmanager
    def host_guard():
        # Root's broker holds the operator lock and restart exclusion for its
        # lifetime; verify it is present before acquiring the journal lock.
        files.verify()
        yield
    adapter = local('codex_cutover_journal_adapter').Adapter('/var/lib/rras-codex-adapter/runtime',
        c['request'],verify,authority,files,host_guard)
    return local('codex_issue_cutover').execute(adapter,expected_plan_sha256=plan_sha)


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    args = parser.parse_args()
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8');os.umask(0o077)
    try:
        value = local('protected_config').decode(args.config,require_root=True,maximum=8*1024*1024)
        print(json.dumps(run(value),sort_keys=True))
    except Exception:
        parser.exit(1,'Journal cutover refused or interrupted; retain state and inspect before retry.\n')


if __name__ == '__main__':main()
