import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/onboarding_admission_service.py'
spec = importlib.util.spec_from_file_location('admission_service_fixture', path)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_only_root_can_request_read_only_verification():
    calls = []
    broker = module.Broker(lambda request:calls.append(request) or True)
    message = {'operation':'admission.verify','request':{'fixture':True}}
    with pytest.raises(ValueError):broker.dispatch(1234, message)
    with pytest.raises(ValueError):broker.dispatch(0, dict(message, extra=True))
    with pytest.raises(ValueError):broker.dispatch(0, {'operation':'decision.write','request':{}})
    assert broker.dispatch(0, message) == {'verified':True}
    assert calls == [{'fixture':True}]


def test_assembly_restricts_history_to_scoped_reads(monkeypatch):
    def human(*_):return lambda _:True
    def evidence(rpc, *_):
        def verify(request):
            rpc(request)
            return True
        return verify
    modules = {'onboarding_human_attestation':SimpleNamespace(Verifier=human),
               'onboarding_admission_evidence':SimpleNamespace(Verifier=evidence)}
    monkeypatch.setattr(module, 'local', lambda name:modules[name])
    allowed = []
    reader = SimpleNamespace(allowed=lambda scope:allowed.append(scope))
    operator = {'reviews':SimpleNamespace(decision_review=lambda _:None),
        'decision_source':SimpleNamespace(verify=lambda _:None),'history':SimpleNamespace(reader=reader)}
    broker = module.assemble(operator, lambda _:None, lambda _:None, lambda _:True)
    request = {'method':'project_read','scope':{'kind':'repository','id':'jarvis'},'query':{}}
    assert broker.dispatch(0, {'operation':'admission.verify','request':request}) == {'verified':True}
    assert allowed == [request['scope']]
    with pytest.raises(ValueError):
        broker.dispatch(0, {'operation':'admission.verify','request':dict(request,method='project_submit')})
