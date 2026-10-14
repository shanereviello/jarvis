"""Verify deployed Linear bridge behavior offline after source consolidation."""
import json
from unittest.mock import patch
import pytest
from app.core.config import get_settings
from app.services.linear_gateway import call_linear_gateway, LinearGatewayError


def test_gateway_preserves_operation_and_secret_delivery(tmp_path,monkeypatch):
    secret=tmp_path/'secret';secret.write_text('NONSECRET-LINEAR-FIXTURE\n')
    monkeypatch.setenv('LINEAR_GATEWAY_URL','http://fixture.invalid/linear')
    monkeypatch.setenv('LINEAR_GATEWAY_SECRET_FILE',str(secret));get_settings.cache_clear()
    with patch('app.services.linear_gateway.urlopen') as request:
        request.return_value.__enter__.return_value.read.return_value=b'{"success": true}'
        assert call_linear_gateway('list',{'limit':2})=={'success':True}
        sent=request.call_args.args[0];body=json.loads(sent.data)
        assert body['schemaVersion']=='linear-action-v1' and body['operation']=='list' and body['arguments']=={'limit':2}
        assert sent.get_header('X-jarvis-bridge-secret')=='NONSECRET-LINEAR-FIXTURE'
        assert request.call_args.kwargs['timeout']==20
    get_settings.cache_clear()


def test_missing_configuration_stops_before_network(monkeypatch):
    monkeypatch.setenv('LINEAR_GATEWAY_URL','');get_settings.cache_clear()
    with patch('app.services.linear_gateway.urlopen') as request:
        with pytest.raises(LinearGatewayError):call_linear_gateway('list',{})
        request.assert_not_called()
    get_settings.cache_clear()
