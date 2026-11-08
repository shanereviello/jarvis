"""Scoped handoff staging and passive delivery; no model or OAuth client.

The private parent supplies the active source identity and retained incoming
chain. The native tool supplies prose only. Delivery retries the same immutable
n8n admission request; it never retries a Linear mutation or a coding turn.
"""
from contextlib import contextmanager
import http.client
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit


def local(name):
    spec=importlib.util.spec_from_file_location('runtime_handoff_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def schema():
    string=lambda maximum:dict(type='string',minLength=1,maxLength=maximum)
    return dict(type='object',additionalProperties=False,required=['key','summary','requested_action','references','limitations'],
        properties=dict(key=dict(type='string',pattern='^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$'),summary=string(8192),
            requested_action=string(4096),limitations=dict(type='array',maxItems=32,items=string(4096)),
            references=dict(type='array',maxItems=32,items=dict(type='object',additionalProperties=False,
                required=['namespace','id','sha256'],properties=dict(namespace=dict(type='string',pattern='^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$'),
                    id=string(512),sha256=dict(anyOf=[dict(type='null'),dict(type='string',pattern='^[0-9a-f]{64}$')]))))))


def incoming(value,policy,issue,session):
    """Validate the subset supplied by authenticated transport, never prose."""
    native=local('native_handoff')
    if (type(value) is not dict or set(value)!={'id','depth','source_session_id','sender_app_user_id','recipient_app_user_id','target_session_id'} or
            type(value['depth']) is not int or not 1<=value['depth']<=4 or value['target_session_id']!=session or
            value['sender_app_user_id']!=policy['agents']['jarvis'] or value['recipient_app_user_id']!=policy['agents']['codex'] or
            issue not in policy['issues']):raise ValueError('exact incoming native handoff context required')
    for field in ('id','source_session_id','sender_app_user_id','recipient_app_user_id','target_session_id'):native.identifier(value[field])
    return json.loads(native.encoded(value))


class Queue:
    def __init__(self,path,*,create=False):
        self.i=local('capture_intake');self.path=Path(path)
        if create:self.path.mkdir(mode=0o700)
        self.i.private(self.path,True);self.db=self.path/'handoffs.sqlite3'
        if create:
            fd=os.open(self.db,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(fd)
            with self.connection() as db:
                db.executescript('''CREATE TABLE handoffs(sequence INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,
                    intent BLOB NOT NULL,digest TEXT NOT NULL,receipt BLOB,last_attempt INTEGER NOT NULL DEFAULT 0);
                    CREATE TRIGGER immutable_intent BEFORE UPDATE OF sequence,id,intent,digest ON handoffs
                        BEGIN SELECT RAISE(ABORT,'immutable handoff intent'); END;
                    CREATE TRIGGER immutable_receipt BEFORE UPDATE OF receipt ON handoffs WHEN OLD.receipt IS NOT NULL
                        BEGIN SELECT RAISE(ABORT,'immutable handoff acknowledgment'); END;
                    CREATE TRIGGER retain_intent BEFORE DELETE ON handoffs
                        BEGIN SELECT RAISE(ABORT,'handoff deletion not enabled'); END;''')
            self.i.sync(self.path)

    @contextmanager
    def connection(self):
        self.i.private(self.path,True);self.i.private(self.db)
        for suffix in ('-journal','-wal','-shm'):
            path=Path(str(self.db)+suffix)
            if path.exists() or path.is_symlink():self.i.private(path)
        db=sqlite3.connect(self.db.as_uri()+'?mode=rw',uri=True,timeout=3);db.row_factory=sqlite3.Row
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA synchronous=FULL')
        try:yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    def stage(self,intent):
        native=local('native_handoff');raw=native.encoded(intent);c=self.i.local('contract')
        if len(raw)>32768:raise ValueError('bounded handoff required')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT intent FROM handoffs WHERE id=?',(intent['id'],)).fetchone()
            if old:
                if old['intent']!=raw:raise ValueError('handoff key changed; retain original intent')
                return dict(staged=True,replayed=True,handoff_id=intent['id'],execution_started=False)
            if db.execute('SELECT count(*) FROM handoffs').fetchone()[0]>=1024:raise ValueError('handoff queue capacity reached; retain source')
            db.execute('INSERT INTO handoffs(id,intent,digest) VALUES(?,?,?)',(intent['id'],raw,c.digest(raw)))
        self.i.sync(self.path)
        return dict(staged=True,replayed=False,handoff_id=intent['id'],execution_started=False)

    def flush(self,send,*,independent=False):
        if type(independent) is not bool:raise ValueError('explicit delivery ordering required')
        delivered=0
        order='last_attempt,sequence' if independent else 'sequence'
        with self.connection() as db:rows=db.execute('SELECT * FROM handoffs WHERE receipt IS NULL ORDER BY '+order+' LIMIT 32').fetchall()
        for row in rows:
            c=self.i.local('contract')
            if c.digest(row['intent'])!=row['digest']:raise ValueError('frozen handoff digest differs')
            if independent:
                with self.connection() as db:
                    counter=db.execute('SELECT coalesce(max(last_attempt),0)+1 FROM handoffs').fetchone()[0]
                    if counter>=2**53:raise ValueError('delivery cursor exhausted; retain queue')
                    db.execute('UPDATE handoffs SET last_attempt=? WHERE id=?',(counter,row['id']))
            try:
                result=send(c.decode(row['intent']))
                if result!=dict(staged=True,request_id=row['id'],execution_started=False):raise ValueError('exact handoff admission unconfirmed')
            except (ValueError,OSError,http.client.HTTPException):
                if independent:continue
                break
            with self.connection() as db:
                db.execute('UPDATE handoffs SET receipt=? WHERE id=? AND receipt IS NULL',(c.encoded(result),row['id']))
            delivered+=1
        with self.connection() as db:pending=db.execute('SELECT count(*) FROM handoffs WHERE receipt IS NULL').fetchone()[0]
        return dict(delivered=delivered,pending=pending,models_started=0)


def stage(runtime,reporter,row,arguments):
    from jsonschema import Draft202012Validator
    Draft202012Validator(schema()).validate(arguments)
    selected=reporter.configuration.get('handoff')
    if selected is None:raise ValueError('native handoff installation unavailable')
    native=local('native_handoff');request=reporter.c.decode(row['request'])
    if reporter.c.digest(row['request'])!=row['digest']:raise ValueError('actual dispatch digest differs')
    chain=request.get('incoming_handoff')
    if chain:incoming(chain,selected['policy'],row['issue'],row['session'])
    trusted=dict(session_id=row['session'],issue_id=row['issue'],binding=request['binding'],
        parent_handoff_id=chain['id'] if chain else None,depth=chain['depth'] if chain else 0)
    # The transport checks quiescence before publishing. Staging does not
    # interrupt the current turn, delegate the issue or give Jarvis coding access.
    intent=native.prepare(selected['policy'],'codex',trusted,arguments)
    return Queue(selected['spool']).stage(intent)


def sender(url,token):
    parsed=urlsplit(url)
    if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path!='/webhook/rras-native-handoff-codex' or type(token) is not bytes or not 32<=len(token)<=256 or
            not all(33<=n<=126 for n in token)):raise ValueError('fixed private Codex handoff admission required')
    def send(intent):
        connection=(http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection)(parsed.hostname,parsed.port,timeout=15)
        try:
            connection.request('POST',parsed.path,body=local('native_handoff').encoded(intent),headers={
                'Content-Type':'application/json','Authorization':'Bearer '+token.decode()})
            response=connection.getresponse();raw=response.read(4097)
            if response.status!=200 or len(raw)>4096:raise ValueError('handoff admission unconfirmed')
            return local('capture_intake').local('contract').decode(raw)
        finally:connection.close()
    return send
