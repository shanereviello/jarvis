"""Build inactive n8n import payloads from protected token inputs; never import."""
import copy
import re

TOKENS={
    'PENDING_CODEX_PLANNING_READER':'codex-reader',
    'PENDING_CODEX_PLANNING_CREATOR':'codex-creator',
    'PENDING_OPERATOR_COMMENT':'operator-comment',
    'PENDING_OPERATOR_ISSUE':'operator-issue',
    'PENDING_JARVIS_PLANNING_READER':'jarvis-reader',
    'PENDING_JARVIS_PLANNING_CREATOR':'jarvis-creator',
}
EXISTING={'LinearBridgePg20261007','LQvmpZCiLdxQkUJw','oaPWcNSNCus22jh4'}
WORKFLOWS={'codex-origin','codex-issue','codex-create','operator-comment','operator-issue',
           'jarvis-origin','jarvis-issue','jarvis-create'}


def build(workflows,ids,tokens,workflow_ids):
    if (type(workflows) is not dict or set(workflows)!=WORKFLOWS or
            type(ids) is not dict or set(ids)!=set(TOKENS.values()) or
            type(tokens) is not dict or set(tokens)!=set(ids) or
            type(workflow_ids) is not dict or set(workflow_ids)!=WORKFLOWS):
        raise ValueError('exact inactive import inputs required')
    all_ids=list(ids.values())+list(workflow_ids.values())
    if any(type(x) is not str or not re.fullmatch(r'[0-9a-f]{16}',x) for x in all_ids) or len(set(all_ids))!=len(all_ids):
        raise ValueError('distinct bounded import identifiers required')
    if any(type(t) is not str or not re.fullmatch(r'[0-9a-f]{64}',t) for t in tokens.values()) or len(set(tokens.values()))!=len(tokens):
        raise ValueError('distinct protected credentials required')
    credentials=[dict(id=ids[name],name='RRAS v0.5 '+name,type='httpHeaderAuth',
        data=dict(name='Authorization',value='Bearer '+tokens[name])) for name in sorted(ids)]
    selected=[];seen=set();paths=set()
    for name in sorted(WORKFLOWS):
        value=copy.deepcopy(workflows[name])
        if type(value) is not dict or value.get('active') is not False or type(value.get('nodes')) is not list:
            raise ValueError('inactive workflow required')
        value['id']=workflow_ids[name]
        for node in value['nodes']:
            if type(node) is not dict:raise ValueError('workflow node required')
            for credential in (node.get('credentials') or {}).values():
                if type(credential) is not dict:raise ValueError('credential reference required')
                old=credential.get('id')
                if old in TOKENS:
                    token_name=TOKENS[old];credential['id']=ids[token_name];credential['name']='RRAS v0.5 '+token_name;seen.add(token_name)
                elif old not in EXISTING:raise ValueError('unexpected credential reference')
            if node.get('type')=='n8n-nodes-base.webhook':
                route=node.get('parameters',{}).get('path')
                if type(route) is not str or not re.fullmatch(r'[a-z0-9-]{1,128}',route) or route in paths:
                    raise ValueError('unique private webhook path required')
                paths.add(route)
        selected.append(value)
    if seen!=set(ids) or len(paths)!=len(WORKFLOWS):raise ValueError('all independent credentials and routes required')
    return dict(credentials=credentials,workflows=selected,webhook_paths=sorted(paths))
