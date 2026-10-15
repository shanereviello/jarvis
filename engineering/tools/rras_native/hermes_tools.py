"""Register preparation-only tools on an existing authenticated Hermes MCP surface."""
import importlib.util
from pathlib import Path
import tempfile


def register(server, *, policy, state, authenticated_identity):
    """Caller supplies identity from trusted transport context, never tool arguments.

    No server is started here. Do not attach this to an unauthenticated endpoint.
    This tool prepares a receipt; launch and publication are operator actions.
    """
    spec = importlib.util.spec_from_file_location('intake', Path(__file__).with_name('intake.py'))
    intake = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(intake)
    a = intake.local('activity')

    @server.tool()
    def prepare_coding_task(task_id: str, repository_id: str, objective: str,
                            allowed_paths: list[str], validation_id: str) -> dict:
        """Prepare a bounded coding task for operator review; does not execute it."""
        identity = authenticated_identity()
        proposal = dict(task_id=task_id, repository_id=repository_id, objective=objective,
                        allowed_paths=allowed_paths, validation_id=validation_id)
        # Temporary inputs and retained receipts stay under the trusted service's private state.
        root = a.private_dir(state)
        with tempfile.TemporaryDirectory(prefix='proposal-', dir=root) as folder:
            path = Path(folder)/'proposal.json'
            a.absent(path, a.encoded(proposal))
            result = intake.prepare(policy, path, root, authenticated_identity=identity)
        return {key: result[key] for key in ('submission_id', 'status', 'api_calls')}

    @server.tool()
    def coding_task_proposal(submission_id: str) -> dict:
        """Read your pending proposal; native execution status is not represented here."""
        import re
        if not re.fullmatch('[0-9a-f]{64}', submission_id):
            raise ValueError('exact submission digest required')
        receipt = a.load(Path(state)/(submission_id+'.json'))
        if a.digest(a.encoded(receipt)) != submission_id:
            raise ValueError('proposal integrity failure')
        identity = authenticated_identity()
        if receipt['authenticated_identity'] != identity:
            raise ValueError('proposal belongs to another identity')
        current = a.load(policy)
        if receipt['request']['repository_id'] not in current['identities'].get(identity, []):
            raise ValueError('identity or repository admission revoked')
        return receipt
