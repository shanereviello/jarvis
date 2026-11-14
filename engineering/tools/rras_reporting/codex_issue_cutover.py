"""Orchestrate an offline issue admission using protected host adapters.

This module does not itself acquire OS locks, write files, or control services.
The host adapter must hold its admission lock and the stopped runtime's journal
lock for the entire call, provide durable intent and atomic policy installation,
and independently recheck the current history and spending authority. No
recovery transition or service start is performed here.
"""
import hashlib
import importlib.util
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location('cutover_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(adapter, *, expected_plan_sha256):
    """Execute a single new transition; interrupted attempts require inspection.

    All adapter methods must operate inside the same protected lock context.
    They are deliberately injected: this is not a production host installer.
    """
    runtime = local('codex_runtime')
    recovery = local('codex_issue_cutover_recovery')
    with adapter.exclusive_stopped():
        # Recompute admission from live evidence while stopped and locked.
        plan, old, new = adapter.revalidate()
        plan_sha = hashlib.sha256(runtime.encoded(plan)).hexdigest()
        if plan_sha != expected_plan_sha256:
            raise ValueError('admission plan changed; inspect before retry')
        old_sha = hashlib.sha256(runtime.encoded(old)).hexdigest()
        new_sha = hashlib.sha256(runtime.encoded(new)).hexdigest()
        if (plan.get('old_policy_sha256'), plan.get('new_policy_sha256')) != (old_sha, new_sha):
            raise ValueError('plan policy digests differ')
        def state():
            return recovery.classify(old_policy_sha256=old_sha, new_policy_sha256=new_sha,
                journal_policy_sha256=adapter.journal_digest(), file_policy_sha256=adapter.file_digest(),
                runtime_stopped=True)['state']
        if state() != 'not_started':
            raise ValueError('cutover is not pristine; inspect retained state')
        # Durable intent is mandatory before either protected resource changes.
        adapter.retain_intent(plan_sha, plan, old, new)
        if state() != 'not_started':
            raise ValueError('policy changed after intent; inspect retained state')
        adapter.update_journal(plan_sha)
        if state() != 'journal_ahead':
            raise ValueError('journal outcome uncertain; inspect retained state')
        # Revocation or a changed issue can occur during the journal update.
        # In that case leave the service stopped with the old file intact.
        adapter.recheck_authority_and_evidence(plan, new)
        adapter.install_policy_atomically(old_sha, new)
        if state() != 'consistent_new':
            raise ValueError('policy installation uncertain; inspect retained state')
        adapter.retain_completion(plan_sha)
        return dict(cutover_complete=True, plan_sha256=plan_sha,
                    service_started=False, models_started=0, automatic_retry=False)
