"""Immutable operator-side review references, with no approval authority.

The database connection and history/issue readers belong to a protected
operator process, not to the planning agent. A review reference simply pins the
proposal and native issue used to solicit a future human decision.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid


def local(name):
    spec=importlib.util.spec_from_file_location('review_store_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class ReviewStore:
    def __init__(self,connection,history,read_issue,allowed_scopes):
        if not callable(connection) or not callable(read_issue) or not allowed_scopes:
            raise ValueError('protected review storage and native readers required')
        self.connection,self.history,self.read_issue=connection,history,read_issue
        self.scopes=[local('onboarding_drafts').selected_scope(s) for s in allowed_scopes]

    @staticmethod
    def initialize(db):
        db.execute('CREATE TABLE architecture_reviews (review_id TEXT PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL)')
        db.execute("CREATE TRIGGER architecture_reviews_no_update BEFORE UPDATE ON architecture_reviews BEGIN SELECT RAISE(ABORT,'immutable review'); END")
        db.execute("CREATE TRIGGER architecture_reviews_no_delete BEFORE DELETE ON architecture_reviews BEGIN SELECT RAISE(ABORT,'immutable review'); END")
        db.commit()

    def prepare(self,origin,issue_id,version):
        d=local('onboarding_drafts');origin=d.verified(origin);d.identifier(issue_id)
        if origin['scope'] not in self.scopes:raise ValueError('review scope refused')
        if type(version) is not int or version<1:raise ValueError('exact draft version required')
        issue=self.read_issue(issue_id)
        keys={'organization_id','team_id','project_id','id'}
        if type(issue) is not dict or set(issue)!=keys or issue['id']!=issue_id or any(issue[k]!=origin[k] for k in ('organization_id','team_id','project_id')):
            raise ValueError('verified review issue required')
        project_id=d.identity('prj_',origin['organization_id'],origin['project_id'])
        document_id=d.identity('doc_',origin['organization_id'],origin['project_id'])
        project=self.history.project(origin['scope'],project_id)
        if project is None or project['scope']!=origin['scope']:raise ValueError('retained project unavailable')
        rows=[row for row in project['architecture'] if row['document_id']==document_id and row['version']==version]
        if len(rows)!=1:raise ValueError('exact retained architecture required')
        document=self.history.architecture(origin['scope'],project_id,version)
        markdown=document['markdown'];sha=hashlib.sha256(markdown.encode('utf-8')).hexdigest()
        if rows[0]['markdown_sha256']!=sha:raise ValueError('retained architecture digest differs')
        value=dict(organization_id=origin['organization_id'],linear_project_id=origin['project_id'],team_id=origin['team_id'],issue_id=issue_id,
            scope=origin['scope'],project_id=project_id,document_id=document_id,version=version,markdown_sha256=sha,
            expected_governing_version=project['governing_version'],expected_project_head=project['head'])
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
        digest=hashlib.sha256(raw.encode('utf-8')).hexdigest()
        review_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rras-architecture-review-v1:'+digest))
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT payload,sha256 FROM architecture_reviews WHERE review_id=?',(review_id,)).fetchone()
            if old is None:db.execute('INSERT INTO architecture_reviews VALUES(?,?,?)',(review_id,raw,digest))
            elif old!=(raw,digest):raise ValueError('review identity conflict')
            db.commit()
        return review_id

    def read(self,review_id):
        local('onboarding_drafts').identifier(review_id)
        with self.connection() as db:row=db.execute('SELECT payload,sha256 FROM architecture_reviews WHERE review_id=?',(review_id,)).fetchone()
        if row is None or hashlib.sha256(row[0].encode('utf-8')).hexdigest()!=row[1]:raise ValueError('review unavailable or corrupt')
        return json.loads(row[0])
