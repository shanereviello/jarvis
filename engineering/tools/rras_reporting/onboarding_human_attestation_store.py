"""Operator-authenticated attestations for otherwise ambiguous authorship.

This is an operator-side primitive, not an HTTP handler or a deployed UI. The
caller must supply the existing cryptographic Cloudflare Access verifier and a
native decision verifier configured to validate everything except authorship.
A trusted browser endpoint must enforce same-origin requests and call these
methods only after presenting the exact decision and attestation wording.
"""
import hashlib
import hmac
import json
import secrets
import threading
import time


def digest(comment,review):
    raw=json.dumps({'comment':comment,'review':review},sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    if len(raw)>131072:raise ValueError('bounded attestation required')
    return hashlib.sha256(raw).hexdigest()


class Store:
    def __init__(self,connection,access,read_comment,read_review,validate_source,clock=time.monotonic):
        if not all(callable(x) for x in (connection,read_comment,read_review,validate_source,clock)) or not callable(getattr(access,'verify',None)):
            raise ValueError('protected attestation readers and authentication required')
        self.connection,self.access,self.read_comment,self.read_review,self.validate_source=connection,access,read_comment,read_review,validate_source
        self.clock=clock;self.pending={};self.lock=threading.Lock()

    @staticmethod
    def initialize(db):
        db.execute('CREATE TABLE human_authorship_attestations (proof_sha256 TEXT NOT NULL, review_id TEXT NOT NULL, comment_id TEXT NOT NULL, '
                   'human_actor_id TEXT NOT NULL, operator_subject TEXT NOT NULL, operator_email TEXT NOT NULL, confirmed_at TEXT NOT NULL, PRIMARY KEY(proof_sha256,operator_email))')
        db.execute("CREATE TRIGGER authorship_no_update BEFORE UPDATE ON human_authorship_attestations BEGIN SELECT RAISE(ABORT,'immutable attestation'); END")
        db.execute("CREATE TRIGGER authorship_no_delete BEFORE DELETE ON human_authorship_attestations BEGIN SELECT RAISE(ABORT,'immutable attestation'); END")
        db.commit()

    def authenticate(self,headers):
        # Access.verify permits omitted Origin on safe GETs. Attestation is a
        # state-changing request and requires exactly one same-origin header.
        origins=[v for k,v in headers if k.lower()==b'origin']
        if len(origins)!=1 or origins[0]!=self.access.config.origin.encode('ascii'):
            raise ValueError('same-origin operator request required')
        identity=self.access.verify(headers)
        if type(identity) is not dict or set(identity)!={'email','subject'} or not identity['email'] or not identity['subject']:
            raise ValueError('authenticated operator required')
        return identity

    def load(self,review_id,comment_id):
        review=self.read_review(review_id);response=self.read_comment(comment_id)
        if type(response) is not dict or type(response.get('comment')) is not dict:raise ValueError('native comment unavailable')
        comment=response['comment']
        verified=self.validate_source({'review_id':review_id,'comment_id':comment_id})
        if (type(verified) is not dict or verified['source_id']!=comment_id or
                verified['human_actor_id']!=comment['author_id'] or verified['decision_text']!=comment['body']):
            raise ValueError('source differs during attestation')
        return comment,review,verified

    def begin(self,headers,review_id,comment_id):
        identity=self.authenticate(headers)
        comment,review,verified=self.load(review_id,comment_id)
        proof=digest(comment,review);now=self.clock()
        with self.lock:
            self.pending={k:v for k,v in self.pending.items() if v['expires']>now}
            if len(self.pending)>=256:raise ValueError('attestation requests temporarily unavailable')
            nonce=secrets.token_urlsafe(32)
            self.pending[nonce]=dict(subject=identity['subject'],email=identity['email'],review_id=review_id,comment_id=comment_id,
                                     proof=proof,expires=now+300)
        return dict(challenge=nonce,linear_project_id=review['linear_project_id'],issue_id=review['issue_id'],
                    project_id=review['project_id'],version=review['version'],markdown_sha256=review['markdown_sha256'],
                    source_text=comment['body'],human_actor_id=verified['human_actor_id'],expires_in_seconds=300)

    def confirm(self,headers,challenge,statement):
        identity=self.authenticate(headers)
        if type(challenge) is not str or statement!='I confirm I personally authored this exact Linear approval.':
            raise ValueError('explicit authorship attestation required')
        from datetime import datetime,timezone
        confirmed_at=datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
        with self.lock:
            pending=self.pending.pop(challenge,None)
        if (pending is None or pending['expires']<=self.clock() or identity['subject']!=pending['subject'] or
                identity['email']!=pending['email']):raise ValueError('expired or mismatched operator challenge')
        comment,review,verified=self.load(pending['review_id'],pending['comment_id'])
        proof=digest(comment,review)
        if not hmac.compare_digest(proof,pending['proof']):raise ValueError('decision changed after review')
        row=(proof,pending['review_id'],pending['comment_id'],verified['human_actor_id'],identity['subject'],identity['email'],confirmed_at)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT review_id,comment_id,human_actor_id,operator_subject,operator_email FROM human_authorship_attestations WHERE proof_sha256=? AND operator_email=?',(proof,identity['email'])).fetchone()
            if old is None:db.execute('INSERT INTO human_authorship_attestations VALUES(?,?,?,?,?,?,?)',row)
            elif old!=row[1:6]:raise ValueError('conflicting authorship attestation')
            db.commit()
        return {'attested':True,'proof_sha256':proof,'execution_authorized':False}

    def verify_authorship(self,comment,review):
        proof=digest(comment,review)
        with self.connection() as db:
            row=db.execute('SELECT human_actor_id,operator_email FROM human_authorship_attestations WHERE proof_sha256=? AND operator_email=?',(proof,self.access.config.email)).fetchone()
        return row is not None and row[0]==comment.get('author_id') and row[1]==self.access.config.email
