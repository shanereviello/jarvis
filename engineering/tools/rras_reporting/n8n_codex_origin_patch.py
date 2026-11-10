"""Prepare an inactive copy of the live Codex dispatch with one origin fix.

This does not import, publish, or change a workflow. The caller must independently
verify the live workflow/version and protect the candidate before any cutover.
"""
import copy
import hashlib
from pathlib import Path
import re

OLD_SOURCE_SHA256='73b35d7834fdabf3d524bda9cc03e6f7369e09b1c32e495d71d6cb7e6f1db189'
OLD_SESSION='agentSession(id:$id){id appUser{id}'
NEW_SESSION='agentSession(id:$id){id sourceMetadata appUser{id}'
OLD_COMMENT='comment{id user{id app}} sourceComment{id user{id app}}'
NEW_COMMENT='comment{id isArtificialAgentSessionRoot agentSession{id} user{id app}} sourceComment{id user{id app}}'


def prepare(original, old_source, candidate_id, expected_original_id):
    if (type(expected_original_id) is not str or not re.fullmatch('[A-Za-z0-9]{1,64}',expected_original_id) or
            type(original) is not dict or original.get('id')!=expected_original_id or original.get('active') is not True or
            type(original.get('nodes')) is not list or type(original.get('connections')) is not dict or
            type(original.get('settings')) is not dict or type(old_source) is not str or
            hashlib.sha256(old_source.encode()).hexdigest()!=OLD_SOURCE_SHA256 or
            type(candidate_id) is not str or not re.fullmatch('[0-9a-f]{16}',candidate_id) or candidate_id==expected_original_id):
        raise ValueError('exact active dispatch and pinned source required')
    nodes=original['nodes']; matches={}
    for name in ('Prepare Codex origin read','Verify native Codex origin'):
        found=[n for n in nodes if n.get('name')==name and n.get('type')=='n8n-nodes-base.code']
        if len(found)!=1:raise ValueError('exact dispatch origin nodes required')
        matches[name]=found[0]
    if any(n.get('type')=='n8n-nodes-base.webhook' for n in nodes):
        raise ValueError('dispatch candidate cannot add a public webhook')
    prepare_code=matches['Prepare Codex origin read'].get('parameters',{}).get('jsCode')
    verify_code=matches['Verify native Codex origin'].get('parameters',{}).get('jsCode')
    if (type(prepare_code) is not str or prepare_code.count(OLD_SESSION)!=1 or
            prepare_code.count(OLD_COMMENT)!=1 or type(verify_code) is not str or not verify_code.startswith(old_source)):
        raise ValueError('running origin nodes differ from reviewed baseline')
    new_source=Path(__file__).with_name('n8n_native_origin.js').read_text()
    patched_nodes=copy.deepcopy(nodes)
    for node in patched_nodes:
        if node['name']=='Prepare Codex origin read':
            node['parameters']['jsCode']=prepare_code.replace(OLD_SESSION,NEW_SESSION).replace(OLD_COMMENT,NEW_COMMENT)
        elif node['name']=='Verify native Codex origin':
            node['parameters']['jsCode']=new_source+verify_code[len(old_source):]
    return dict(id=candidate_id,name='Codex Runtime Dispatch — verified delegation fix (inactive)',active=False,
        nodes=patched_nodes,connections=copy.deepcopy(original['connections']),settings=copy.deepcopy(original['settings']),
        tags=[],pinData={})
