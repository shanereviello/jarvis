"""Passive private export spool and history delivery; never launches engineering.

Accept collector output bytes and explicit context. Collection and authorization
of a source belong to the selected-source adapter, not text inside an export.
"""
import base64
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid

ROOT=Path(__file__).resolve().parents[1]/'rras_history'
MAX_EXPORT=64*1024**2
MAX_SPOOL=1024**3
MAX_ITEMS=10000
PROFILE='engineering-redaction-v1'


def local(name):
    spec=importlib.util.spec_from_file_location('capture_intake_'+name,ROOT/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def private(path,directory=False):
    p=Path(path);info=p.lstat()
    if (not p.is_absolute() or p.resolve()!=p or info.st_uid!=os.getuid() or
            stat.S_IMODE(info.st_mode)!=(0o700 if directory else 0o600) or
            not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink==1)):
        raise ValueError('private caller-owned canonical spool required')
    return p


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def redact(raw):
    if type(raw) is not bytes or len(raw)>MAX_EXPORT:raise ValueError('bounded collector bytes required')
    text=raw.decode('utf-8');counts={}
    rules=[
        ('private_key',r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----'),
        ('authorization',r'(?im)\b(?:authorization|proxy-authorization)\s*[:=]\s*[^\r\n]+'),
        ('cookie',r'(?im)\b(?:set-cookie|cookie)\s*:\s*[^\r\n]+'),
        ('credential_value',r'''(?im)(?:["']?\b(?:client[_-]?secret|access[_-]?token|refresh[_-]?token|api[_-]?key|password|cf_access_client_secret|codex_n8n_bridge_secret|n8n_bridge_secret|linear_webhook_secret|codex_webhook_secret)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;\r\n]+)'''),
        ('provider_token',r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'),
        ('jwt',r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b'),
    ]
    for name,pattern in rules:
        text,count=re.subn(pattern,'[REDACTED:'+name+']',text)
        if count:counts[name]=count
    return text.encode(),counts


def redact_object(value):
    """Filter strings before JSON escaping can hide line/header boundaries."""
    counts={}
    def clean(item):
        if type(item) is str:
            raw,found=redact(item.encode())
            for k,n in found.items():counts[k]=counts.get(k,0)+n
            return raw.decode()
        if type(item) is list:return [clean(x) for x in item]
        if type(item) is dict:
            result={}
            for k,v in item.items():
                if re.fullmatch(r'(?i)(authorization|proxy-authorization|set-cookie|cookie|client[_-]?secret|access[_-]?token|refresh[_-]?token|api[_-]?key|password)',k):
                    result[k]='[REDACTED:credential_value]';counts['credential_value']=counts.get('credential_value',0)+1
                else:result[k]=clean(v)
            return result
        return item
    return clean(value),counts


def stamp():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


class Spool:
    def __init__(self,root,*,create=False):
        self.root=Path(root);self.c=local('contract')
        if create:self.root.mkdir(mode=0o700,parents=False,exist_ok=False)
        private(self.root,True);self.exports=self.root/'exports';self.db=self.root/'spool.sqlite3'
        if create:
            self.exports.mkdir(mode=0o700)
            fd=os.open(self.db,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
            with self.connection() as db:
                db.executescript('''CREATE TABLE items(sequence INTEGER PRIMARY KEY,key TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL,artifact TEXT,request BLOB NOT NULL,request_sha256 TEXT NOT NULL,
                    export_sha256 TEXT,depends INTEGER REFERENCES items(sequence),receipt BLOB,
                    state TEXT NOT NULL DEFAULT 'pending',last_error TEXT);
                    CREATE TRIGGER immutable_capture_request BEFORE UPDATE OF key,kind,artifact,request,
                        request_sha256,export_sha256,depends ON items
                        BEGIN SELECT RAISE(ABORT,'frozen capture request'); END;
                    CREATE TABLE chunk_receipts(item INTEGER REFERENCES items(sequence),chunk_index INTEGER,
                        receipt BLOB NOT NULL,PRIMARY KEY(item,chunk_index));
                    CREATE TRIGGER no_capture_delete BEFORE DELETE ON items
                        BEGIN SELECT RAISE(ABORT,'capture retention deletion not enabled'); END;''')
                db.commit()
            sync(self.root)
        private(self.exports,True)

    @contextmanager
    def connection(self):
        private(self.root,True);private(self.db)
        for suffix in ('-journal','-wal','-shm'):
            p=Path(str(self.db)+suffix)
            if p.exists() or p.is_symlink():private(p)
        db=sqlite3.connect(self.db.as_uri()+'?mode=rw',uri=True,timeout=10);db.row_factory=sqlite3.Row
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA synchronous=FULL')
        try:yield db
        finally:db.close()

    def enqueue(self,db,request,kind,artifact=None,export=None,depends=None):
        request=local('reporting_contract').validate(request);raw=self.c.encoded(request);sha=self.c.digest(raw)
        old=db.execute('SELECT * FROM items WHERE key=?',(request['client_event_key'],)).fetchone()
        if old:
            if old['request']!=raw:raise ValueError('capture key conflict')
            return old['sequence']
        if db.execute('SELECT count(*) FROM items').fetchone()[0]>=MAX_ITEMS:raise ValueError('capture spool capacity reached; retain source')
        seq=db.execute('INSERT INTO items(key,kind,artifact,request,request_sha256,export_sha256,depends) VALUES(?,?,?,?,?,?,?)',
            (request['client_event_key'],kind,artifact,raw,sha,export,depends)).lastrowid
        return seq

    def observation(self,request,state,detail,*,when=None):
        when=when or stamp();source=request['body']['session']
        key=self.c.digest(self.c.encoded(dict(request=request['client_event_key'],status=state,detail=detail)))
        return dict(contract='engineering-reporting.v1',operation='source.observe',client_event_key='capture-status:'+key,
            expected_head=None,scope=request['scope'],context=request['context'],source=request['source'],occurred_at=when,
            body=dict(source=source,source_observed_at=request['body'].get('captured_at'),cursor=request['body']['source_range']['end'],status=state,
                gaps=[] if state=='current' else [detail],detail=detail))

    def status_item(self,db,request,state,detail):
        value=self.observation(request,state,detail)
        old=db.execute('SELECT sequence FROM items WHERE key=?',(value['client_event_key'],)).fetchone()
        # Preserve the first observed status/time on repeat failure or replay.
        return old[0] if old else self.enqueue(db,value,'status')

    def source_status(self,*,scope,context,session,status,detail,cursor=None,source_observed_at=None):
        """Record a meaningful selected-source state transition, never every poll."""
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE');prior=None
            for row in db.execute("SELECT request,request_sha256 FROM items WHERE kind='status' ORDER BY sequence DESC"):
                value=self.c.decode(row['request'])
                if value['scope']==scope and value['body']['source']==session:
                    prior=(value,row['request_sha256']);break
            if (prior and prior[0]['context']==context and prior[0]['body']['status']==status and
                    prior[0]['body']['detail']==detail):return dict(staged=False)
            count=db.execute('SELECT count(*) FROM items').fetchone()[0]
            pending=db.execute("SELECT count(*) FROM items WHERE kind='artifact' AND receipt IS NULL").fetchone()[0]
            if count+2*pending+1>MAX_ITEMS:raise ValueError('capture status capacity reached; retain pending source')
            key=self.c.digest(self.c.encoded(dict(scope=scope,source=session,status=status,detail=detail,
                predecessor=prior[1] if prior else None,context=context)))
            request=dict(contract='engineering-reporting.v1',operation='source.observe',client_event_key='source-state:'+key,
                expected_head=None,scope=scope,context=context,source=dict(kind='imported',namespace='capture_intake',id=session['id']),
                occurred_at=stamp(),body=dict(source=session,source_observed_at=source_observed_at,cursor=cursor,
                    status=status,gaps=[] if status=='current' else [detail],detail=detail))
            self.enqueue(db,request,'status');db.commit()
        sync(self.root);return dict(staged=True)

    def observe_linear(self,snapshot,*,scope,context,organization_id,team_id,project_id,object_kind,object_id,updated_at):
        original=self.c.encoded(snapshot);snapshot,redactions=redact_object(snapshot);raw=self.c.encoded(snapshot)
        # The owned observation contract bounds small snapshots. Oversized
        # content is a gap, never silent truncation into a successful record.
        if len(raw)>65536:raise ValueError('Linear snapshot exceeds bounded observation; retain source')
        body=dict(object_kind=object_kind,organization_id=organization_id,team_id=team_id,
            linear_project_id=project_id,object_id=object_id,source_updated_at=updated_at,
            snapshot_sha256=self.c.digest(raw),snapshot_text=raw.decode(),references=[],
            redaction_profile=PROFILE,source_snapshot_sha256=self.c.digest(original),
            gaps=['Polling can miss intermediate edits and objects deleted between polls.',
                'Pattern redaction is partial; imported statements grant no execution or approval authority.'])
        if redactions:body['gaps'].append('Recognized credentials were removed before persistent observation staging.')
        key=self.c.digest(self.c.encoded(dict(scope=scope,context=context,body=body)))
        request=dict(contract='engineering-reporting.v1',operation='linear.observe',client_event_key='linear-observation:'+key,
            expected_head=None,scope=scope,context=context,source=dict(kind='imported',namespace='linear_poll',id=object_id),
            occurred_at=updated_at,body=body)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT sequence FROM items WHERE key=?',(request['client_event_key'],)).fetchone()
            if old:return dict(staged=False,sequence=old[0])
            count=db.execute('SELECT count(*) FROM items').fetchone()[0]
            pending=db.execute("SELECT count(*) FROM items WHERE kind='artifact' AND receipt IS NULL").fetchone()[0]
            if count+2*pending+1>MAX_ITEMS:raise ValueError('observation capacity reached; retain pending source')
            seq=self.enqueue(db,request,'observation');db.commit()
        sync(self.root);return dict(staged=True,sequence=seq)

    def stage(self,raw,*,scope,context,session,collector,collector_version,source_sha256,
              source_range=None,gaps=(),source_created_at=None,source_updated_at=None,authorization_reference=None):
        original=raw;raw,redactions=redact(raw);digest=hashlib.sha256(raw).hexdigest()
        if type(source_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',source_sha256):raise ValueError('exact source identity required')
        artifact='cap_'+uuid.uuid5(uuid.NAMESPACE_URL,json.dumps([scope,session,collector],sort_keys=True)).hex
        event_key='capture:'+self.c.digest(self.c.encoded(dict(scope=scope,context=context,session=session,
            source=source_sha256,content=digest,collector=collector,collector_version=collector_version)))
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT sequence FROM items WHERE key=?',(event_key,)).fetchone()
            if existing:return dict(staged=False,sequence=existing[0],artifact_id=artifact,redactions=redactions)
            count=db.execute('SELECT count(*) FROM items').fetchone()[0]
            pending=db.execute("SELECT count(*) FROM items WHERE kind='artifact' AND receipt IS NULL").fetchone()[0]
            if count+2*pending+4>MAX_ITEMS:
                raise ValueError('capture spool capacity reached; retain source')
            previous=db.execute("SELECT * FROM items WHERE artifact=? AND kind='artifact' ORDER BY sequence DESC LIMIT 1",(artifact,)).fetchone()
            old=self.c.decode(previous['request']) if previous else None
            limits=list(gaps)+['Session-level context; this export does not prove that every exchange belongs to the linked work.',
                'Pattern redaction covers recognized credentials; it is not proof that arbitrary secrets are absent.']
            if redactions:limits.append('Recognized credential values were redacted by '+PROFILE+'.')
            request=dict(contract='engineering-reporting.v1',operation='artifact.record',client_event_key=event_key,
                expected_head=previous['request_sha256'] if previous else None,scope=scope,context=context,
                source=dict(kind='imported',namespace='capture_intake',id=session['id']),occurred_at=source_updated_at,
                body=dict(artifact_id=artifact,version=old['body']['version']+1 if old else 1,
                    previous_sha256=previous['request_sha256'] if previous else None,session=session,
                    collector=collector,collector_version=collector_version,media_type='text/markdown',
                    content_sha256=digest,byte_length=len(raw),
                    chunks=[dict(index=i,sha256=hashlib.sha256(raw[n:n+65536]).hexdigest(),byte_length=len(raw[n:n+65536]))
                        for i,n in enumerate(range(0,len(raw),65536))],
                    source_range=dict(source_range or dict(start=None,end=None),source_sha256=source_sha256),
                    completeness='partial',gaps=limits,redaction_profile=PROFILE,
                    source_created_at=source_created_at,source_updated_at=source_updated_at,captured_at=stamp()))
            if authorization_reference is not None:request['body']['authorization_reference']=authorization_reference
            local('reporting_contract').validate(request)
            path=self.exports/digest
            used=0
            for p in self.exports.iterdir():
                private(p);used+=p.stat().st_size
            if not path.exists():
                if used+len(raw)>MAX_SPOOL:raise ValueError('capture spool byte capacity reached; retain native source')
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
                sync(self.exports)
            else:
                private(path)
                if path.read_bytes()!=raw:raise ValueError('private export digest collision')
            self.status_item(db,request,'pending' if context else 'unmapped','Export retained privately; history delivery pending.')
            seq=self.enqueue(db,request,'artifact',artifact,digest,previous['sequence'] if previous else None)
            db.commit()
        sync(self.root)
        return dict(staged=True,sequence=seq,artifact_id=artifact,redactions=redactions,
            normalized_sha256=digest,raw_bytes_retained=False,source_byte_length=len(original))

    def flush(self,send,*,maximum=100):
        if type(maximum) is not int or not 1<=maximum<=1000:raise ValueError('bounded passive delivery batch required')
        delivered=failed=0;visited=set()
        for _ in range(maximum):
            with self.connection() as db:
                rows=db.execute('SELECT * FROM items WHERE receipt IS NULL ORDER BY sequence').fetchall()
                row=next((r for r in rows if r['sequence'] not in visited and (r['depends'] is None or
                    db.execute('SELECT receipt FROM items WHERE sequence=?',(r['depends'],)).fetchone()[0] is not None)),None)
            if row is None:break
            visited.add(row['sequence']);request=self.c.decode(row['request'])
            try:
                if self.c.digest(row['request'])!=row['request_sha256']:raise ValueError('frozen spool request changed')
                if row['kind']=='artifact':
                    p=private(self.exports/row['export_sha256'])
                    if p.stat().st_size>MAX_EXPORT:raise ValueError('private export exceeds bound')
                    with p.open('rb') as f:raw=f.read(MAX_EXPORT+1)
                    if len(raw)>MAX_EXPORT or hashlib.sha256(raw).hexdigest()!=row['export_sha256']:raise ValueError('private export changed')
                    for part in request['body']['chunks']:
                        piece=raw[part['index']*65536:part['index']*65536+part['byte_length']]
                        chunk=dict(contract='engineering-evidence-chunk.v1',client_event_key='capture-chunk:'+part['sha256'],
                            scope=request['scope'],sha256=part['sha256'],byte_length=len(piece),data_base64=base64.b64encode(piece).decode())
                        # Namespace the key by scope; identical bytes elsewhere do not confer access.
                        chunk['client_event_key']='capture-chunk:'+self.c.digest(self.c.encoded(dict(scope=request['scope'],sha256=part['sha256'])))
                        answer=send(dict(method='evidence_upload',request=chunk));receipt=answer['receipt']
                        if type(receipt) is not dict:raise ValueError('chunk receipt required')
                        expected=self.c.digest(self.c.encoded({k:v for k,v in chunk.items() if k!='data_base64'}))
                        if (receipt.get('request_sha256')!=expected or receipt.get('scope')!=request['scope'] or
                                receipt.get('sha256')!=part['sha256'] or receipt.get('byte_length')!=len(piece) or
                                receipt.get('authority_granted') is not False):raise ValueError('chunk receipt differs')
                        with self.connection() as db:
                            old=db.execute('SELECT receipt FROM chunk_receipts WHERE item=? AND chunk_index=?',(row['sequence'],part['index'])).fetchone()
                            if old and old[0]!=self.c.encoded(receipt):raise ValueError('retained chunk receipt changed')
                            if not old:db.execute('INSERT INTO chunk_receipts VALUES(?,?,?)',(row['sequence'],part['index'],self.c.encoded(receipt)))
                            db.commit()
                answer=send(dict(method='reporting_submit',request=request));receipt=answer['receipt']
                if type(receipt) is not dict:raise ValueError('reporting receipt required')
                if (receipt.get('request_sha256')!=row['request_sha256'] or receipt.get('scope')!=request['scope'] or
                        receipt.get('context')!=request['context'] or receipt.get('authority_granted') is not False):
                    raise ValueError('reporting receipt differs')
                with self.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute("UPDATE items SET receipt=?,state='delivered',last_error=NULL WHERE sequence=?",
                        (self.c.encoded(receipt),row['sequence']))
                    if row['kind']=='artifact':
                        known=request['context'] is not None
                        self.status_item(db,request,'current' if known else 'unmapped',
                            'Exact private artifact receipt retained.' if known else 'Artifact retained; explicit project/work association is still required.')
                    db.commit()
                delivered+=1
            except (ValueError,OSError,KeyError,TypeError,sqlite3.Error):
                with self.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute("UPDATE items SET state='failed',last_error='delivery unconfirmed; replay frozen request' WHERE sequence=?",(row['sequence'],))
                    if row['kind']=='artifact':
                        self.status_item(db,request,'failed','History delivery unconfirmed; exact private export and request remain queued.')
                    db.commit()
                failed+=1
        sync(self.root)
        with self.connection() as db:
            pending=db.execute('SELECT count(*) FROM items WHERE receipt IS NULL').fetchone()[0]
        return dict(delivered=delivered,failed=failed,pending=pending,work_launched=False)
