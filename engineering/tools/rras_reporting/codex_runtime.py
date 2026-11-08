"""Private Codex App Server adapter. No Linear OAuth, webhooks, or work scheduler.

The journal records runtime dispatch uncertainty; n8n owns transport delivery.
Only the fixed, operator-installed policy selects a runtime and work context.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import select
import socket
import sqlite3
import stat
import subprocess
import threading
import time
import uuid

MAX_MESSAGE = 64 * 1024
MAX_FRAME = 1024 * 1024


class ExecutionNotAuthorized(ValueError):
    code='execution_not_authorized_before_dispatch'


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode()


def identifier(value):
    if type(value) is not str or str(uuid.UUID(value)) != value:
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


def visible_message(item):
    return (type(item) is dict and item.get('type')=='agentMessage' and
        item.get('channel',item.get('phase')) not in ('analysis','reasoning'))


def journal_event(event):
    """Runtime lifecycle journal, not a transcript or reasoning archive.

    Drop token/delta noise before the bounded queue and project terminal frames
    without their nested items (which can contain explicit reasoning payloads).
    Full visible exchanges are captured separately by selected-source adapters.
    """
    if type(event) is not dict:return None
    method=event.get('method');params=event.get('params') or {}
    if type(params) is not dict:return None
    if method=='thread/tokenUsage/updated':
        value=params.get('tokenUsage');counters={}
        if type(value) is not dict:return None
        for name in ('threadId','turnId'):
            if type(params.get(name)) is not str or not 1<=len(params[name])<=256:return None
        names=('inputTokens','outputTokens','cachedInputTokens','cacheWriteInputTokens','reasoningOutputTokens','totalTokens')
        for label in ('total','last'):
            raw=value.get(label)
            if type(raw) is not dict or not {'inputTokens','outputTokens','cachedInputTokens'}<=set(raw):return None
            clean={key:raw[key] for key in names if key in raw}
            if any(type(number) is not int or not 0<=number<2**53 for number in clean.values()):return None
            counters[label]=clean
        return dict(method=method,params=dict(threadId=params['threadId'],turnId=params['turnId'],tokenUsage=counters))
    if method=='adapter/approvalRequired':
        return dict(method=method,params={k:params[k] for k in ('method','request_id') if k in params})
    if method=='item/completed' and visible_message(params.get('item')):
        item=params['item']
        return dict(method=method,params=dict(threadId=params.get('threadId'),turnId=params.get('turnId'),
            item={k:item[k] for k in ('id','type','text','phase') if k in item}))
    if method=='turn/completed' and type(params.get('turn')) is dict:
        return dict(method=method,params=dict(threadId=params.get('threadId'),turnId=params.get('turnId'),
            turn={k:params['turn'][k] for k in ('id','status') if k in params['turn']}))
    return None


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
    READ_FRAME_LIMIT=MAX_FRAME
    def __init__(self, executable, cwd, *, timeout=15,codex_home=None):
        self._setup(timeout)
        # This stdio launcher is for isolated fixtures. Production uses the
        # socket-activated native account, without the adapter's files/identity.
        env = {k: os.environ[k] for k in ('HOME', 'PATH', 'LANG', 'CODEX_HOME') if k in os.environ}
        if codex_home is not None:
            home=private(codex_home,True);env.update(CODEX_HOME=str(home),HOME=str(home.parent))
        self.process = subprocess.Popen([executable, 'app-server'], cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.reader_stream=self.process.stdout;self.writer_stream=self.process.stdin
        self._initialize()

    def _setup(self,timeout):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.pending = {}
        self.notifications = queue.Queue(maxsize=128)
        self.sequence = 0
        self.closed = False

    def _initialize(self):
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
        self.writer_stream.write(raw); self.writer_stream.flush()

    def _read(self):
        try:
            while True:
                raw = self.reader_stream.readline(self.READ_FRAME_LIMIT + 1)
                if not raw or len(raw) > self.READ_FRAME_LIMIT or not raw.endswith(b'\n'):
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
                    projected=journal_event(message)
                    if projected is not None:self.notifications.put_nowait(projected)
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


def history_unix():
    import importlib.util
    spec=importlib.util.spec_from_file_location('runtime_unix_framing',Path(__file__).parents[1]/'rras_history/unix.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


class SocketAppServer(AppServer):
    """Native stdio RPC over a protected systemd-accepted Unix stream.

    The listening socket is owned by the adapter and has an exact expected peer
    UID (normally root/systemd). Its accepted service runs as the separate coding
    account. No bridge credential or adapter journal is mounted into that account.
    """
    def __init__(self,path,peer_uid,*,timeout=15):
        if type(peer_uid) is not int or not 0<=peer_uid<2**32-1:raise ValueError('exact native listener identity required')
        u=history_unix();path=u.endpoint(path);u.parents(path,os.getuid());info=path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('private adapter-owned native socket required')
        self._setup(timeout);self.connection_socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            self.connection_socket.settimeout(5);self.connection_socket.connect(str(path))
            if u.peer(self.connection_socket)!=peer_uid:raise ValueError('native listener identity differs')
            self.connection_socket.settimeout(None);self.reader_stream=self.connection_socket.makefile('rb')
            self._initialize()
        except BaseException:
            self.connection_socket.close();raise

    def _write(self,value):
        raw=encoded(value)
        if len(raw)>MAX_FRAME:raise ValueError('runtime frame too large')
        pending=memoryview(raw);deadline=time.monotonic()+5
        while pending:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([],[self.connection_socket],[],remaining)[1]:raise TimeoutError('native write unavailable')
            try:sent=self.connection_socket.send(pending,socket.MSG_DONTWAIT)
            except BlockingIOError:continue
            if sent<=0:raise OSError('native stream ended')
            pending=pending[sent:]

    def close(self):
        self.closed=True
        try:self.connection_socket.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        if hasattr(self,'reader'):self.reader.join(timeout=3)
        if hasattr(self,'reader_stream'):self.reader_stream.close()
        self.connection_socket.close()


class Runtime:
    """Durable dispatch results and issue ownership, isolated from transport queues."""
    def __init__(self, root, selected_policy, *, create=False, client_factory=AppServer,reporter=None,checkpoint_tool=None):
        self.policy = policy(selected_policy)
        self.root = Path(root)
        if create: self.root.mkdir(mode=0o700, parents=False, exist_ok=False)
        private(self.root, True)
        self.path = self.root / 'runtime.sqlite3'
        self.client_factory = client_factory
        self.reporter=reporter
        self.checkpoint_tool=checkpoint_tool
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
        if self.reporter is not None:
            with self.connection() as db:pending=[r[0] for r in db.execute("SELECT dispatch FROM turns WHERE state='uncertain'")]
            for dispatch in pending:self._report(dispatch)

    def _report(self,dispatch):
        if self.reporter is None:return
        try:self.reporter.observe(self,dispatch)
        except Exception:
            # Reporting is passive. A local spool failure must not repeat or
            # revoke an otherwise authorized in-scope coding turn. Retain an
            # explicit gap in the runtime journal without source exception text.
            event=dict(method='adapter/reportingGap',params=dict(dispatch=dispatch,
                detail='Runtime history staging unconfirmed; retain native journal and selected source.'))
            with self.connection() as db:
                prior=db.execute('SELECT body FROM events WHERE dispatch=? ORDER BY sequence DESC LIMIT 1',(dispatch,)).fetchone()
                if not prior or prior[0]!=encoded(event):db.execute('INSERT INTO events(dispatch,body) VALUES(?,?)',(dispatch,encoded(event)))

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
        required={'contract','dispatch_id','organization_id','app_user_id','session_id','issue_id','message','binding'}
        if type(value) is not dict or not required<=set(value) or set(value)-required-{'incoming_handoff'} or value['contract'] != 'codex-dispatch.v1':
            raise ValueError('exact admitted dispatch required')
        for key in ('dispatch_id','organization_id','app_user_id','session_id','issue_id'): identifier(value[key])
        if (value['organization_id'] != self.policy['organization_id'] or
                value['app_user_id'] != self.policy['app_user_id'] or
                value['issue_id'] not in self.policy['issues'] or
                value['binding'] != self.policy['issues'][value['issue_id']]):
            raise ValueError('wrong app, organization, issue or architecture context')
        bounded(value['message'])
        if 'incoming_handoff' in value:
            selected=self.reporter.configuration.get('handoff') if self.reporter is not None else None
            if selected is None:raise ValueError('installed handoff policy required')
            spec=importlib.util.spec_from_file_location('runtime_incoming_handoff',Path(__file__).with_name('runtime_handoff.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.incoming(value['incoming_handoff'],selected['policy'],value['issue_id'],value['session_id'])
        if not self.policy['execution_authorized']:
            raise ExecutionNotAuthorized('runtime execution not authorized by installed operator policy')
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
            self._report(dispatch)
            try:
                client = self._client()
                checkpoint_parameters=self.checkpoint_tool.parameters(session,dispatch) if self.checkpoint_tool is not None else {}
                if self.reporter is not None:
                    instructions=self.reporter.task_instructions(issue)
                    if instructions:checkpoint_parameters['developerInstructions']=checkpoint_parameters.get('developerInstructions','')+instructions
                if prior and prior['thread']:
                    opened = client.call('thread/resume', dict(threadId=prior['thread'],
                        cwd=self.policy['cwd'], sandbox=self.policy['sandbox'], approvalPolicy='on-request',**checkpoint_parameters))
                    info=opened['thread']
                    if info['id'] != prior['thread']: raise ValueError('runtime thread changed')
                else:
                    opened = client.call('thread/start', dict(cwd=self.policy['cwd'],
                        sandbox=self.policy['sandbox'], approvalPolicy='on-request', ephemeral=False,**checkpoint_parameters))
                    info=opened['thread']
                thread = bounded(info['id'], 256); lineage = bounded(info['sessionId'],256) if info.get('sessionId') else None
                if info.get('cwd') is not None and info['cwd']!=self.policy['cwd']:raise ValueError('native workspace differs')
                with self.connection() as db:
                    db.execute('UPDATE sessions SET thread=?,lineage=? WHERE session=?', (thread,lineage,session))
                    db.execute('UPDATE turns SET thread=? WHERE dispatch=?', (thread,dispatch))
                    metadata={k:info[k] for k in ('id','sessionId','parentThreadId','forkedFromId','path','cwd','cliVersion','model','modelProvider','gitInfo','createdAt','updatedAt') if k in info}
                    for field in ('model','modelProvider'):
                        if type(opened.get(field)) is str:metadata[field]=opened[field]
                    raw_metadata=encoded(dict(method='adapter/threadMetadata',params=metadata))
                    if len(raw_metadata)<=16384:db.execute('INSERT INTO events(dispatch,body) VALUES(?,?)',(dispatch,raw_metadata))
                self._report(dispatch)
                if self.checkpoint_tool is not None and not self.checkpoint_tool.verify_inventory(client,thread):
                    with self.connection() as db:db.execute('INSERT INTO events(dispatch,body) VALUES(?,?)',(dispatch,
                        encoded(dict(method='adapter/reportingGap',params=dict(detail='Scoped checkpoint tool unavailable; automatic lifecycle reporting and selected capture remain independent.')))))
                context = 'Pinned engineering context (not additional authority):\n' + encoded(value['binding']).decode()
                response = client.call('turn/start', dict(threadId=thread,
                    input=[dict(type='text',text=context+'\nOperator/session request:\n'+value['message'])]))
                turn = bounded(response['turn']['id'], 256)
                with self.connection() as db:
                    db.execute("UPDATE turns SET turn=?,state='running' WHERE dispatch=?", (turn,dispatch))
                self._report(dispatch)
                self.collect()
            except (ValueError, OSError, KeyError, TypeError):
                with self.connection() as db:
                    db.execute("UPDATE turns SET state='uncertain',reason='runtime dispatch outcome requires reconciliation' WHERE dispatch=?", (dispatch,))
                self._report(dispatch)
                raise ValueError('runtime dispatch uncertain; retain dispatch ID and reconcile') from None
            return self.status(dispatch)

    @staticmethod
    def _public(row):
        value={k:row[k] for k in ('dispatch','session','issue','state','thread','turn','result','reason')}
        if value['result'] is not None:
            import importlib.util
            spec=importlib.util.spec_from_file_location('runtime_public_redaction',Path(__file__).parents[1]/'rras_history/redaction.py')
            redaction=importlib.util.module_from_spec(spec);spec.loader.exec_module(redaction)
            value['result']=redaction.redact(value['result'].encode())[0].decode()
        return value

    def collect(self):
        if self.client is None: return
        changed=set()
        for event in self.client.events():
            event=journal_event(event)
            if event is None:continue
            raw = encoded(event)
            if len(raw) > MAX_FRAME: raise ValueError('runtime event exceeds bound')
            params = event.get('params') or {}
            with self.connection() as db:
                row = db.execute('SELECT * FROM turns WHERE thread=? AND turn=?',
                    (params.get('threadId'), params.get('turnId') or (params.get('turn') or {}).get('id'))).fetchone()
                dispatch = row['dispatch'] if row else None
                db.execute('INSERT INTO events(dispatch,body) VALUES(?,?)', (dispatch,raw))
                if not row: continue
                changed.add(dispatch)
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
                changed.update(r[0] for r in db.execute("SELECT dispatch FROM turns WHERE state IN ('preparing','running','interrupt_requested')"))
                db.execute("UPDATE turns SET state='uncertain',reason='runtime stream unavailable' WHERE state IN ('preparing','running','interrupt_requested')")
        for dispatch in changed:self._report(dispatch)

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
            self._report(dispatch)
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
                if visible_message(item) and item.get('text'):
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
