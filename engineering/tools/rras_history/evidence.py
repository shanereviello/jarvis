"""Private immutable byte custody, explicitly added to a schema-4 history store.

No source-path reads, URLs, collection, work launches or retention deletion.
Reporting manifests pin bytes; upload receipts alone do not associate a project.
"""
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import stat
import uuid

CHUNK_BYTES=65536
MAX_CHUNKS=131072
MAX_UPLOADS=1000000
TOTAL_BYTES=8*1024**3
SCOPE_BYTES=2*1024**3
SHA=re.compile(r'[0-9a-f]{64}\Z')
DDL=(
    '''CREATE TABLE evidence_uploads(sequence INTEGER PRIMARY KEY,principal INTEGER NOT NULL,
       client_key TEXT NOT NULL,scope_kind TEXT NOT NULL,scope_id TEXT NOT NULL,
       chunk_sha256 TEXT NOT NULL,byte_length INTEGER NOT NULL,
       request_sha256 TEXT NOT NULL,receipt BLOB NOT NULL,UNIQUE(principal,client_key))''',
    '''CREATE TABLE evidence_chunks(scope_kind TEXT NOT NULL,scope_id TEXT NOT NULL,
       chunk_sha256 TEXT NOT NULL,byte_length INTEGER NOT NULL,upload_sequence INTEGER NOT NULL
       REFERENCES evidence_uploads(sequence),PRIMARY KEY(scope_kind,scope_id,chunk_sha256))''',
    '''CREATE TRIGGER evidence_upload_no_update BEFORE UPDATE ON evidence_uploads
       BEGIN SELECT RAISE(ABORT,'immutable evidence receipt'); END''',
    '''CREATE TRIGGER evidence_upload_no_delete BEFORE DELETE ON evidence_uploads
       BEGIN SELECT RAISE(ABORT,'immutable evidence receipt'); END''',
    '''CREATE TRIGGER evidence_chunk_no_update BEFORE UPDATE ON evidence_chunks
       BEGIN SELECT RAISE(ABORT,'immutable evidence chunk index'); END''',
    '''CREATE TRIGGER evidence_chunk_no_delete BEFORE DELETE ON evidence_chunks
       BEGIN SELECT RAISE(ABORT,'evidence retention deletion not enabled'); END''',
)


def local(name):
    spec=importlib.util.spec_from_file_location('evidence_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def validate(value):
    if (type(value) is not dict or set(value)!={'contract','client_event_key','scope','sha256','byte_length','data_base64'}
            or value['contract']!='engineering-evidence-chunk.v1'):
        raise ValueError('exact bounded chunk request required')
    local('projects').scope(value['scope'])
    key=value['client_event_key']
    if type(key) is not str or not 1<=len(key)<=128 or not key.strip() or '\0' in key:
        raise ValueError('stable bounded upload key required')
    if type(value['sha256']) is not str or not SHA.fullmatch(value['sha256']):
        raise ValueError('chunk digest required')
    if type(value['byte_length']) is not int or not 1<=value['byte_length']<=CHUNK_BYTES:
        raise ValueError('bounded positive chunk required')
    text=value['data_base64']
    if type(text) is not str or len(text)>4*((CHUNK_BYTES+2)//3):
        raise ValueError('bounded base64 required')
    try:raw=base64.b64decode(text,validate=True)
    except (ValueError,binascii.Error):raise ValueError('canonical base64 required') from None
    if (base64.b64encode(raw).decode()!=text or len(raw)!=value['byte_length'] or
            hashlib.sha256(raw).hexdigest()!=value['sha256']):
        raise ValueError('exact chunk bytes required')
    return value,raw


class Evidence:
    def __init__(self,store):
        self.store=store;self.c=local('contract')
        self.root=store.root/'evidence';self.chunks=self.root/'chunks'

    def directory(self,path,create=False):
        if create:
            try:path.mkdir(mode=0o700)
            except FileExistsError:pass
        info=path.lstat()
        if (path.resolve()!=path or not stat.S_ISDIR(info.st_mode) or
                info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700):
            raise ValueError('service-owned private evidence directory required')

    @staticmethod
    def sync(path):
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    def fingerprint(self,db):
        reporting=local('reporting').Reporting(self.store);reporting.events(db)
        base=reporting.fingerprint(db);digest=hashlib.sha256(self.c.encoded(base))
        for name in ('reporting_submissions','reporting_outbox'):
            for row in db.execute('SELECT * FROM '+name+' ORDER BY sequence'):
                digest.update(self.c.encoded([x.hex() if isinstance(x,bytes) else x for x in row]))
        # Bind the proposed additive schema and initial quota policy too.
        digest.update(self.c.encoded(dict(ddl=DDL,chunk_bytes=CHUNK_BYTES,total_bytes=TOTAL_BYTES,scope_bytes=SCOPE_BYTES,max_chunks=MAX_CHUNKS)))
        return dict(contract='engineering-evidence-migration.v1',from_version=4,to_version=5,
            expected_sha256=digest.hexdigest(),authority_granted=False,
            changes='add immutable chunk custody; preserve every prior database record and signed snapshot')

    def migration_plan(self):
        with self.store.connection() as db:
            db.execute('BEGIN')
            if db.execute('PRAGMA user_version').fetchone()[0]!=4:raise ValueError('exact schema-4 store required')
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('database integrity differs')
            return self.fingerprint(db)

    def migrate(self,expected_sha256):
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0]!=4:raise ValueError('explicit schema-4 store required')
            plan=self.fingerprint(db)
            if plan['expected_sha256']!=expected_sha256:raise ValueError('exact reviewed evidence migration required')
            self.directory(self.root,True);self.directory(self.chunks,True)
            self.sync(self.root);self.store.sync()
            for statement in DDL:db.execute(statement)
            db.execute('PRAGMA user_version=5');db.commit()
        self.store.sync();return dict(plan,migrated=True)

    def read_blob(self,digest,length):
        if type(digest) is not str or not SHA.fullmatch(digest) or not 1<=length<=CHUNK_BYTES:
            raise ValueError('exact bounded chunk reference required')
        self.directory(self.root);self.directory(self.chunks)
        fd=os.open(self.chunks/digest,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as f:
            info=os.fstat(f.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
                    stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size!=length):
                raise ValueError('private immutable chunk required')
            raw=f.read(CHUNK_BYTES+1)
        if len(raw)!=length or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('retained chunk bytes differ')
        return raw

    def usage(self):
        self.directory(self.root);self.directory(self.chunks)
        count=total=0
        with os.scandir(self.chunks) as entries:
            for entry in entries:
                count+=1
                if count>MAX_CHUNKS or not SHA.fullmatch(entry.name):raise ValueError('evidence directory exceeds policy or contains unknown entries')
                info=entry.stat(follow_symlinks=False)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
                        stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or not 1<=info.st_size<=CHUNK_BYTES):
                    raise ValueError('unsafe evidence entry')
                total+=info.st_size
        return count,total

    def upload(self,value,*,peer_uid=None):
        value,raw=validate(value);metadata={k:v for k,v in value.items() if k!='data_base64'}
        request_sha=self.c.digest(self.c.encoded(metadata));selected=value['scope']
        if peer_uid is not None:local('unix').uid(peer_uid)
        principal=os.getuid() if peer_uid is None else -peer_uid
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('PRAGMA user_version').fetchone()[0]!=5:raise ValueError('explicit evidence upgrade required')
            prior=db.execute('SELECT request_sha256,receipt FROM evidence_uploads WHERE principal=? AND client_key=?',
                (principal,value['client_event_key'])).fetchone()
            if prior:
                if prior[0]!=request_sha:raise ValueError('evidence idempotency conflict')
                self.read_blob(value['sha256'],len(raw))
                return dict(inserted=False,receipt=self.c.decode(prior[1]))
            count=db.execute('SELECT count(*) FROM evidence_uploads').fetchone()[0]
            if count>=MAX_UPLOADS:raise ValueError('evidence receipt capacity reached; retain pending capture')
            args=(selected['kind'],selected['id'])
            exists=db.execute('SELECT byte_length FROM evidence_chunks WHERE scope_kind=? AND scope_id=? AND chunk_sha256=?',
                args+(value['sha256'],)).fetchone()
            if not exists:
                used=db.execute('SELECT coalesce(sum(byte_length),0) FROM evidence_chunks WHERE scope_kind=? AND scope_id=?',args).fetchone()[0]
                if used+len(raw)>SCOPE_BYTES:raise ValueError('evidence capacity reached; retain pending capture')
            files,used=self.usage();path=self.chunks/value['sha256']
            try:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            except FileExistsError:
                self.read_blob(value['sha256'],len(raw))
            else:
                try:
                    if files>=MAX_CHUNKS or used+len(raw)>TOTAL_BYTES:raise ValueError('evidence capacity reached; retain pending capture')
                    with os.fdopen(fd,'wb') as f:
                        fd=None;f.write(raw);f.flush();os.fsync(f.fileno())
                    self.sync(self.chunks)
                except BaseException:
                    if fd is not None:os.close(fd)
                    path.unlink();self.sync(self.chunks);raise
            stamp=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
            scoped_sequence=db.execute('SELECT count(*) FROM evidence_uploads WHERE scope_kind=? AND scope_id=?',args).fetchone()[0]+1
            receipt=dict(contract='engineering-evidence-receipt.v1',receipt_id='rcp_'+uuid.uuid4().hex,
                sequence=scoped_sequence,request_sha256=request_sha,scope=selected,sha256=value['sha256'],byte_length=len(raw),
                writer_uid=os.getuid(),peer_uid=peer_uid,recorded_at=stamp,visibility='operator_private',authority_granted=False)
            db.execute('INSERT INTO evidence_uploads VALUES(?,?,?,?,?,?,?,?,?)',
                (count+1,principal,value['client_event_key'],*args,value['sha256'],len(raw),request_sha,self.c.encoded(receipt)))
            if not exists:db.execute('INSERT INTO evidence_chunks VALUES(?,?,?,?,?)',(*args,value['sha256'],len(raw),count+1))
            db.commit()
        self.store.sync();return dict(inserted=True,receipt=receipt)

    def verify_manifest(self,db,selected,body):
        if db.execute('PRAGMA user_version').fetchone()[0]!=5:raise ValueError('private evidence byte intake upgrade required')
        digest=hashlib.sha256()
        for chunk in body['chunks']:
            row=db.execute('SELECT byte_length FROM evidence_chunks WHERE scope_kind=? AND scope_id=? AND chunk_sha256=?',
                (selected['kind'],selected['id'],chunk['sha256'])).fetchone()
            if row is None or row[0]!=chunk['byte_length']:raise ValueError('retained scoped chunk required before finalization')
            digest.update(self.read_blob(chunk['sha256'],chunk['byte_length']))
        if digest.hexdigest()!=body['content_sha256']:raise ValueError('artifact content digest differs')

    def read(self,selected,query):
        if type(query) is not dict or set(query) not in (
                {'artifact_id','version','snapshot'},{'artifact_id','version','snapshot','index'},
                {'artifact_id','version','snapshot','index','count'}):
            raise ValueError('exact signed artifact query required')
        if (type(query['artifact_id']) is not str or not re.fullmatch('cap_[0-9a-f]{32}',query['artifact_id']) or
                type(query['version']) is not int or query['version']<1):raise ValueError('exact artifact revision required')
        boundary=local('projects').Projects(self.store).read(selected,dict(view='reporting',snapshot=query['snapshot']))
        if not boundary['available']:raise ValueError('artifact unavailable at this signed boundary')
        with self.store.connection() as db:
            events=local('reporting').Reporting(self.store).events(db,selected)[:query['snapshot']['reporting_sequence']]
        rows=[(r,rcpt) for r,rcpt in events if r['operation']=='artifact.record' and
            r['body']['artifact_id']==query['artifact_id'] and r['body']['version']==query['version']]
        if len(rows)!=1:raise ValueError('artifact unavailable at this signed boundary')
        request,receipt=rows[0];body=request['body']
        result=dict(manifest=body,manifest_sha256=receipt['request_sha256'],scope=selected,
            context=request['context'],source=request['source'],snapshot=query['snapshot'],
            audience='authorized_scope_private',authority_granted=False)
        associations=local('reporting').Reporting.associations(events)
        association=associations.get((query['artifact_id'],query['version']))
        result['association']=dict(submission=association[0],receipt=association[1]) if association else None
        result['effective_context']=association[0]['context'] if association else request['context']
        if 'index' in query:
            index=query['index'];count=query.get('count',1)
            if (type(index) is not int or type(count) is not int or not 1<=count<=8 or
                    not 0<=index<len(body['chunks']) or index+count>len(body['chunks'])):
                raise ValueError('bounded artifact chunk range required')
            chunks=[]
            for chunk in body['chunks'][index:index+count]:
                raw=self.read_blob(chunk['sha256'],chunk['byte_length'])
                chunks.append(dict(chunk,data_base64=base64.b64encode(raw).decode()))
            if 'count' in query:result['chunks']=chunks
            else:result['chunk']=chunks[0]
        return result
