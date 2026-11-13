"""Produce one protected sandbox proof from current units and a real probe.

This source entry is inactive until separately installed and configured. It
does not authorize coding, start a model, or alter existing service units.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location('sandbox_producer_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def produce(config):
    fields = {'unit_directory','native_release','proof_directory','proof_name','request'}
    if (os.getuid() != 0 or os.geteuid() != 0 or type(config) is not dict or set(config) != fields or
            type(config['request']) is not dict or set(config['request']) != {'issue_id','workspace','native_socket'}):
        raise ValueError('root and exact protected sandbox configuration required')
    request = config['request'];seen = []
    # This effective-unit check is only a structural precondition for the
    # actual probe below. It is never exposed as a standalone isolation proof.
    effective = local('onboarding_workspace_effective_units').Verifier(config['unit_directory'],lambda _:True)
    def capture(expected):
        if effective(expected) is not True:raise ValueError('effective units refused')
        seen.append(expected)
        return True
    units = local('onboarding_workspace_unit_evidence').Verifier(config['unit_directory'],config['native_release'],capture)
    units(request)
    if len(seen) != 1:raise ValueError('one exact issue configuration required')
    expected = seen[0]
    def recheck(candidate):
        seen.clear();units(request)
        return len(seen) == 1 and seen[0] == candidate
    return local('onboarding_sandbox_proof_writer').create(config['proof_directory'],config['proof_name'],expected,
        recheck,local('onboarding_native_sandbox_probe').probe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    args = parser.parse_args()
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME='/nonexistent',LANG='C.UTF-8');os.umask(0o077)
    try:
        config = local('protected_config').decode(args.config,require_root=True,maximum=65536)
        print(json.dumps(produce(config),sort_keys=True))
    except Exception:
        parser.exit(1,'Native sandbox proof refused; retain existing state for inspection.\n')


if __name__ == '__main__':main()
