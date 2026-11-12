"""Durable create-once coordination for a Linear draft issue.

The connection and callbacks are trusted infrastructure. In particular,
`create` performs the configured Linear mutation, and `verify` independently
reads and validates the returned issue. This module does not authenticate an
agent, choose a Linear project, or enable engineering execution.
"""
import hashlib
import json
import re
import sqlite3
import uuid


def canonical(value):
    if type(value) is not str:
        raise ValueError('canonical UUID required')
    try:
        if str(uuid.UUID(value)) != value: raise ValueError()
    except (ValueError, AttributeError):
        raise ValueError('canonical UUID required') from None
    return value


def digest(value):
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    if len(raw)>65536:raise ValueError('bounded issue proposal required')
    return hashlib.sha256(raw).hexdigest()


class IssueJournal:
    def __init__(self,connection):
        self.connection=connection

    @staticmethod
    def initialize(db):
        db.execute('CREATE TABLE issue_creation (organization_id TEXT NOT NULL, project_id TEXT NOT NULL, '
                   'plan_id TEXT NOT NULL, proposal_sha256 TEXT NOT NULL, state TEXT NOT NULL '
                   "CHECK(state IN ('creating','uncertain','complete')), issue_id TEXT, "
                   'PRIMARY KEY(organization_id,project_id,plan_id), UNIQUE(organization_id,issue_id))')
        db.commit()

    def create_once(self,origin,plan_id,proposal,create,verify):
        if type(origin) is not dict or set(origin)!={'organization_id','project_id','team_id'}:
            raise ValueError('trusted project identity required')
        org=canonical(origin['organization_id']);project=canonical(origin['project_id']);team=canonical(origin['team_id'])
        if type(plan_id) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',plan_id):
            raise ValueError('plan identity required')
        if type(proposal) is not dict or not callable(create) or not callable(verify):
            raise ValueError('issue proposal and trusted callbacks required')
        sha=digest(dict(team_id=team,proposal=proposal));key=(org,project,plan_id)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT proposal_sha256,state,issue_id FROM issue_creation WHERE organization_id=? AND project_id=? AND plan_id=?',key).fetchone()
            if row:
                if row[0]!=sha:raise ValueError('issue proposal differs; reconcile explicitly')
                if row[1]=='complete':return dict(state='complete',issue_id=row[2],created=False)
                return dict(state='uncertain',issue_id=None,created=False)
            db.execute('INSERT INTO issue_creation VALUES(?,?,?,?,?,NULL)',(*key,sha,'creating'))
            db.commit()
        try:
            candidate=canonical(create(proposal))
            verified=verify(candidate)
            if type(verified) is not dict or verified.get('id')!=candidate or verified.get('organization_id')!=org or verified.get('project_id')!=project or verified.get('team_id')!=team:
                raise ValueError('created Linear issue could not be verified')
        except Exception:
            with self.connection() as db:
                db.execute("UPDATE issue_creation SET state='uncertain' WHERE organization_id=? AND project_id=? AND plan_id=? AND state='creating'",key)
                db.commit()
            return dict(state='uncertain',issue_id=None,created=False)
        try:
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                changed=db.execute("UPDATE issue_creation SET state='complete',issue_id=? WHERE organization_id=? AND project_id=? AND plan_id=? AND state='creating' AND proposal_sha256=?",(candidate,*key,sha)).rowcount
                if changed!=1:raise ValueError('issue creation outcome uncertain')
                db.commit()
        except sqlite3.IntegrityError:
            return dict(state='uncertain',issue_id=None,created=False)
        return dict(state='complete',issue_id=candidate,created=True)

    def reconcile(self,origin,plan_id,proposal,issue_id,verify):
        """Bind one independently verified result after an uncertain creation.

        `verify` must establish the issue's project and exact planning identity
        from a trusted source; a model-authored issue label is not sufficient.
        No additional issue is created here.
        """
        if type(origin) is not dict or set(origin)!={'organization_id','project_id','team_id'}:
            raise ValueError('trusted project identity required')
        org=canonical(origin['organization_id']);project=canonical(origin['project_id']);team=canonical(origin['team_id']);candidate=canonical(issue_id)
        if type(plan_id) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',plan_id):
            raise ValueError('plan identity required')
        if type(proposal) is not dict or not callable(verify):raise ValueError('trusted reconciliation required')
        sha=digest(dict(team_id=team,proposal=proposal));key=(org,project,plan_id)
        verified=verify(candidate,plan_id,sha)
        if verified is not True:raise ValueError('issue reconciliation could not be verified')
        try:
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT proposal_sha256,state,issue_id FROM issue_creation WHERE organization_id=? AND project_id=? AND plan_id=?',key).fetchone()
                if row is None or row[0]!=sha:raise ValueError('issue proposal differs; reconcile explicitly')
                if row[1]=='complete':
                    if row[2]!=candidate:raise ValueError('issue identity differs')
                    return dict(state='complete',issue_id=candidate,reconciled=False)
                if row[1]!='uncertain':raise ValueError('issue creation may still be active')
                db.execute("UPDATE issue_creation SET state='complete',issue_id=? WHERE organization_id=? AND project_id=? AND plan_id=?",(candidate,*key))
                db.commit()
        except sqlite3.IntegrityError:
            raise ValueError('issue identity already bound') from None
        return dict(state='complete',issue_id=candidate,reconciled=True)
