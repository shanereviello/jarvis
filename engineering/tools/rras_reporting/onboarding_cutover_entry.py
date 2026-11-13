"""Protected root entry for a single exact issue-admission cutover.

This source is not installed or activated. Configuration must be created by
the operator and all backing reader services must already be independently
configured. It never starts the runtime or a model.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import pwd


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_entry_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def configuration(value, lookup=pwd.getpwnam):
    fields = {'contract','request','transition','operator_socket','operator_uid','workspace_root','native_release',
              'sandbox_proof','execution_grants','audit_directory','broker_socket'}
    if type(value) is not dict or set(value) != fields or value['contract'] != 'codex-issue-cutover-host.v1':
        raise ValueError('exact protected cutover configuration required')
    if type(value['operator_uid']) is not int or value['operator_uid'] <= 0:
        raise ValueError('dedicated operator identity required')
    adapter = lookup('rras-codex-adapter');native = lookup('rras-codex-native')
    if len({adapter.pw_uid,native.pw_uid,value['operator_uid'],0}) != 4:
        raise ValueError('distinct protected identities required')
    for key in ('operator_socket','workspace_root','native_release','sandbox_proof','execution_grants','audit_directory','broker_socket'):
        if type(value[key]) is not str:
            raise ValueError('canonical protected path required')
        path = Path(value[key])
        if not path.is_absolute() or path.resolve(strict=False) != path or path == Path('/'):
            raise ValueError('canonical protected path required')
    if type(value['request']) is not dict or type(value['transition']) is not dict:
        raise ValueError('exact protected transition required')
    return value,adapter,native


def run(config):
    if os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError('protected root cutover required')
    c,adapter,native = configuration(config)
    partial = local('onboarding_admission_service').Client(c['operator_socket'],c['operator_uid'],partial=True)
    proof = local('onboarding_sandbox_proof').Verifier(c['sandbox_proof'])
    effective = local('onboarding_workspace_effective_units').Verifier('/etc/systemd/system',proof)
    units = local('onboarding_workspace_unit_evidence').Verifier('/etc/systemd/system',c['native_release'],effective)
    def socket_for_issue(issue):
        return '/run/rras-codex-runtime/coding-' + issue + '.sock'
    workspace = local('onboarding_workspace_evidence').Verifier(c['workspace_root'],native.pw_uid,socket_for_issue,units)
    evidence = local('onboarding_admission_service').SplitVerifier(partial,workspace)
    # Reload root-owned grants on each check, including after the journal write.
    authority = lambda request:local('onboarding_execution_authority').protected(c['execution_grants'])(request)
    recheck = local('codex_cutover_evidence_recheck').Recheck(c['request'],evidence,authority)
    journal = local('codex_cutover_journal_reader').Reader('/var/lib/rras-codex-adapter/runtime',adapter.pw_uid)
    return local('codex_cutover_root_host').run(unit='rras-codex-runtime.service',socket_path=c['broker_socket'],
        peer_uid=adapter.pw_uid,peer_gid=adapter.pw_gid,policy_path='/etc/rras-engineering/codex-runtime/policy.json',
        audit_dir=c['audit_directory'],transition=c['transition'],verify_journal=journal,verify_evidence=recheck)


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    args = parser.parse_args()
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8');os.umask(0o077)
    try:
        value = local('protected_config').decode(args.config,require_root=True,maximum=8*1024*1024)
        print(json.dumps(run(value),sort_keys=True))
    except Exception:
        parser.exit(1,'Cutover refused or interrupted; retain state and inspect before restarting.\n')


if __name__ == '__main__':main()
