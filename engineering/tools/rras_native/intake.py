"""Prepare bounded tasks for review. No worker launch, provider auth or publication."""
import argparse
import importlib.util
import json
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(policy_path, proposal_path, state, *, authenticated_identity):
    """Identity must come from a trusted caller, never from the proposal body."""
    a = local('activity')
    policy, proposal = a.load(policy_path), a.load(proposal_path)
    if set(policy) != {'schema_version', 'identities', 'repositories'} or policy['schema_version'] != 1:
        raise ValueError('invalid policy')
    if set(proposal) != {'task_id', 'repository_id', 'objective', 'allowed_paths', 'validation_id'}:
        raise ValueError('invalid proposal; identity and execution authority are not caller fields')
    identity = a.identifier(authenticated_identity)
    if identity not in policy['identities']:
        raise ValueError('identity not admitted')
    repo_id = a.identifier(proposal['repository_id'])
    if repo_id not in policy['identities'][identity]:
        raise ValueError('repository not admitted for identity')
    row = policy['repositories'][repo_id]
    if set(row) != {'enabled', 'allowed_paths', 'validations', 'worker_timeout_seconds', 'validation_timeout_seconds'} or row['enabled'] is not True:
        raise ValueError('repository disabled or invalid policy')
    if not set(proposal['allowed_paths']) <= set(row['allowed_paths']):
        raise ValueError('paths not admitted')
    validation_id = a.identifier(proposal['validation_id'])
    if validation_id not in row['validations']:
        raise ValueError('validation not admitted')
    request = dict(schema_version=1, task_id=proposal['task_id'], repository_id=repo_id,
                   objective=proposal['objective'], allowed_paths=proposal['allowed_paths'],
                   validation_argv=row['validations'][validation_id],
                   worker_timeout_seconds=row['worker_timeout_seconds'],
                   validation_timeout_seconds=row['validation_timeout_seconds'],
                   commit_policy='leave_uncommitted')
    # Validate with the same runner contract, without publishing intermediate files.
    local('manual_runner').validate_request(request)
    receipt = {'schema_version': 1, 'authenticated_identity': identity,
               'policy_sha256': a.digest(Path(policy_path).read_bytes()), 'request': request,
               'execution_authorized': False, 'publication_authorized': False}
    submission_id = a.digest(a.encoded(receipt))
    root = a.private_dir(state)
    a.absent(root / (submission_id + '.json'), a.encoded(receipt))
    return {'submission_id': submission_id, 'path': str(root / (submission_id + '.json')),
            'status': 'pending_operator_review', 'api_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('policy', 'proposal', 'state', 'operator-identity'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    # Operator CLI only. A future chat adapter must authenticate its transport independently.
    print(json.dumps(prepare(args.policy, args.proposal, args.state,
                             authenticated_identity=args.operator_identity)))
