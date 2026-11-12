"""Offline, audited one-issue policy admission; never installs or starts a model.

The protected caller must stop the runtime, hold the operator admission lock,
independently recheck external evidence and execution authority, and coordinate
protected on-disk policy replacement/recovery separately. A journal update is
not itself a production deployment or permission to spend.
"""
import hashlib
import importlib.util
import json
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('issue_admission_migration_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def snapshot(db,request,verify,verify_authority):
    runtime=local('codex_runtime');migration=local('codex_policy_migration')
    rows=db.execute('SELECT body FROM policy').fetchall()
    if len(rows)!=1:raise ValueError('one existing runtime policy required')
    current=runtime.policy(json.loads(rows[0][0]));migration.settled(db)
    result=local('onboarding_admission').candidate(current,request,verify,verify_authority)
    candidate=result['policy']
    # The builder may add only this issue and its dedicated paths; all other
    # runtime and spending settings must remain byte-for-byte equivalent.
    for key in set(current)-{'issues','workspaces','native_sockets'}:
        if current[key]!=candidate[key]:raise ValueError('unrelated runtime policy changed')
    for key in ('issues','workspaces','native_sockets'):
        if any(candidate[key].get(k)!=v for k,v in current[key].items()):raise ValueError('existing issue policy changed')
        if set(candidate[key])-set(current[key])!={request['issue_id']}:raise ValueError('exactly one new issue required')
    prior=[]
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='policy_issue_admissions'").fetchone():
        prior=[row[0] for row in db.execute('SELECT plan_sha256 FROM policy_issue_admissions ORDER BY sequence')]
    value=dict(contract='codex-issue-admission-plan.v1',issue_id=request['issue_id'],
        old_policy_sha256=hashlib.sha256(runtime.encoded(current)).hexdigest(),
        new_policy_sha256=hashlib.sha256(runtime.encoded(candidate)).hexdigest(),
        evidence_sha256=hashlib.sha256(runtime.encoded(request)).hexdigest(),authority=result['authority'],tables=migration.fingerprints(db),
        prior_admissions=prior,models_started=0,policy_installed=False)
    return value,current,candidate


def plan(root,request,verify,verify_authority):
    migration=local('codex_policy_migration')
    with migration.locked(root) as db:
        value,_,_=snapshot(db,request,verify,verify_authority)
        value['expected_sha256']=hashlib.sha256(local('codex_runtime').encoded(value)).hexdigest()
        return value


def apply(root,request,verify,verify_authority,expected_sha256):
    runtime=local('codex_runtime');migration=local('codex_policy_migration')
    with migration.locked(root) as db:
        value,old,new=snapshot(db,request,verify,verify_authority)
        digest=hashlib.sha256(runtime.encoded(value)).hexdigest()
        if digest!=expected_sha256:raise ValueError('admission plan differs; reconcile before retry')
        db.execute('CREATE TABLE IF NOT EXISTS policy_issue_admissions(sequence INTEGER PRIMARY KEY,issue_id TEXT NOT NULL UNIQUE, '
                   'old_body BLOB NOT NULL,new_body BLOB NOT NULL,evidence_sha256 TEXT NOT NULL,authority_body BLOB NOT NULL,plan_sha256 TEXT NOT NULL)')
        for operation in ('UPDATE','DELETE'):
            db.execute('CREATE TRIGGER IF NOT EXISTS retain_issue_admissions_'+operation.lower()+' BEFORE '+operation+
                       " ON policy_issue_admissions BEGIN SELECT RAISE(ABORT,'retained issue admission evidence'); END")
        db.execute('INSERT INTO policy_issue_admissions(issue_id,old_body,new_body,evidence_sha256,authority_body,plan_sha256) VALUES(?,?,?,?,?,?)',
                   (request['issue_id'],runtime.encoded(old),runtime.encoded(new),value['evidence_sha256'],runtime.encoded(value['authority']),digest))
        db.execute('UPDATE policy SET body=?',(runtime.encoded(new),))
        return dict(journal_updated=True,issue_id=request['issue_id'],plan_sha256=digest,policy_installed=False,models_started=0)


def reconcile(root,request,expected_sha256):
    """Read retained outcome after a lost response; never submit it again."""
    runtime=local('codex_runtime');migration=local('codex_policy_migration')
    with migration.locked(root) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='policy_issue_admissions'").fetchone():
            raise ValueError('no retained admission outcome')
        rows=db.execute('SELECT new_body,evidence_sha256,plan_sha256 FROM policy_issue_admissions WHERE issue_id=?',(request['issue_id'],)).fetchall()
        if len(rows)!=1 or rows[0][2]!=expected_sha256 or rows[0][1]!=hashlib.sha256(runtime.encoded(request)).hexdigest():
            raise ValueError('exact retained admission unavailable')
        retained=runtime.policy(json.loads(rows[0][0]));current_rows=db.execute('SELECT body FROM policy').fetchall()
        if len(current_rows)!=1:raise ValueError('runtime policy unavailable')
        current=runtime.policy(json.loads(current_rows[0][0]));issue=request['issue_id']
        pins_match=all(current[key].get(issue)==retained[key].get(issue) for key in ('issues','workspaces','native_sockets'))
        return dict(retained=True,issue_id=issue,plan_sha256=expected_sha256,current_issue_pins_match=pins_match,
                    current_policy_matches=(current==retained),policy_installed=False,models_started=0)
