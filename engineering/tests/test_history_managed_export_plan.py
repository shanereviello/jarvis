"""Passive plan construction binds exact revisions without leaking narratives."""
import copy
import hashlib
import os
import pytest
from test_engineering_history_local import module
from test_history_managed_link import setup,exporter,j,fixtures

m=module('managed_export_plan_cli');c=module('contract')


def test_plan_selects_only_reviewed_allowlist(setup):
    _,rows,_,work,_=setup;operational=rows[1]
    plan=m.build(operational,work,'managed-production','a'*32);review=m.inspect(plan)
    assert plan['source_work_sha256']==exporter.local('workflow_records').record_digest(operational)
    assert review['source_authenticated'] is False and review['root_source_opened'] is False
    assert review['export_authorized'] is False and review['history_records_written'] is False
    assert 'objective' not in plan and 'actor' not in plan and 'provenance' not in plan


@pytest.mark.parametrize('field',['work_item_id','repository_id','baseline','allowed_paths'])
def test_mismatched_engineering_scope_refused(setup,field):
    _,rows,_,work,_=setup;work=copy.deepcopy(work)
    if field=='work_item_id':work['body'][field]='wrk_'+'f'*32
    elif field=='repository_id':work['body'][field]='other_repo'
    elif field=='baseline':work['body'][field]['commit']='f'*40
    else:work['body'][field]=['other.py']
    with pytest.raises(ValueError,match='exact work'):m.build(rows[1],work,'managed-production','a'*32)


@pytest.mark.parametrize('journal,capture',[('../escape','a'*32),('valid','bad'),('valid','A'*32)])
def test_unsafe_export_identity_refused(setup,journal,capture):
    _,rows,_,work,_=setup
    with pytest.raises(ValueError):m.build(rows[1],work,journal,capture)


def test_private_plan_preparation_has_root_export_canonical_digest(setup,tmp_path):
    _,rows,_,work,_=setup;parent=tmp_path/'private';parent.mkdir(mode=0o700)
    a=parent/'operational.json';b=parent/'engineering.json';module('link_delivery').write(a,rows[1]);module('link_delivery').write(b,work)
    result=m.prepare(parent/'proposal',a,b,'managed-production','a'*32)
    path=parent/'proposal/plan.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==result['plan_sha256']
    assert path.stat().st_mode&0o777==0o600 and (parent/'proposal').stat().st_mode&0o777==0o700
    with pytest.raises(FileExistsError):m.prepare(parent/'proposal',a,b,'managed-production','a'*32)


def test_bad_scope_before_destination_creation(setup,tmp_path):
    _,rows,_,work,_=setup;parent=tmp_path/'private';parent.mkdir(mode=0o700)
    work=copy.deepcopy(work);work['body']['allowed_paths']=['other.py']
    a=parent/'a.json';b=parent/'b.json';module('link_delivery').write(a,rows[1]);module('link_delivery').write(b,work)
    with pytest.raises(ValueError):m.prepare(parent/'proposal',a,b,'managed-production','a'*32)
    assert not (parent/'proposal').exists()


def test_source_revision_change_changes_plan_binding(setup):
    _,rows,_,work,_=setup;original=m.build(rows[1],work,'managed-production','a'*32)
    changed=copy.deepcopy(rows[1]);changed['objective']='Different operational objective, same displayed scope'
    revised=m.build(changed,work,'managed-production','b'*32)
    assert original['source_work_sha256']!=revised['source_work_sha256']


def test_cli_inspect_never_calls_root_or_service(setup,tmp_path,capsys):
    _,rows,_,work,_=setup;path=tmp_path/'plan.json';module('link_delivery').write(path,m.build(rows[1],work,'managed-production','a'*32))
    m.main(['inspect','--plan',str(path)])
    assert '"export_authorized":false' in capsys.readouterr().out


def test_unicode_scope_uses_root_exporter_encoding(setup,tmp_path):
    _,rows,_,work,_=setup;operational=copy.deepcopy(rows[1]);work=copy.deepcopy(work)
    operational['requested_paths']=['docs/café.md'];work['body']['allowed_paths']=operational['requested_paths']
    parent=tmp_path/'private';parent.mkdir(mode=0o700)
    a=parent/'a.json';b=parent/'b.json';module('link_delivery').write(a,operational);module('link_delivery').write(b,work)
    result=m.prepare(parent/'proposal',a,b,'managed-production','a'*32)
    assert hashlib.sha256((parent/'proposal/plan.json').read_bytes()).hexdigest()==result['plan_sha256']


def test_privileged_proposal_preparation_refused_before_inputs(tmp_path,monkeypatch):
    monkeypatch.setattr(m.os,'getuid',lambda:0)
    with pytest.raises(ValueError,match='unprivileged'):m.prepare(tmp_path/'proposal','/missing','/missing','journal','a'*32)
    assert not (tmp_path/'proposal').exists()
