"""Read-only admission verification through a protected operator service.

The root caller may request only a current verification; no decision, scope,
or work record can be written through this broker. Hosting is separate.
"""
import importlib.util
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location('admission_service_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Broker:
    def __init__(self, verify, *, partial=False):
        if not callable(verify):raise ValueError('protected admission verifier required')
        if type(partial) is not bool:raise ValueError('explicit admission verification scope required')
        self.grants = {0:{}}
        self.verify = verify
        self.partial = partial

    def dispatch(self, peer, message):
        if type(peer) is not int or peer != 0 or type(message) is not dict or set(message) != {'operation','request'}:
            raise ValueError('protected admission peer refused')
        if message['operation'] != 'admission.verify' or type(message['request']) is not dict:
            raise ValueError('exact read-only admission request required')
        if self.verify(message['request']) is not True:
            raise ValueError('admission evidence refused')
        return {'history_issue_human_verified':True} if self.partial else {'verified':True}


class Client:
    def __init__(self, path, operator_uid, *, partial=False):
        if type(partial) is not bool:raise ValueError('explicit admission verification scope required')
        self.unix = local('onboarding_broker_unix').unix()
        self.unix.uid(operator_uid)
        self.unix.DEADLINE_SECONDS = 60
        self.path = self.unix.endpoint(path)
        self.operator_uid = operator_uid
        self.partial = partial

    def __call__(self, request):
        result = self.unix.call(self.path, self.operator_uid,
            {'operation':'admission.verify','request':request})
        expected = {'history_issue_human_verified':True} if self.partial else {'verified':True}
        if result != expected:
            raise ValueError('protected operator admission verification refused')
        return True


def assemble(operator, history_rpc, read_issue, verify_workspace, *, partial=False):
    if type(operator) is not dict or not all(callable(x) for x in (history_rpc,read_issue,verify_workspace)):
        raise ValueError('protected admission services required')
    reviews = operator['reviews'];source = operator['decision_source'];history = operator['history']
    human = local('onboarding_human_attestation').Verifier(reviews.decision_review, source.verify)
    def scoped_rpc(message):
        if (type(message) is not dict or message.get('method') != 'project_read' or
                set(message) != {'method','scope','query'}):
            raise ValueError('scoped history read required')
        history.reader.allowed(message['scope'])
        return history_rpc(message)
    verify = local('onboarding_admission_evidence').Verifier(scoped_rpc, read_issue, human, verify_workspace)
    return Broker(verify,partial=partial)


def assemble_history(operator, history_rpc, read_issue):
    """Verify only history, human and native issue; root must verify workspace."""
    return assemble(operator, history_rpc, read_issue, lambda _:True, partial=True)


class SplitVerifier:
    def __init__(self, history_and_issue, workspace):
        if not callable(history_and_issue) or not callable(workspace):
            raise ValueError('independent admission halves required')
        self.history_and_issue, self.workspace = history_and_issue, workspace

    def __call__(self, request):
        if self.history_and_issue(request) is not True or self.workspace(request) is not True:
            raise ValueError('complete admission evidence required')
        return True
