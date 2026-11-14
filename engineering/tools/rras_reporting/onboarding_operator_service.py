"""Source-only protected composition for review and operator attestation.

Hosting, dedicated OS identities, access policy, sockets, credentials and live
routes must be installed and verified separately. This module does not start a
listener or grant authority to a planning agent.
"""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('operator_service_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def initialize_empty(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
        raise ValueError('new private operator journal required')
    local('onboarding_review_store').ReviewStore.initialize(db)
    local('onboarding_human_attestation_store').Store.initialize(db)


class Browser:
    def __init__(self,attestations,coordinator):self.attestations,self.coordinator=attestations,coordinator
    def begin(self,headers,review_id,comment_id):return self.attestations.begin(headers,review_id,comment_id)
    def confirm(self,headers,challenge,statement):
        result=self.attestations.confirm(headers,challenge,statement)
        # Attestation commits first; if designation fails, its exact immutable
        # evidence remains for operator-visible reconciliation and no coding is
        # admitted. It must never be silently retried as a model turn.
        decision=self.coordinator.approve(dict(review_id=result['review_id'],comment_id=result['comment_id']))
        return dict(attested=True,decision_recorded=True,project_id=decision['project_id'],version=decision['version'],
                    decision_receipt_sha256=decision['decision_receipt_sha256'],execution_authorized=False)


def assemble(config,connection,access,planning_reader,comment_transport,history_rpc):
    fields={'organization_id','app_user_id','team_id','human_ids','planning_peer_uid','scopes'}
    if type(config) is not dict or set(config)!=fields:raise ValueError('exact operator service configuration required')
    d=local('onboarding_drafts')
    for name in ('organization_id','app_user_id','team_id'):d.identifier(config[name])
    peer=config['planning_peer_uid']
    if type(peer) is not int or peer<1:raise ValueError('exact planning service identity required')
    if type(config['human_ids']) is not list or len(config['human_ids'])!=1:
        raise ValueError('one explicit operator-to-Linear human binding required')
    if not callable(connection) or not callable(history_rpc) or not callable(comment_transport) or not callable(getattr(access,'verify',None)):
        raise ValueError('protected operator service transports required')
    scopes=[d.selected_scope(x) for x in config['scopes']]
    if not scopes or len(scopes)>128 or len({(x['kind'],x['id']) for x in scopes})!=len(scopes):raise ValueError('distinct operator scopes required')
    history=local('onboarding_operator_history').Adapter(history_rpc,scopes)
    def issue(dispatch,origin,issue_id):return planning_reader.issue(dispatch,origin,issue_id)
    grants={peer:dict(agent='codex',organization_id=config['organization_id'],team_id=config['team_id'],scopes=scopes)}
    review_broker=local('onboarding_review_broker').Broker(grants,
        lambda uid,dispatch,issue_id:planning_reader.origin(dispatch,issue_id),issue,connection,history.reader,scopes)
    reviews=local('onboarding_review_store').ReviewStore(connection,history.reader,lambda _:None,scopes)
    comment_reader=local('onboarding_linear_comment_reader').Reader(comment_transport,config['app_user_id'],config['organization_id'])
    # This content-only validator is private to the challenge creator. It must
    # never be used directly by the decision recorder or exposed to the agent.
    preliminary=local('onboarding_linear_decision').Verifier(comment_reader,reviews.read,lambda *_:True,
        config['organization_id'],config['app_user_id'],config['human_ids'])
    attests=local('onboarding_human_attestation_store').Store(connection,access,comment_reader,reviews.read,preliminary.verify)
    decision_source=local('onboarding_linear_decision').Verifier(comment_reader,reviews.read,attests.verify_authorship,
        config['organization_id'],config['app_user_id'],config['human_ids'])
    recorder=local('onboarding_decisions').DecisionRecorder(decision_source.verify,history,scopes)
    coordinator=local('onboarding_operator_decision').Coordinator(recorder,reviews)
    browser=Browser(attests,coordinator)
    return dict(review_broker=review_broker,browser=browser,attestations=attests,reviews=reviews,
                decision_source=decision_source,history=history,production_active=False)
