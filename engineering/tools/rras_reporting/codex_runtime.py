"""Private Codex App Server adapter. No Linear OAuth, webhooks, or work scheduler.

The journal records runtime dispatch uncertainty; n8n owns transport delivery.
Only the fixed, operator-installed policy selects a runtime and work context.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import sqlite3
import stat
import subprocess
import threading
import uuid

MAX_MESSAGE = 64 * 1024
MAX_FRAME = 1024 * 1024


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode()


def identifier(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('canonical UUID required')
    return value


def bounded(value, limit=MAX_MESSAGE):
    if not isinstance(value, str) or not value.strip() or '\0' in value or len(value.encode()) > limit:
        raise ValueError('bounded nonempty text required')
    return value


def private(path, directory=False):
    path = Path(path)
    info = path.lstat()
    if (not path.is_absolute() or path.resolve() != path or info.st_uid != os.getuid() or
            info.st_mode & 0o077 or not (stat.S_ISDIR(info.st_mode) if directory else
                                       stat.S_ISREG(info.st_mode) and info.st_nlink == 1)):
        raise ValueError('private owner-controlled canonical path required')
    return path


def policy(value):
    if type(value) is not dict or set(value) != {'contract', 'organization_id', 'app_user_id',
            'execution_authorized', 'execution_authority_reference', 'binary', 'cwd',
            'sandbox', 'issues'} or value['contract'] != 'codex-runtime-policy.v1':
        raise ValueError('exact installed runtime policy required')
    identifier(value['organization_id']); identifier(value['app_user_id'])
    if type(value['execution_authorized']) is not bool:
        raise ValueError('explicit execution authority required')
    bounded(value['execution_authority_reference'], 4096)
    for field in ('binary', 'cwd'):
        p = Path(value[field])
        if not p.is_absolute() or p.resolve() != p:
            raise ValueError('fixed canonical runtime paths required')
    if value['sandbox'] not in ('read-only', 'workspace-write'):
        raise ValueError('bounded runtime sandbox required')
    if type(value['issues']) is not dict or not 1 <= len(value['issues']) <= 4096:
        raise ValueError('explicit issue pins required')
    for key, pin in value['issues'].items():
        identifier(key)
        if type(pin) is not dict or set(pin) != {'project_id', 'work_id', 'plan_id',
                'work_revision_sha256', 'architecture_version', 'architecture_sha256'}:
            raise ValueError('exact issue/work/architecture pin required')
        import re
        for field, prefix in [('project_id', 'prj_'), ('work_id', 'wrk_')]:
            if not isinstance(pin[field], str) or not re.fullmatch(prefix + '[0-9a-f]{32}', pin[field]):
                raise ValueError('history identity required')
        for field in ('work_revision_sha256', 'architecture_sha256'):
            if not isinstance(pin[field], str) or not re.fullmatch('[0-9a-f]{64}', pin[field]):
                raise ValueError('exact history digest required')
        if type(pin['architecture_version']) is not int or pin['architecture_version'] < 1:
            raise ValueError('positive architecture version required')
        bounded(pin['plan_id'], 96)
    return json.loads(encoded(value))


class AppServer:
    """Bounded stdio RPC. Never auto-accept server tool/permission requests."""
    def __init__(self, executable, cwd, *, timeout=15):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.pending = {}
        self.notifications = queue.Queue(maxsize=128)
        self.sequence = 0
        self.closed = False
        # No Linear credential or n8n secret is passed to the coding runtime.
        env = {k: os.environ[k] for k in ('HOME', 'PATH', 'LANG', 'CODEX_HOME') if k in os.environ}
        self.process = subprocess.Popen([executable, 'app-server'], cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.reader = threading.Thread(target=self._read, daemon=True); self.reader.start()
        try:
            self.call('initialize', dict(clientInfo=dict(name='rras_n8n_codex', version='0.4'),
                                         capabilities={}))
            self._write(dict(method='initialized'))
        except BaseException:
            self.close(); raise

    def _write(self, value):
        raw = encoded(value)
        if len(raw) > MAX_FRAME: raise ValueError('runtime frame too large')
        self.process.stdin.write(raw); self.process.stdin.flush()

    def _read(self):
        try:
            while True:
                raw = self.process.stdout.readline(MAX_FRAME + 1)
                if not raw or len(raw) > MAX_FRAME or not raw.endswith(b'\n'):
                    raise ValueError('runtime stream ended or exceeded its bound')
                message = json.loads(raw)
                if type(message) is not dict: raise ValueError('invalid runtime frame')
                if 'id' in message and 'method' in message:
                    # Approval requests remain visible; an RPC error grants nothing.
                    self.notifications.put_nowait(dict(method='adapter/approvalRequired', params={
                        'method': message['method'], 'request_id': message['id']}))
                    with self.lock:
                        self._write(dict(id=message['id'], error=dict(code=-32000,
                            message='No automatic approval; use the existing authorized operator surface.')))
                elif 'id' in message:
                    with self.lock:
                        target = self.pending.get(message['id'])
                        if target: target.put_nowait(message)
                else:
                    self.notifications.put_nowait(message)
        except (OSError, ValueError, TypeError, RecursionError, queue.Full):
            with self.lock:
                self.closed = True
                for target in self.pending.values():
                    try: target.put_nowait(dict(error=dict(message='runtime transport unavailable')))
                    except queue.Full: pass

    def call(self, method, params):
        with self.lock:
            if self.closed: raise ValueError('runtime unavailable; reconcile before retry')
            self.sequence += 1; key = self.sequence
            target = queue.Queue(maxsize=1); self.pending[key] = target
            try: self._write(dict(id=key, method=method, params=params))
            except BaseException:
                self.pending.pop(key); raise
        try:
            result = target.get(timeout=self.timeout)
            if 'error' in result: raise ValueError('runtime refused or outcome uncertain')
            return result['result']
        except queue.Empty:
            raise ValueError('runtime response uncertain; do not repeat the turn') from None
        finally:
            with self.lock: self.pending.pop(key, None)

    def events(self):
        result = []
        while True:
            try: result.append(self.notifications.get_nowait())
            except queue.Empty: return result

    def close(self):
        self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=3)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=3)
        self.reader.join(timeout=3)
        self.process.stdin.close(); self.process.stdout.close()


class Runtime:
    """Durable dispatch results and issue ownership, isolated from transport queues."""
    def __init__(self, root, selected_policy, *, create=False, client_factory=AppServer):
        self.policy = policy(selected_policy)
        self.root = Path(root)
        if create: self.root.mkdir(mode=0o700, parents=False, exist_ok=False)
        private(self.root, True)
        self.path = self.root / 'runtime.sqlite3'
        self.client_factory = client_factory
        self.client = None
        self.journal_lock = None
        self.closed = False
        self.lock = threading.RLock()
        if create:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); os.close(fd)
            with self.connection() as db:
                db.executescript('''
                    CREATE TABLE policy(body BLOB NOT NULL);
                    CREATE TABLE sessions(session TEXT PRIMARY KEY,issue TEXT NOT NULL,thread TEXT UNIQUE,lineage TEXT);
                    CREATE TABLE turns(dispatch TEXT PRIMARY KEY,session TEXT NOT NULL REFERENCES sessions(session),
                        issue TEXT NOT NULL,request BLOB NOT NULL,digest TEXT NOT NULL,
                        state TEXT NOT NULL,thread TEXT,turn TEXT,result TEXT,reason TEXT);
                    CREATE UNIQUE INDEX one_issue_executor ON turns(issue)
                        WHERE state IN ('preparing','running','uncertain','interrupt_requested');
                    CREATE UNIQUE INDEX one_workspace_executor ON turns((1))
                        WHERE state IN ('preparing','running','uncertain','interrupt_requested');
                    CREATE TABLE events(sequence INTEGER PRIMARY KEY,dispatch TEXT,body BLOB NOT NULL);
                ''')
                db.execute('INSERT INTO policy VALUES(?)', (encoded(self.policy),))
        with self.connection() as db:
            if db.execute('SELECT body FROM policy').fetchone()[0] != encoded(self.policy):
                raise ValueError('installed policy differs; retain journal and reconcile migration')
        lock_path = self.root / 'runtime.lock'
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            private(lock_path)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise ValueError('another adapter owns this runtime journal or lock is unsafe') from None
        self.journal_lock = fd
        with self.connection() as db:
            # A new process must not rerun a dispatched turn after losing its stream.
            db.execute("UPDATE turns SET state='uncertain',reason='adapter restarted; runtime reconciliation required' "
                       "WHERE state IN ('preparing','running','interrupt_requested')")

    @contextmanager
    def connection(self):
        private(self.path)
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL'); db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db; db.commit()
        except BaseException: db.rollback(); raise
        finally: db.close()

    def _client(self):
        if self.closed: raise ValueError('runtime adapter closed')
        if self.client is None:
            self.client = self.client_factory(self.policy['binary'], self.policy['cwd'])
        return self.client

    def validate(self, value):
        if type(value) is not dict or set(value) != {'contract','dispatch_id','organization_id',
                'app_user_id','session_id','issue_id','message','binding'} or value['contract'] != 'codex-dispatch.v1':
            raise ValueError('exact admitted dispatch required')
        for key in ('dispatch_id','organization_id','app_user_id','session_id','issue_id'): identifier(value[key])
        if (value['organization_id'] != self.policy['organization_id'] or
                value['app_user_id'] != self.policy['app_user_id'] or
                value['issue_id'] not in self.policy['issues'] or
                value['binding'] != self.policy['issues'][value['issue_id']]):
            raise ValueError('wrong app, organization, issue or architecture context')
        bounded(value['message'])
        if not self.policy['execution_authorized']:
            raise ValueError('runtime execution not authorized by installed operator policy')
        return json.loads(encoded(value))

    def dispatch(self, value):
        value = self.validate(value); raw = encoded(value); digest = hashlib.sha256(raw).hexdigest()
        dispatch, session, issue = (value[k] for k in ('dispatch_id','session_id','issue_id'))
        with self.lock:
            if self.closed: raise ValueError('runtime adapter closed')
            self.collect()
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                existing = db.execute('SELECT * FROM turns WHERE dispatch=?', (dispatch,)).fetchone()
                if existing:
                    if existing['digest'] != digest: raise ValueError('dispatch identity changed')
                    return self._public(existing)
                prior = db.execute('SELECT * FROM sessions WHERE session=?', (session,)).fetchone()
                if prior and prior['issue'] != issue: raise ValueError('session issue cannot change')
                if not prior: db.execute('INSERT INTO sessions(session,issue) VALUES(?,?)', (session, issue))
                try:
                    db.execute('INSERT INTO turns(dispatch,session,issue,request,digest,state) VALUES(?,?,?,?,?,?)',
                               (dispatch, session, issue, raw, digest, 'preparing'))
                except sqlite3.IntegrityError:
                    raise ValueError('workspace has an active or uncertain executor; reconcile first') from None
            try:
                client = self._client()
                if prior and prior['thread']:
                    info = client.call('thread/resume', dict(threadId=prior['thread'],
                        cwd=self.policy['cwd'], sandbox=self.policy['sandbox'], approvalPolicy='on-request'))['thread']
                    if info['id'] != prior['thread']: raise ValueError('runtime thread changed')
                else:
                    info = client.call('thread/start', dict(cwd=self.policy['cwd'],
                        sandbox=self.policy['sandbox'], approvalPolicy='on-request', ephemeral=False))['thread']
                thread = bounded(info['id'], 256); lineage = bounded(info.get('sessionId', thread), 256)
                with self.connection() as db:
                    db.execute('UPDATE sessions SET thread=?,lineage=? WHERE session=?', (thread,lineage,session))
                    db.execute('UPDATE turns SET thread=? WHERE dispatch=?', (thread,dispatch))
                context = 'Pinned engineering context (not additional authority):\n' + encoded(value['binding']).decode()
                response = client.call('turn/start', dict(threadId=thread,
                    input=[dict(type='text',text=context+'\nOperator/session request:\n'+value['message'])]))
                turn = bounded(response['turn']['id'], 256)
                with self.connection() as db:
                    db.execute("UPDATE turns SET turn=?,state='running' WHERE dispatch=?", (turn,dispatch))
                self.collect()
            except (ValueError, OSError, KeyError, TypeError):
                with self.connection() as db:
                    db.execute("UPDATE turns SET state='uncertain',reason='runtime dispatch outcome requires reconciliation' WHERE dispatch=?", (dispatch,))
                raise ValueError('runtime dispatch uncertain; retain dispatch ID and reconcile') from None
            return self.status(dispatch)

    @staticmethod
    def _public(row):
        return {k:row[k] for k in ('dispatch','session','issue','state','thread','turn','result','reason')}

    def collect(self):
        if self.client is None: return
        for event in self.client.events():
            raw = encoded(event)
            if len(raw) > MAX_FRAME: raise ValueError('runtime event exceeds bound')
            params = event.get('params') or {}
            with self.connection() as db:
                row = db.execute('SELECT * FROM turns WHERE thread=? AND turn=?',
                    (params.get('threadId'), params.get('turnId') or (params.get('turn') or {}).get('id'))).fetchone()
                dispatch = row['dispatch'] if row else None
                db.execute('INSERT INTO events(dispatch,body) VALUES(?,?)', (dispatch,raw))
                if not row: continue
                if event.get('method') == 'item/completed':
                    item = params.get('item') or {}
                    if item.get('type') == 'agentMessage':
                        text = bounded(item.get('text'), MAX_MESSAGE)
                        db.execute('UPDATE turns SET result=? WHERE dispatch=?', (text,dispatch))
                elif event.get('method') == 'turn/completed':
                    state = (params.get('turn') or {}).get('status')
                    state = state if state in ('completed','failed','interrupted') else 'uncertain'
                    db.execute('UPDATE turns SET state=? WHERE dispatch=?', (state,dispatch))
        if getattr(self.client, 'closed', False):
            with self.connection() as db:
                db.execute("UPDATE turns SET state='uncertain',reason='runtime stream unavailable' WHERE state IN ('preparing','running','interrupt_requested')")

    def status(self, dispatch):
        identifier(dispatch)
        with self.lock:
            if self.closed: raise ValueError('runtime adapter closed')
            self.collect()
            with self.connection() as db:
                row = db.execute('SELECT * FROM turns WHERE dispatch=?', (dispatch,)).fetchone()
                if not row: raise ValueError('unknown dispatch')
            if row['state']=='uncertain' and row['thread'] and row['turn']:
                self._reconcile(row)
                with self.connection() as db:
                    row=db.execute('SELECT * FROM turns WHERE dispatch=?',(dispatch,)).fetchone()
            return self._public(row)

    def _reconcile(self, row):
        """Read only the retained thread and accept only the exact saved turn.

        An unacknowledged turn/start with no retained turn ID cannot be inferred
        from whichever turn happens to be latest. It remains uncertain.
        """
        try:
            if self.client is not None and getattr(self.client,'closed',False):
                self.client.close();self.client=None
            thread=self._client().call('thread/read',dict(threadId=row['thread'],includeTurns=True))['thread']
            if (type(thread) is not dict or thread.get('id')!=row['thread'] or
                    thread.get('cwd')!=self.policy['cwd']):
                raise ValueError('stored thread context differs')
            turns=thread.get('turns',[])
            if type(turns) is not list or any(type(t) is not dict for t in turns):
                raise ValueError('stored turn list differs')
            matches=[t for t in turns if t.get('id')==row['turn']]
            if len(matches)!=1 or matches[0].get('status') not in ('completed','failed','interrupted'):
                return
            turn=matches[0];result=None
            items=turn.get('items',[])
            if type(items) is not list or any(type(i) is not dict for i in items):
                raise ValueError('stored items differ')
            for item in items:
                if item.get('type')=='agentMessage' and item.get('text'):
                    result=bounded(item['text'],MAX_MESSAGE)
            evidence=dict(method='adapter/reconciled',params=dict(threadId=row['thread'],
                turnId=row['turn'],status=turn['status'],stored_turn_sha256=hashlib.sha256(encoded(turn)).hexdigest()))
            with self.connection() as db:
                db.execute('INSERT INTO events(dispatch,body) VALUES(?,?)',(row['dispatch'],encoded(evidence)))
                db.execute("UPDATE turns SET state=?,result=coalesce(?,result),reason=? WHERE dispatch=? AND state='uncertain'",
                    (turn['status'],result,'reconciled exact stored runtime turn'+
                     ('; final response unavailable' if result is None else ''),row['dispatch']))
        except (ValueError,OSError,KeyError,TypeError):
            # A failed read does not authorize a resume, a new turn or a guessed
            # completion. Keep the original frozen dispatch available for audit.
            return

    def interrupt(self, dispatch):
        with self.lock:
            row = self.status(dispatch)
            if row['state'] in ('completed','failed','interrupted'): return row
            if row['state'] not in ('running','interrupt_requested') or self.client is None:
                raise ValueError('cannot confirm active runtime turn; reconcile first')
            with self.connection() as db:
                db.execute("UPDATE turns SET state='interrupt_requested' WHERE dispatch=?", (dispatch,))
            try: self.client.call('turn/interrupt', dict(threadId=row['thread'], turnId=row['turn']))
            except (ValueError, OSError):
                with self.connection() as db:
                    db.execute("UPDATE turns SET state='uncertain',reason='interrupt outcome unconfirmed' WHERE dispatch=?", (dispatch,))
            return self.status(dispatch)

    def close(self):
        with self.lock:
            if self.closed: return
            if self.client: self.client.close()
            self.collect()
            if self.journal_lock is not None:
                os.close(self.journal_lock); self.journal_lock = None
            self.closed = True
