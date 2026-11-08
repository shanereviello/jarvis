"""Pure native Linear handoff preparation/verification for n8n-owned transport.

No OAuth custody or network client. n8n supplies separately authenticated actor
observations and retains mutation intent before using the appropriate credential.
Agent text is context; it cannot supply actual app/session/work identities.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import uuid


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def identifier(value):
    if type(value) is not str or str(uuid.UUID(value))!=value:raise ValueError('canonical UUID required')
    return value
def text(value,maximum=8192):
    if type(value) is not str or not value.strip() or '\0' in value or len(value.encode())>maximum:raise ValueError('bounded handoff context required')
    return value
def local(name):
    spec=importlib.util.spec_from_file_location('native_handoff_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def stable_uuid(value):return str(uuid.UUID(bytes=hashlib.sha256(encoded(value)).digest()[:16],version=4))


def policy(value):
    if (type(value) is not dict or set(value)!={'contract','organization_id','agents','issues'} or
            value['contract']!='native-agent-handoff-policy.v1' or set(value['agents'])!={'jarvis','codex'}):raise ValueError('two installed native identities required')
    identifier(value['organization_id']);actors=[identifier(value['agents'][role]) for role in ('jarvis','codex')]
    if len(set(actors))!=2:raise ValueError('separate native agents required')
    local('codex_runtime').policy(dict(contract='codex-runtime-policy.v1',organization_id=value['organization_id'],
        app_user_id=value['agents']['codex'],execution_authorized=False,execution_authority_reference='handoff validation only',
        binary='/usr/bin/false',cwd='/',sandbox='read-only',issues=value['issues']))
    return json.loads(encoded(value))


def prepare(configuration,role,trusted,arguments):
    """Transport/native adapter supplies trusted context; tool accepts prose only."""
    configuration=policy(configuration)
    if role not in ('jarvis','codex') or type(trusted) is not dict or set(trusted)!={'session_id','issue_id','binding','parent_handoff_id','depth'}:
        raise ValueError('actual scoped source session required')
    identifier(trusted['session_id']);identifier(trusted['issue_id'])
    if trusted['binding']!=configuration['issues'].get(trusted['issue_id']):raise ValueError('actual work/architecture binding differs')
    if trusted['parent_handoff_id'] is not None:identifier(trusted['parent_handoff_id'])
    if type(trusted['depth']) is not int or not 0<=trusted['depth']<4:raise ValueError('handoff chain limit reached; human context required')
    if (type(arguments) is not dict or set(arguments)!={'key','summary','requested_action','references','limitations'} or
            not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',arguments.get('key','')) or
            type(arguments['references']) is not list or len(arguments['references'])>32 or
            type(arguments['limitations']) is not list or len(arguments['limitations'])>32):raise ValueError('exact bounded handoff report required')
    for field in ('summary','requested_action'):text(arguments[field])
    for item in arguments['limitations']:text(item,4096)
    for ref in arguments['references']:
        if type(ref) is not dict or set(ref)!={'namespace','id','sha256'}:raise ValueError('exact evidence reference required')
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',ref['namespace']):raise ValueError('exact evidence namespace required')
        text(ref['id'],512)
        if ref['sha256'] is not None and not re.fullmatch('[0-9a-f]{64}',ref['sha256']):raise ValueError('exact evidence digest required')
    clean,redactions=local('capture_intake').redact_object(arguments)
    target='jarvis' if role=='codex' else 'codex'
    identity=dict(org=configuration['organization_id'],sender=configuration['agents'][role],session=trusted['session_id'],key=arguments['key'])
    result=dict(contract='native-agent-handoff.v1',id=stable_uuid(identity),organization_id=configuration['organization_id'],
        sender=role,recipient=target,sender_app_user_id=configuration['agents'][role],recipient_app_user_id=configuration['agents'][target],
        source_session_id=trusted['session_id'],issue_id=trusted['issue_id'],binding=trusted['binding'],
        parent_handoff_id=trusted['parent_handoff_id'],depth=trusted['depth']+1,
        summary=clean['summary'],requested_action=clean['requested_action'],references=clean['references'],limitations=clean['limitations'],
        execution_authority_granted=False,human_approval_inferred=False)
    # Comment creation accepts a client UUID; native session creation does not.
    result['comment_id']=stable_uuid(dict(handoff_id=result['id'],purpose='source-attributed-context-comment'))
    if len(encoded(result))>32768:raise ValueError('handoff exceeds bounded transport')
    return result


def comment_body(intent):
    # Deliberately no @mention: the recipient credential explicitly creates its
    # own native session, once, after the source runtime is known quiescent.
    literal=lambda value:re.sub(r'([\\`*_{}\[\]<>()#!|~])',r'\\\1',value.replace('@','＠'))
    return ('Engineering handoff '+intent['id']+'\n\n'+intent['sender'].title()+' → '+intent['recipient'].title()+
        '\n\n'+literal(intent['summary'])+'\n\nRequested action: '+literal(intent['requested_action'])+
        '\n\nPinned engineering context:\n```json\n'+json.dumps(intent['binding'],sort_keys=True,indent=2,ensure_ascii=False)+'\n```\n\n'+
        'Evidence references:\n```json\n'+json.dumps(intent['references'],sort_keys=True,indent=2,ensure_ascii=False)+'\n```\n\n'+
        'Known limitations: '+literal(json.dumps(intent['limitations'],ensure_ascii=False))+
        '\n\nThis handoff supplies context and responsibility. It grants no new execution, spending, architecture approval, merge or deployment permission.').replace('@','＠')


VIEWER='query NativeHandoffViewer {viewer{id organization{id}}}'
COMMENT='mutation NativeHandoffComment($input:CommentCreateInput!){commentCreate(input:$input){success comment{id}}}'
SESSION='mutation NativeHandoffSession($input:AgentSessionCreateOnComment!){agentSessionCreateOnComment(input:$input){success agentSession{id}}}'
READ_COMMENT='query NativeHandoffReadComment($id:String!){comment(id:$id){id body user{id} issue{id} agentSessions(first:50){nodes{id appUser{id} issue{id}} pageInfo{hasNextPage endCursor}}}}'
READ_SESSION='query NativeHandoffReadSession($id:String!){viewer{id organization{id}} agentSession(id:$id){id appUser{id} issue{id} creator{id app} comment{id user{id app}} sourceComment{id user{id app}}}}'


def viewer(response,intent,role):
    body=response.get('body',{})
    return (response.get('statusCode')==200 and not body.get('errors') and body.get('data',{}).get('viewer')==
        dict(id=intent['sender_app_user_id'] if role=='sender' else intent['recipient_app_user_id'],organization=dict(id=intent['organization_id'])))


def mutation(intent,stage):
    if stage=='comment':return dict(query=COMMENT,variables=dict(input=dict(id=intent['comment_id'],issueId=intent['issue_id'],body=comment_body(intent))))
    if stage=='session':return dict(query=SESSION,variables=dict(input=dict(commentId=intent['comment_id'])))
    raise ValueError('one native handoff mutation stage required')


def confirm_comment(intent,response):
    body=response.get('body',{});value=body.get('data',{}).get('comment')
    if (response.get('statusCode')!=200 or body.get('errors') or type(value) is not dict or
            value.get('id')!=intent['comment_id'] or value.get('body')!=comment_body(intent) or
            value.get('user',{}).get('id')!=intent['sender_app_user_id'] or value.get('issue',{}).get('id')!=intent['issue_id']):
        raise ValueError('exact source-attributed handoff comment unconfirmed')
    return value


def reconcile_session(intent,response):
    comment=confirm_comment(intent,response);page=comment.get('agentSessions',{})
    if page.get('pageInfo',{}).get('hasNextPage') is not False or type(page.get('nodes')) is not list or len(page['nodes'])>50:
        raise ValueError('bounded complete native session page required')
    sessions=[s for s in page['nodes'] if s.get('appUser',{}).get('id')==intent['recipient_app_user_id']]
    if len(sessions)!=1 or sessions[0].get('issue',{}).get('id')!=intent['issue_id']:
        raise ValueError('unique recipient session unconfirmed; never blindly repeat creation')
    return identifier(sessions[0]['id'])


def correlate(intent,event):
    """Only verified ingress/native-read observations may call this function."""
    session=event.get('agentSession',{});issue=session.get('issue',{}).get('id') or session.get('issueId')
    comments={x for x in (session.get('sourceCommentId'),session.get('commentId'),
        (session.get('sourceComment') or {}).get('id'),(session.get('comment') or {}).get('id')) if x}
    if (event.get('type')!='AgentSessionEvent' or event.get('action')!='created' or
            event.get('organizationId')!=intent['organization_id'] or issue!=intent['issue_id'] or
            session.get('appUserId',event.get('appUserId'))!=intent['recipient_app_user_id'] or
            intent['comment_id'] not in comments):raise ValueError('uncorrelated native handoff; no execution admitted')
    return identifier(session['id'])
