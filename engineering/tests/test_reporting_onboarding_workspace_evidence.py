import importlib.util
import os
from pathlib import Path
import subprocess
import pytest
from test_reporting_codex_runtime import uid

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_workspace_evidence.py'
spec=importlib.util.spec_from_file_location('workspace_evidence_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


@pytest.fixture
def workspace(tmp_path):
    root=tmp_path/'workspaces';root.mkdir();issue=uid(42);repo=root/issue;repo.mkdir(mode=0o700)
    def git(*args):return subprocess.check_output(['/usr/bin/git','-C',str(repo),*args],stderr=subprocess.DEVNULL,text=True).strip()
    git('init');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    (repo/'README').write_text('fixture\n');git('add','README');git('commit','-m','fixture')
    value=dict(issue_id=issue,workspace=str(repo),native_socket='/run/fixture/'+issue,baseline_commit=git('rev-parse','HEAD'))
    return root,repo,value,git


def test_clean_isolated_workspace_is_checked(workspace):
    root,repo,value,git=workspace
    verifier=module.Verifier(str(root),os.getuid(),lambda issue:'/run/fixture/'+issue,lambda _:True)
    assert verifier(value) is True


@pytest.mark.parametrize('change',['modified','untracked','baseline','remote','socket','isolation','symlink'])
def test_refuses_bad_workspace(workspace,change,tmp_path):
    root,repo,value,git=workspace;isolation=lambda _:True
    if change=='modified':(repo/'README').write_text('changed')
    elif change=='untracked':(repo/'new').write_text('new')
    elif change=='baseline':value['baseline_commit']='0'*40
    elif change=='remote':git('remote','add','origin','https://example.invalid/example')
    elif change=='socket':value['native_socket']='/run/other'
    elif change=='isolation':isolation=lambda _:False
    else:
        link=tmp_path/'alias';link.symlink_to(repo,target_is_directory=True);value['workspace']=str(link)
    verifier=module.Verifier(str(root),os.getuid(),lambda issue:'/run/fixture/'+issue,isolation)
    with pytest.raises(ValueError):verifier(value)
