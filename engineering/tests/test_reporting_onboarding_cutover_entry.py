import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

path = Path(__file__).resolve().parents[1] / 'tools/rras_reporting/onboarding_cutover_entry.py'
spec = importlib.util.spec_from_file_location('cutover_entry_fixture',path)
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_cutover_configuration_requires_exact_fields_distinct_identities_and_canonical_paths(tmp_path):
    value = dict(contract='codex-issue-cutover-host.v1',request={},transition={},operator_socket=str(tmp_path/'operator.sock'),
        operator_uid=61180,workspace_root=str(tmp_path/'workspaces'),native_release=str(tmp_path/'release'),
        sandbox_proof=str(tmp_path/'proof'),execution_grants=str(tmp_path/'grants'),audit_directory=str(tmp_path/'audit'),
        broker_socket=str(tmp_path/'broker.sock'))
    accounts = {'rras-codex-adapter':SimpleNamespace(pw_uid=61181,pw_gid=61181),
                'rras-codex-native':SimpleNamespace(pw_uid=61182,pw_gid=61182)}
    assert module.configuration(value,accounts.get)[0] == value
    with pytest.raises(ValueError):module.configuration(dict(value,operator_uid=61181),accounts.get)
    with pytest.raises(ValueError):module.configuration(dict(value,extra=True),accounts.get)
    with pytest.raises(ValueError):module.configuration(dict(value,broker_socket='relative'),accounts.get)
