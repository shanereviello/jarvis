import importlib.util
import os
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_attestation_web_entry.py'
spec=importlib.util.spec_from_file_location('attestation_entry_fixture',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def config(tmp_path):
    return dict(browser_uid=os.getuid(),browser_gid=os.getgid(),operator_uid=61183,operator_socket=str(tmp_path/'operator.sock'),
        bind='127.0.0.1',port=8769,access=dict(issuer='https://fixture.cloudflareaccess.com',audience='fixture',email='owner@example.test',origin='https://fixture.example.test'))


def test_browser_configuration_is_private_and_separately_identified(tmp_path):
    value=config(tmp_path);assert module.configuration(value,os.getuid(),os.getgid())==value
    for changed in (dict(operator_uid=os.getuid()),dict(bind='0.0.0.0'),dict(bind='8.8.8.8'),dict(bind='169.254.1.1'),dict(port=0),dict(extra=True)):
        with pytest.raises(ValueError):module.configuration(dict(value,**changed),os.getuid(),os.getgid())
    options=module.web('entry').server_options(value)
    assert options['proxy_headers'] is False and options['access_log'] is False and options['workers']==1


def test_browser_entry_validates_optional_route_prefix(tmp_path):
    value=dict(config(tmp_path),path_prefix='/engineering-approval')
    assert module.configuration(value,os.getuid(),os.getgid())==value
    with pytest.raises(ValueError):
        module.configuration(dict(value,path_prefix='//bad'),os.getuid(),os.getgid())
