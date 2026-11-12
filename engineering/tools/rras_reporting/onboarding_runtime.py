"""Read-only planning dispatch with durable uncertain-outcome handling.

The runtime uses trusted native-origin and session registries supplied by its
host process. It does not expose an HTTP endpoint or install any authority.
"""
import hashlib
import importlib.util
import json
import fcntl
import os
from pathlib import Path
import stat
import threading


def local(name):
    spec=importlib.util.spec_from_file_location('onboarding_runtime_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def encoded(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')


class Runtime:
    def __init__(self,connection,policy,verify_event,registry,launch,client_factory,clock,lock_path):
        required={'organization_id','app_user_id','peer_uid','cwd','planning_authorized','authority_reference'}
        if type(policy) is not dict or set(policy)!=required or not all(callable(x) for x in (verify_event,client_factory,clock)):
            raise ValueError('exact protected planning runtime policy required')
        d=local('onboarding_drafts');d.identifier(policy['organization_id']);d.identifier(policy['app_user_id'])
        if type(policy['peer_uid']) is not int or policy['peer_uid']<0 or type(policy['planning_authorized']) is not bool:
            raise ValueError('explicit planning authority required')
        d.text(policy['authority_reference'],4096)
        path=Path(policy['cwd']) if type(policy['cwd']) is str else Path('.')
        if not path.is_absolute() or path.resolve()!=path or path==Path('/') or not path.is_dir():
            raise ValueError('fixed canonical planning directory required')
        lock_path=Path(lock_path)
        if not lock_path.is_absolute() or lock_path.parent.resolve()!=lock_path.parent:
            raise ValueError('canonical private lock required')
        parent=lock_path.parent.stat()
        if parent.st_uid!=os.getuid() or stat.S_IMODE(parent.st_mode)&0o077:
            raise ValueError('private service-owned lock directory required')
        fd=os.open(lock_path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)&0o077:
                raise ValueError('private service-owned lock required')
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            os.close(fd);raise ValueError('planning journal already owned or lock unsafe') from None
        self.lock_fd=fd
        try:
            with connection() as db:
                db.execute('BEGIN IMMEDIATE')
                rows=db.execute('SELECT body FROM planning_policy').fetchall()
                if not rows:db.execute('INSERT INTO planning_policy(body) VALUES(?)',(encoded(policy),))
                elif len(rows)!=1 or rows[0][0]!=encoded(policy):raise ValueError('planning policy differs; explicit migration required')
                db.commit()
        except BaseException:
            os.close(fd);self.lock_fd=None;raise
        self.connection,self.policy,self.verify_event,self.registry=connection,dict(policy),verify_event,registry
        self.launch,self.client_factory,self.clock=launch,client_factory,clock
        self.clients={};self.lock=threading.Lock()
        try:self.recover_after_exclusive_start()
        except BaseException:
            os.close(fd);self.lock_fd=None;raise

    @staticmethod
    def initialize(db):
        db.executescript('CREATE TABLE planning_policy (body BLOB NOT NULL);'
            'CREATE TABLE planning_turns (dispatch TEXT PRIMARY KEY,session TEXT NOT NULL,issue TEXT NOT NULL, '
            'request BLOB NOT NULL,sha256 TEXT NOT NULL,state TEXT NOT NULL,thread TEXT,turn TEXT,result TEXT);'
            "CREATE UNIQUE INDEX planning_single_active ON planning_turns((1)) WHERE state IN ('preparing','running','uncertain','interrupt_requested');")
        db.commit()

    def dispatch(self,event):
        if self.lock_fd is None:raise ValueError('exclusive planning lock required')
        fields={'dispatch_id','session_id','issue_id','organization_id','app_user_id','message'}
        if type(event) is not dict or set(event)!=fields:raise ValueError('exact planning dispatch required')
        d=local('onboarding_drafts')
        for key in fields-{'message'}:d.identifier(event[key])
        d.text(event['message'],65536)
        if (event['organization_id']!=self.policy['organization_id'] or event['app_user_id']!=self.policy['app_user_id'] or
                not self.policy['planning_authorized']):raise ValueError('planning execution not authorized')
        # This callback must independently verify the native app, human,
        # session, issue, project and configured scope for the exact dispatch.
        if self.verify_event(dict(event)) is not True:raise ValueError('native planning origin unconfirmed')
        raw=encoded(event)
        if len(raw)>128*1024:raise ValueError('bounded dispatch required')
        sha=hashlib.sha256(raw).hexdigest();dispatch=event['dispatch_id']
        with self.lock:
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                policies=db.execute('SELECT body FROM planning_policy').fetchall()
                if len(policies)!=1 or policies[0][0]!=encoded(self.policy):raise ValueError('planning policy differs')
                prior=db.execute('SELECT sha256,state,thread,turn FROM planning_turns WHERE dispatch=?',(dispatch,)).fetchone()
                if prior:
                    if prior[0]!=sha:raise ValueError('dispatch identity changed')
                    return dict(dispatch=dispatch,state=prior[1],thread=prior[2],turn=prior[3],replayed=True)
                session=db.execute('SELECT issue,thread FROM planning_turns WHERE session=? ORDER BY rowid DESC LIMIT 1',
                                   (event['session_id'],)).fetchone()
                if session and session[0]!=event['issue_id']:raise ValueError('planning session issue changed')
                db.execute('INSERT INTO planning_turns(dispatch,session,issue,request,sha256,state) VALUES(?,?,?,?,?,?)',
                    (dispatch,event['session_id'],event['issue_id'],raw,sha,'preparing'))
                db.commit()
            try:
                self.registry.register(self.policy['peer_uid'],dispatch,int(self.clock())+1800)
                client=self.client_factory();self.clients[dispatch]=client
                options=dict(cwd=self.policy['cwd'],sandbox='read-only',approvalPolicy='never',**self.launch.parameters(dispatch))
                if session and session[1]:
                    opened=client.call('thread/resume',dict(threadId=session[1],**options))
                else:opened=client.call('thread/start',dict(ephemeral=False,**options))
                thread=d.text(opened['thread']['id'],256,single_line=True)
                if session and session[1] and thread!=session[1]:raise ValueError('planning thread changed')
                if opened['thread'].get('cwd',self.policy['cwd'])!=self.policy['cwd']:raise ValueError('planning directory differs')
                with self.connection() as db:
                    db.execute('UPDATE planning_turns SET thread=? WHERE dispatch=?',(thread,dispatch));db.commit()
                if self.launch.verify_inventory(client,thread) is not True:
                    raise ValueError('exact planning tools required')
                response=client.call('turn/start',dict(threadId=thread,input=[dict(type='text',text=event['message'])]))
                turn=d.text(response['turn']['id'],256,single_line=True)
                with self.connection() as db:
                    db.execute("UPDATE planning_turns SET turn=?,state='running' WHERE dispatch=?",(turn,dispatch));db.commit()
            except Exception:
                with self.connection() as db:
                    db.execute("UPDATE planning_turns SET state='uncertain' WHERE dispatch=?",(dispatch,));db.commit()
                self.registry.revoke(dispatch)
                raise ValueError('planning outcome uncertain; reconcile before retry') from None
        return dict(dispatch=dispatch,state='running',thread=thread,turn=turn,replayed=False)

    def complete(self,dispatch,thread,turn,status,result=None):
        """Called only by the trusted native event collector."""
        if self.lock_fd is None:raise ValueError('exclusive planning lock required')
        local('onboarding_drafts').identifier(dispatch)
        if status not in ('completed','failed','interrupted') or (result is not None and (type(result) is not str or len(result.encode())>65536)):
            raise ValueError('bounded native terminal event required')
        with self.lock,self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            updated=db.execute("UPDATE planning_turns SET state=?,result=? WHERE dispatch=? AND thread=? AND turn=? AND state IN ('running','interrupt_requested')",
                (status,result,dispatch,thread,turn)).rowcount
            if updated!=1:raise ValueError('planning terminal event differs')
            db.commit()
            self.registry.revoke(dispatch)
            client=self.clients.pop(dispatch,None)
            if callable(getattr(client,'close',None)):client.close()

    def recover_after_exclusive_start(self):
        """Retain ambiguous previous work after acquiring the service lock."""
        if self.lock_fd is None:raise ValueError('exclusive planning lock required')
        with self.lock,self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT dispatch FROM planning_turns WHERE state IN ('preparing','running','interrupt_requested')").fetchall()
            db.execute("UPDATE planning_turns SET state='uncertain' WHERE state IN ('preparing','running','interrupt_requested')")
            db.commit()
        for row in rows:self.registry.revoke(row[0])
        return dict(uncertain=len(rows),automatically_retried=0)

    def interrupt(self,dispatch,session):
        """Called after a separately verified native stop from the same session."""
        if self.lock_fd is None:raise ValueError('exclusive planning lock required')
        d=local('onboarding_drafts');d.identifier(dispatch);d.identifier(session)
        with self.lock,self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT session,state,thread,turn FROM planning_turns WHERE dispatch=?',(dispatch,)).fetchone()
            if row is None or row[0]!=session:raise ValueError('exact planning session required')
            if row[1]=='interrupt_requested':return dict(state='interrupt_requested')
            if row[1]!='running' or not row[2] or not row[3] or dispatch not in self.clients:
                raise ValueError('active planning turn required')
            db.execute("UPDATE planning_turns SET state='interrupt_requested' WHERE dispatch=?",(dispatch,));db.commit()
            try:self.clients[dispatch].call('turn/interrupt',dict(threadId=row[2],turnId=row[3]))
            except Exception:
                db.execute("UPDATE planning_turns SET state='uncertain' WHERE dispatch=?",(dispatch,));db.commit()
                self.registry.revoke(dispatch)
                raise ValueError('interrupt outcome uncertain; reconcile') from None
            return dict(state='interrupt_requested')

    def close(self):
        with self.lock:
            for client in self.clients.values():
                if callable(getattr(client,'close',None)):client.close()
            self.clients.clear()
            if self.lock_fd is not None:os.close(self.lock_fd);self.lock_fd=None
