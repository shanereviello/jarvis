import copy
import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/onboarding_human_attestation.py'
spec=importlib.util.spec_from_file_location('human_attestation_test',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def values():
    scope={'kind':'repository','id':'jarvis'}
    pin=dict(document_id='doc_'+'1'*32,version=1,markdown_sha256='a'*64)
    body=dict(kind='architecture',state='approved',attribution='imported_source',
        attributed_author=dict(role='human',runtime='linear',source_actor_id='human'),
        source_reference=dict(namespace='linear_comment',id='comment',sha256='b'*64),decision_text='approved')
    record=dict(submission=dict(operation='decision.observe',scope=scope,body=body,context=dict(project_id='project',architecture=pin)),
        receipt=dict(request_sha256='c'*64))
    verified=dict(project_id='project',scope=scope,document_id=pin['document_id'],version=1,markdown_sha256='a'*64,
        human_actor_id='human',source_namespace='linear_comment',source_id='comment',source_sha256='b'*64,decision_text='approved')
    return record,verified


def test_rechecks_exact_source_and_retained_decision():
    record,verified=values();calls=[]
    check=module.Verifier(lambda receipt:'review',lambda value:calls.append(value) or verified)
    assert check(record) and calls==[dict(review_id='review',comment_id='comment')]


@pytest.mark.parametrize('field',['project_id','scope','document_id','version','markdown_sha256','human_actor_id','source_id','source_sha256','decision_text'])
def test_refuses_different_or_changed_native_evidence(field):
    record,verified=values();verified=copy.deepcopy(verified);verified[field]='different'
    with pytest.raises(ValueError):module.Verifier(lambda _:'review',lambda _:verified)(record)


def test_refuses_agent_reported_decision():
    record,verified=values();record['submission']['body']['attribution']='agent_reported'
    with pytest.raises(ValueError):module.Verifier(lambda _:'review',lambda _:verified)(record)
