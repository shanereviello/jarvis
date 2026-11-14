import copy
import hashlib
import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'tools/rras_reporting/n8n_codex_origin_patch.py'
spec=importlib.util.spec_from_file_location('origin_patch',path)
patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)


def test_candidate_changes_only_origin_nodes_and_stays_inactive(monkeypatch):
    old='// synthetic original origin verifier\n'
    monkeypatch.setattr(patch,'OLD_SOURCE_SHA256',hashlib.sha256(old.encode()).hexdigest())
    original=dict(id='original123',active=True,nodes=[
        dict(name='Poll',type='n8n-nodes-base.scheduleTrigger',parameters={}),
        dict(name='Prepare Codex origin read',type='n8n-nodes-base.code',parameters=dict(jsCode=patch.OLD_SESSION+' '+patch.OLD_COMMENT)),
        dict(name='Verify native Codex origin',type='n8n-nodes-base.code',parameters=dict(jsCode=old+'// exact policy')),
        dict(name='Dispatch',type='n8n-nodes-base.httpRequest',parameters=dict(url='http://fixture'))],
        connections={'fixture':'unchanged'},settings={'executionOrder':'v1'})
    before=copy.deepcopy(original)
    result=patch.prepare(original,old,'0123456789abcdef','original123')
    assert original==before and result['active'] is False and result['id']!='original123'
    assert result['nodes'][0]==before['nodes'][0] and result['nodes'][3]==before['nodes'][3]
    assert patch.NEW_SESSION in result['nodes'][1]['parameters']['jsCode']
    assert patch.NEW_COMMENT in result['nodes'][1]['parameters']['jsCode']
    assert result['nodes'][2]['parameters']['jsCode'].endswith('// exact policy')
    assert result['connections']==before['connections'] and result['settings']==before['settings']
    for change in ('disabled','wrong_source','changed_query','extra_webhook'):
        bad=copy.deepcopy(before)
        if change=='disabled':bad['active']=False
        if change=='changed_query':bad['nodes'][1]['parameters']['jsCode']='unexpected'
        if change=='extra_webhook':bad['nodes'].append(dict(name='web',type='n8n-nodes-base.webhook'))
        with pytest.raises(ValueError):
            patch.prepare(bad,'wrong' if change=='wrong_source' else old,'0123456789abcdef','original123')
