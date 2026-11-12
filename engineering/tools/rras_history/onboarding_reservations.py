"""Explicit additive v5-to-v6 reservation store for Linear project identities.

This internal module does not expose a transport, authenticate an agent, or
authorize work. Callers must enforce peer, actor, workspace and scope grants.
"""
import hashlib
import importlib.util
from pathlib import Path
import re
import uuid


DDL=(
    '''CREATE TABLE onboarding_reservations(
       organization_id TEXT NOT NULL,linear_project_id TEXT NOT NULL,team_id TEXT NOT NULL,
       project_id TEXT NOT NULL UNIQUE,scope_kind TEXT NOT NULL,scope_id TEXT NOT NULL,
       PRIMARY KEY(organization_id,linear_project_id))''',
    "CREATE TRIGGER onboarding_reservation_no_update BEFORE UPDATE ON onboarding_reservations BEGIN SELECT RAISE(ABORT,'immutable onboarding reservation'); END",
    "CREATE TRIGGER onboarding_reservation_no_delete BEFORE DELETE ON onboarding_reservations BEGIN SELECT RAISE(ABORT,'immutable onboarding reservation'); END",
    '''CREATE TABLE onboarding_work_reservations(
       organization_id TEXT NOT NULL,linear_issue_id TEXT NOT NULL,linear_project_id TEXT NOT NULL,
       team_id TEXT NOT NULL,project_id TEXT NOT NULL,plan_id TEXT NOT NULL,work_id TEXT NOT NULL UNIQUE,
       scope_kind TEXT NOT NULL,scope_id TEXT NOT NULL,PRIMARY KEY(organization_id,linear_issue_id),
       UNIQUE(project_id,plan_id))''',
    "CREATE TRIGGER onboarding_work_reservation_no_update BEFORE UPDATE ON onboarding_work_reservations BEGIN SELECT RAISE(ABORT,'immutable onboarding work reservation'); END",
    "CREATE TRIGGER onboarding_work_reservation_no_delete BEFORE DELETE ON onboarding_work_reservations BEGIN SELECT RAISE(ABORT,'immutable onboarding work reservation'); END",
)


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_reservation_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def canonical(value):
    try:
        if type(value) is not str or str(uuid.UUID(value))!=value:raise ValueError('UUID required')
    except (ValueError,AttributeError):raise ValueError('canonical Linear identity required') from None
    return value


class Reservations:
    def __init__(self,store):self.store=store;self.c=local('contract')

    def fingerprint(self,db):
        digest=hashlib.sha256();tables=[]
        for row in db.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"):
            digest.update(self.c.encoded(list(row)))
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('unsupported table name')
            count=0
            for row in db.execute('SELECT * FROM "'+name+'" ORDER BY rowid'):
                digest.update(self.c.encoded([{'bytes':x.hex()} if isinstance(x,bytes) else x for x in row]));count+=1
            tables.append(dict(name=name,count=count))
        digest.update(self.c.encoded(DDL))
        return dict(contract='engineering-onboarding-migration.v1',from_version=5,to_version=6,
                    expected_sha256=digest.hexdigest(),tables=tables,authority_granted=False,
                    changes='add immutable project identity reservations; preserve prior history and snapshots')

    def migration_plan(self):
        with self.store.connection() as db:
            db.execute('BEGIN')
            if db.execute('PRAGMA user_version').fetchone()[0]!=5 or db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise ValueError('intact schema-5 store required')
            return self.fingerprint(db)

    def migrate(self,expected_sha256):
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0]!=5 or db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise ValueError('intact schema-5 store required')
            plan=self.fingerprint(db)
            if plan['expected_sha256']!=expected_sha256:raise ValueError('exact migration plan required')
            for statement in DDL:db.execute(statement)
            db.execute('PRAGMA user_version=6');db.commit()
        self.store.sync();return dict(plan,migrated=True)

    def reserve(self,organization_id,linear_project_id,team_id,project_id,scope):
        for value in (organization_id,linear_project_id,team_id):canonical(value)
        if type(project_id) is not str or not re.fullmatch('prj_[0-9a-f]{32}',project_id):
            raise ValueError('exact project identity required')
        scope=local('projects').scope(scope)
        expected=(team_id,project_id,scope['kind'],scope['id'])
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0]!=6:raise ValueError('explicit reservation upgrade required')
            prior=db.execute('SELECT team_id,project_id,scope_kind,scope_id FROM onboarding_reservations '
                             'WHERE organization_id=? AND linear_project_id=?',(organization_id,linear_project_id)).fetchone()
            if prior is not None:
                if tuple(prior)!=expected:raise ValueError('planning binding unavailable')
                return dict(inserted=False,project_id=project_id,authority_granted=False)
            if db.execute('SELECT 1 FROM onboarding_reservations WHERE project_id=?',(project_id,)).fetchone():
                raise ValueError('planning binding unavailable')
            reporting=local('reporting').Reporting(self.store);events=reporting.events(db);latest={}
            for request,receipt in events:
                if request['operation']=='mapping.record':latest[reporting.entity(request)]=request
            matched_existing=False
            for request in latest.values():
                if request['body']['kind']!='project':continue
                linear=request['body']['linear'];ctx=request['context']
                same_linear=(linear['organization_id'],linear['project_id'])==(organization_id,linear_project_id)
                same_project=ctx['project_id']==project_id
                if (same_linear or same_project) and (not same_linear or not same_project or
                    linear['team_id']!=team_id or request['scope']!=scope):
                    raise ValueError('planning binding unavailable')
                if same_linear and same_project:matched_existing=True
            projects,_=local('projects').Projects(self.store).replay(local('projects').Projects(self.store).events(db))
            if project_id in projects and (projects[project_id]['scope']!=scope or not matched_existing):
                raise ValueError('planning binding unavailable')
            if db.execute('SELECT count(*) FROM onboarding_reservations').fetchone()[0]>=10000:
                raise ValueError('planning reservation capacity reached')
            db.execute('INSERT INTO onboarding_reservations VALUES(?,?,?,?,?,?)',
                       (organization_id,linear_project_id,team_id,project_id,scope['kind'],scope['id']))
            db.commit()
        self.store.sync();return dict(inserted=True,project_id=project_id,authority_granted=False)

    def reserve_work(self,organization_id,linear_project_id,team_id,project_id,scope,plan_id,linear_issue_id,work_id):
        for value in (organization_id,linear_project_id,team_id,linear_issue_id):canonical(value)
        if (type(project_id) is not str or not re.fullmatch('prj_[0-9a-f]{32}',project_id) or
                type(work_id) is not str or not re.fullmatch('wrk_[0-9a-f]{32}',work_id) or
                type(plan_id) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',plan_id)):
            raise ValueError('exact project, plan and work identity required')
        scope=local('projects').scope(scope)
        expected=(linear_project_id,team_id,project_id,plan_id,work_id,scope['kind'],scope['id'])
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0]!=6:raise ValueError('explicit reservation upgrade required')
            parent=db.execute('SELECT team_id,project_id,scope_kind,scope_id FROM onboarding_reservations '
                              'WHERE organization_id=? AND linear_project_id=?',(organization_id,linear_project_id)).fetchone()
            if parent is None or tuple(parent)!=(team_id,project_id,scope['kind'],scope['id']):
                raise ValueError('planning binding unavailable')
            prior=db.execute('SELECT linear_project_id,team_id,project_id,plan_id,work_id,scope_kind,scope_id '
                             'FROM onboarding_work_reservations WHERE organization_id=? AND linear_issue_id=?',
                             (organization_id,linear_issue_id)).fetchone()
            if prior is not None:
                if tuple(prior)!=expected:raise ValueError('planning binding unavailable')
                return dict(inserted=False,work_id=work_id,authority_granted=False)
            if db.execute('SELECT 1 FROM onboarding_work_reservations WHERE (project_id=? AND plan_id=?) OR work_id=?',
                          (project_id,plan_id,work_id)).fetchone():
                raise ValueError('planning binding unavailable')
            reporting=local('reporting').Reporting(self.store);latest={}
            for request,receipt in reporting.events(db):
                if request['operation']=='mapping.record':latest[reporting.entity(request)]=request
            matched_existing=False
            for request in latest.values():
                if request['body']['kind']!='execution':continue
                linear=request['body']['linear'];ctx=request['context'];work=ctx['work']
                same_issue=(linear['organization_id'],linear['issue_id'])==(organization_id,linear_issue_id)
                same_plan=(ctx['project_id'],request['body']['plan_id'])==(project_id,plan_id)
                same_work=work['work_item_id']==work_id
                if (same_issue or same_plan or same_work) and (not (same_issue and same_plan and same_work) or
                    (linear['project_id'],linear['team_id'])!=(linear_project_id,team_id) or request['scope']!=scope):
                    raise ValueError('planning binding unavailable')
                if same_issue and same_plan and same_work:matched_existing=True
            existing=[r for r,_,_,_ in self.store.rows(db) if r['operation'].startswith('work.') and r['body']['work_item_id']==work_id]
            if existing and not matched_existing:raise ValueError('planning binding unavailable')
            if db.execute('SELECT count(*) FROM onboarding_work_reservations').fetchone()[0]>=100000:
                raise ValueError('planning reservation capacity reached')
            db.execute('INSERT INTO onboarding_work_reservations VALUES(?,?,?,?,?,?,?,?,?)',
                       (organization_id,linear_issue_id,linear_project_id,team_id,project_id,plan_id,work_id,scope['kind'],scope['id']))
            db.commit()
        self.store.sync();return dict(inserted=True,work_id=work_id,authority_granted=False)
