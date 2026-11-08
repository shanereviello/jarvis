"""Native context has no agent-selected identity or environment fallback."""
import os
import pytest
from test_reporting_capture_collectors import module


m=module('hermes_native_context')
ORG='00000000-0000-0000-0000-000000000001';SESSION='00000000-0000-0000-0000-000000000005'
ALIAS='linear:'+ORG+':'+SESSION;RUN='run_'+'a'*32


def test_actual_native_alias_and_run_are_separate_identifiers():
    assert m.parse('api_server',ALIAS,RUN)==dict(organization_id=ORG,session_id=SESSION,hermes_session_id=ALIAS,run_id=RUN)


@pytest.mark.parametrize('platform,session,run',[('cli',ALIAS,RUN),('api_server','../'+ALIAS,RUN),('api_server',ALIAS,'agent-chosen'),
    ('api_server',ALIAS.replace(ORG,ORG[:-1]+'A'),RUN),('api_server',ALIAS+':extra',RUN),('api_server',None,RUN)])
def test_unknown_or_unbound_surface_is_refused(platform,session,run):
    with pytest.raises(ValueError):m.parse(platform,session,run)


def test_readonly_selection_requires_authorization_before_any_file_access():
    with pytest.raises(ValueError,match='authorization'):module('hermes_readonly').selected('/never-opened',ALIAS,'')
