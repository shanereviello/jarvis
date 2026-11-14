import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/onboarding_linear_issue_reader.py'
spec = importlib.util.spec_from_file_location('native_issue_fixture', path)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
uid = lambda n: '00000000-0000-0000-0000-' + str(n).zfill(12)


def test_issue_reader_checks_viewer_organization_and_issue():
    data = {'viewer':{'id':uid(1), 'organization':{'id':uid(2)}},
            'issue':{'id':uid(3), 'team':{'id':uid(4)}, 'project':{'id':uid(5)}}}
    def graphql(request):
        assert request == {'query':module.QUERY, 'variables':{'id':uid(3)}}
        return {'data':data}
    reader = module.Reader(graphql, uid(1), uid(2))
    assert reader(uid(3)) == dict(organization_id=uid(2), team_id=uid(4), linear_project_id=uid(5), issue_id=uid(3))
    data['viewer']['organization']['id'] = uid(6)
    with pytest.raises(ValueError, match='identity'):reader(uid(3))
    data['viewer']['organization']['id'] = uid(2)
    data['issue']['project'] = None
    with pytest.raises(ValueError, match='identity'):reader(uid(3))


def test_issue_transport_uses_fixed_query_and_loopback(monkeypatch):
    transport_path = path.with_name('onboarding_operator_issue_http.py')
    transport_spec = importlib.util.spec_from_file_location('native_issue_http_fixture', transport_path)
    transport = importlib.util.module_from_spec(transport_spec);transport_spec.loader.exec_module(transport)
    import json
    calls = []
    class Response:
        status = 200
        def read(self, _):return json.dumps({'permitted':True,'data':{'fixture':True}}).encode()
    class Connection:
        def __init__(self, host, port, timeout):
            assert host == '127.0.0.1' and port == 8765
        def request(self, method, url, body, headers):
            calls.append((method,url,json.loads(body)))
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(transport.http.client, 'HTTPConnection', Connection)
    client = transport.Transport('http://127.0.0.1:8765/webhook/rras-operator-issue-'+uid(1), uid(1), b'x'*32)
    assert client({'query':module.QUERY,'variables':{'id':uid(3)}}) == {'data':{'fixture':True}}
    assert calls == [('POST','/webhook/rras-operator-issue-'+uid(1),{'issue_id':uid(3)})]
    with pytest.raises(ValueError):client({'query':'mutation','variables':{'id':uid(3)}})
    with pytest.raises(ValueError):transport.Transport('http://example.com:8765/webhook/rras-operator-issue-'+uid(1), uid(1), b'x'*32)
