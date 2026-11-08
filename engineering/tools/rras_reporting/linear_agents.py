"""Two separately authenticated Linear agent inboxes; passive, durable and bounded.

No model runner, credential forwarding, history database mutation, or automatic
execution/retry. A supervisor binds each admitted message to an authorized runtime.
Schema basis: Linear's published AgentSessionEventWebhookPayload and GraphQL SDK.
"""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid

MAX_BODY = 256 * 1024
MAX_TEXT = 64 * 1024
MAX_EVENTS = 10000
ROLE_NAMES = {'jarvis', 'codex'}


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()


def decode(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BODY:
        raise ValueError('bounded JSON required')
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid number')))
    pending = [(value, 0)]
    while pending:
        child, depth = pending.pop()
        if depth > 24: raise ValueError('bounded nesting required')
        if isinstance(child, str) and '\0' in child: raise ValueError('NUL refused')
        if isinstance(child, dict): pending.extend((v, depth + 1) for v in child.values())
        if isinstance(child, list): pending.extend((v, depth + 1) for v in child)
    return value


def identifier(value):
    if type(value) is not str:
        raise ValueError('canonical UUID required')
    try: valid = str(uuid.UUID(value)) == value
    except (ValueError, AttributeError): valid = False
    if not valid: raise ValueError('canonical UUID required')
    return value


def text(value):
    if type(value) is not str or not value.strip() or len(value.encode()) > MAX_TEXT or '\0' in value:
        raise ValueError('bounded message text required')
    return value


def private_file(path, maximum=MAX_BODY):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path: raise ValueError('canonical private path required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('caller-owned private regular file required')
        data = stream.read(maximum + 1)
        if len(data) > maximum: raise ValueError('private file too large')
        return data


def policy(value):
    if type(value) is not dict or set(value) != {'contract', 'organization_id', 'agents', 'issues'}:
        raise ValueError('exact agent policy required')
    if value['contract'] != 'linear-agent-policy.v1': raise ValueError('unknown policy')
    identifier(value['organization_id'])
    if type(value['agents']) is not dict or set(value['agents']) != ROLE_NAMES:
        raise ValueError('two named agents required')
    actors, clients, secrets, tokens = set(), set(), set(), set()
    for name, agent in value['agents'].items():
        if type(agent) is not dict or set(agent) != {'app_user_id', 'oauth_client_id', 'webhook_secret_file', 'access_token_file'}:
            raise ValueError('exact scoped app binding required')
        actors.add(identifier(agent['app_user_id'])); clients.add(identifier(agent['oauth_client_id']))
        for key in ('webhook_secret_file', 'access_token_file'):
            path = Path(agent[key])
            if not path.is_absolute() or path.resolve(strict=False) != path: raise ValueError('canonical credential path required')
        secrets.add(agent['webhook_secret_file']); tokens.add(agent['access_token_file'])
    if min(len(values) for values in [actors, clients, secrets, tokens]) != 2 or secrets & tokens:
        raise ValueError('distinct actor/client/credential bindings required')
    if type(value['issues']) is not dict or not 1 <= len(value['issues']) <= 4096:
        raise ValueError('explicit issue bindings required')
    for issue_id, binding in value['issues'].items():
        identifier(issue_id)
        if type(binding) is not dict or set(binding) != {'project_id', 'work_id', 'work_revision_sha256',
                'architecture_version', 'architecture_sha256', 'plan_id'}:
            raise ValueError('exact work and architecture binding required')
        for field, prefix in [('project_id', 'prj_'), ('work_id', 'wrk_')]:
            if not re.fullmatch(prefix + '[0-9a-f]{32}', binding[field]): raise ValueError('invalid history identity')
        for key in ('work_revision_sha256', 'architecture_sha256'):
            if not re.fullmatch('[0-9a-f]{64}', binding[key]): raise ValueError('exact digest required')
        if type(binding['architecture_version']) is not int or binding['architecture_version'] < 1:
            raise ValueError('positive architecture version required')
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', binding['plan_id']): raise ValueError('plan ID required')
    return decode(encoded(value))


class Inbox:
    def __init__(self, root, selected_policy, *, create=False):
        self.policy = policy(selected_policy)
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.resolve(strict=False) != self.root:
            raise ValueError('canonical inbox root required')
        if create: self.root.mkdir(mode=0o700, parents=False, exist_ok=False)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private inbox root required')
        self.path = self.root / 'inbox.sqlite3'
        if create:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
            with self.connection() as db:
                db.executescript('''
                    CREATE TABLE configuration(policy BLOB NOT NULL);
                    CREATE TABLE messages(sequence INTEGER PRIMARY KEY,agent TEXT NOT NULL,delivery TEXT NOT NULL,
                        source_key TEXT NOT NULL,sha256 TEXT NOT NULL,raw BLOB NOT NULL,envelope BLOB NOT NULL,
                        UNIQUE(agent,delivery),UNIQUE(agent,source_key));
                    CREATE TABLE sessions(agent TEXT NOT NULL,session TEXT NOT NULL,issue TEXT NOT NULL,
                        PRIMARY KEY(agent,session));
                    CREATE TABLE bindings(agent TEXT NOT NULL,session TEXT NOT NULL,runtime TEXT NOT NULL,
                        PRIMARY KEY(agent,session));
                    CREATE TABLE publication_attempts(agent TEXT NOT NULL,key TEXT NOT NULL,PRIMARY KEY(agent,key));
                    CREATE TABLE publication_receipts(agent TEXT NOT NULL,key TEXT NOT NULL,body BLOB NOT NULL,PRIMARY KEY(agent,key));
                    CREATE TRIGGER publication_attempts_no_update BEFORE UPDATE ON publication_attempts BEGIN SELECT RAISE(ABORT,'immutable attempt'); END;
                    CREATE TRIGGER publication_attempts_no_delete BEFORE DELETE ON publication_attempts BEGIN SELECT RAISE(ABORT,'retain uncertain attempt'); END;
                    CREATE TRIGGER publication_receipts_no_update BEFORE UPDATE ON publication_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
                    CREATE TRIGGER publication_receipts_no_delete BEFORE DELETE ON publication_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
                    CREATE TABLE handoffs(id TEXT PRIMARY KEY,sender TEXT NOT NULL,target TEXT NOT NULL,issue TEXT NOT NULL,
                        source_session TEXT NOT NULL,body BLOB NOT NULL);
                    CREATE TABLE handoff_events(id TEXT NOT NULL,state TEXT NOT NULL,body BLOB NOT NULL,PRIMARY KEY(id,state));
                    CREATE TRIGGER handoffs_no_update BEFORE UPDATE ON handoffs BEGIN SELECT RAISE(ABORT,'immutable handoff'); END;
                    CREATE TRIGGER handoffs_no_delete BEFORE DELETE ON handoffs BEGIN SELECT RAISE(ABORT,'immutable handoff'); END;
                    CREATE TRIGGER handoff_events_no_update BEFORE UPDATE ON handoff_events BEGIN SELECT RAISE(ABORT,'immutable handoff state'); END;
                    CREATE TRIGGER handoff_events_no_delete BEFORE DELETE ON handoff_events BEGIN SELECT RAISE(ABORT,'immutable handoff state'); END;
                    CREATE TABLE activities(agent TEXT NOT NULL,key TEXT NOT NULL,sha256 TEXT NOT NULL,request BLOB NOT NULL,
                        PRIMARY KEY(agent,key));
                    CREATE TRIGGER messages_no_update BEFORE UPDATE ON messages BEGIN SELECT RAISE(ABORT,'immutable message'); END;
                    CREATE TRIGGER messages_no_delete BEFORE DELETE ON messages BEGIN SELECT RAISE(ABORT,'immutable message'); END;
                    CREATE TRIGGER bindings_no_update BEFORE UPDATE ON bindings BEGIN SELECT RAISE(ABORT,'immutable runtime binding'); END;
                    CREATE TRIGGER bindings_no_delete BEFORE DELETE ON bindings BEGIN SELECT RAISE(ABORT,'immutable runtime binding'); END;
                    CREATE TRIGGER activities_no_update BEFORE UPDATE ON activities BEGIN SELECT RAISE(ABORT,'immutable activity'); END;
                    CREATE TRIGGER activities_no_delete BEFORE DELETE ON activities BEGIN SELECT RAISE(ABORT,'immutable activity'); END;
                    CREATE TRIGGER configuration_no_update BEFORE UPDATE ON configuration BEGIN SELECT RAISE(ABORT,'fixed policy'); END;
                    CREATE TRIGGER configuration_no_delete BEFORE DELETE ON configuration BEGIN SELECT RAISE(ABORT,'fixed policy'); END;
                ''')
                db.execute('INSERT INTO configuration VALUES(?)', (encoded(self.policy),))
        with self.connection() as db:
            if db.execute('SELECT policy FROM configuration').fetchone()[0] != encoded(self.policy):
                raise ValueError('inbox policy differs; retain existing state')

    @contextmanager
    def connection(self):
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private inbox database required')
        db = sqlite3.connect(self.path, timeout=3)
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally: db.close()

    def receive(self, agent, raw, headers, *, now=None):
        if agent not in ROLE_NAMES: raise ValueError('unknown agent')
        if type(raw) is not bytes or len(raw) > MAX_BODY: raise ValueError('bounded body required')
        config = self.policy['agents'][agent]
        secret = private_file(config['webhook_secret_file'], 4096).strip()
        if len(secret) < 24: raise ValueError('webhook secret not configured')
        headers = {k.lower(): v for k, v in headers.items()}
        signature = headers.get('linear-signature', '')
        if not re.fullmatch('[0-9a-f]{64}', signature) or not hmac.compare_digest(signature, hmac.new(secret, raw, hashlib.sha256).hexdigest()):
            raise ValueError('webhook refused')
        body = decode(raw)
        stamp = body.get('webhookTimestamp')
        if type(stamp) not in (int, float) or abs(stamp / 1000 - (time.time() if now is None else now)) > 60:
            raise ValueError('stale webhook')
        delivery = identifier(headers.get('linear-delivery'))
        if body.get('type') != 'AgentSessionEvent' or body.get('action') not in ('created', 'prompted'):
            raise ValueError('unsupported agent event')
        if body.get('organizationId') != self.policy['organization_id'] or body.get('appUserId') != config['app_user_id'] or body.get('oauthClientId') != config['oauth_client_id']:
            raise ValueError('wrong organization or app')
        session = body.get('agentSession', {})
        session_id = identifier(session.get('id'))
        if session.get('appUserId') != config['app_user_id'] or session.get('organizationId') != self.policy['organization_id']:
            raise ValueError('session belongs to another app')
        issue_id = identifier(session.get('issueId'))
        if issue_id not in self.policy['issues']: raise ValueError('unbound issue')
        activity = body.get('agentActivity') or {}
        if body['action'] == 'created':
            message = text(body.get('promptContext'))
            source_key = 'created:' + session_id
            source_actor = session.get('creatorId')
        else:
            content = activity.get('content') or {}
            if content.get('type') != 'prompt' or activity.get('agentSessionId') != session_id:
                raise ValueError('only a directed user prompt is admitted')
            source_actor = activity.get('userId')
            if source_actor in {v['app_user_id'] for v in self.policy['agents'].values()}:
                raise ValueError('agent echo is not a user prompt')
            identifier(source_actor)
            message = text(content.get('body'))
            source_key = 'prompt:' + identifier(activity.get('id'))
        envelope = dict(contract='linear-agent-message.v1', agent=agent, app_user_id=config['app_user_id'],
            organization_id=self.policy['organization_id'], linear_session_id=session_id, issue_id=issue_id,
            source_key=source_key, source_actor_id=source_actor, message=message,
            binding=self.policy['issues'][issue_id], signal=activity.get('signal'),
            execution_authorized=False, human_approval_inferred=False)
        sha = hashlib.sha256(raw).hexdigest()
        content_sha = hashlib.sha256(encoded(envelope)).hexdigest()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            duplicate = db.execute('SELECT sequence,sha256 FROM messages WHERE agent=? AND delivery=?', (agent, delivery)).fetchone()
            if duplicate:
                if duplicate[1] != sha: raise ValueError('delivery changed')
                return dict(accepted=True, inserted=False, sequence=duplicate[0], agent=agent)
            prior = db.execute('SELECT sequence,envelope FROM messages WHERE agent=? AND source_key=?', (agent, source_key)).fetchone()
            if prior:
                if hashlib.sha256(prior[1]).hexdigest() != content_sha: raise ValueError('source event changed')
                return dict(accepted=True, inserted=False, sequence=prior[0], agent=agent)
            existing = db.execute('SELECT issue FROM sessions WHERE agent=? AND session=?', (agent, session_id)).fetchone()
            if existing and existing[0] != issue_id: raise ValueError('session issue changed')
            if body['action'] == 'prompted' and not existing: raise ValueError('initial session event must be reconciled first')
            if db.execute('SELECT COUNT(*) FROM messages').fetchone()[0] >= MAX_EVENTS: raise ValueError('inbox full')
            db.execute('INSERT OR IGNORE INTO sessions VALUES(?,?,?)', (agent, session_id, issue_id))
            cursor = db.execute('INSERT INTO messages(agent,delivery,source_key,sha256,raw,envelope) VALUES(?,?,?,?,?,?)',
                (agent, delivery, source_key, sha, raw, encoded(envelope)))
            return dict(accepted=True, inserted=True, sequence=cursor.lastrowid, agent=agent)

    def messages(self, agent, *, after=0, limit=20):
        if agent not in ROLE_NAMES or type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('bounded agent cursor required')
        with self.connection() as db:
            rows = db.execute('SELECT sequence,envelope FROM messages WHERE agent=? AND sequence>? ORDER BY sequence LIMIT ?',
                (agent, after, limit)).fetchall()
        return [dict(sequence=sequence, **decode(raw)) for sequence, raw in rows]

    def bind_runtime(self, agent, session_id, runtime_session_id):
        identifier(session_id); text(runtime_session_id)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM sessions WHERE agent=? AND session=?', (agent, session_id)).fetchone():
                raise ValueError('unknown agent session')
            old = db.execute('SELECT runtime FROM bindings WHERE agent=? AND session=?', (agent, session_id)).fetchone()
            if old and old[0] != runtime_session_id: raise ValueError('runtime session binding changed')
            db.execute('INSERT OR IGNORE INTO bindings VALUES(?,?,?)', (agent, session_id, runtime_session_id))
        return dict(agent=agent, linear_session_id=session_id, runtime_session_id=runtime_session_id)

    def activity(self, agent, session_id, key, kind, body):
        identifier(session_id); text(key); text(body)
        if len(key) > 128 or kind not in ('thought', 'response', 'elicitation', 'error'):
            raise ValueError('bounded supported activity required')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM bindings WHERE agent=? AND session=?', (agent, session_id)).fetchone():
                raise ValueError('runtime session must be bound before replies')
            old = db.execute('SELECT request FROM activities WHERE agent=? AND key=?', (agent, key)).fetchone()
            if old:
                previous = decode(old[0])
                if previous['variables']['input']['content'] != dict(type=kind, body=body) or previous['variables']['input']['agentSessionId'] != session_id:
                    raise ValueError('activity key changed')
                return previous
            request = dict(query='mutation ReportingActivity($input: AgentActivityCreateInput!) { agentActivityCreate(input: $input) { success agentActivity { id } } }',
                variables={'input': dict(id=str(uuid.uuid4()), agentSessionId=session_id, content=dict(type=kind, body=body))})
            raw = encoded(request)
            db.execute('INSERT INTO activities VALUES(?,?,?,?)', (agent, key, hashlib.sha256(raw).hexdigest(), raw))
        return request


    def handoff(self, sender, session_id, target, key, summary):
        identifier(session_id); text(key); text(summary)
        if sender not in ROLE_NAMES or target not in ROLE_NAMES or sender == target or len(key) > 128:
            raise ValueError('explicit different recipient required')
        handoff_id = 'hnd_' + uuid.uuid5(uuid.NAMESPACE_URL, sender + ':' + session_id + ':' + key).hex
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT s.issue FROM sessions s JOIN bindings b ON s.agent=b.agent AND s.session=b.session WHERE s.agent=? AND s.session=?',
                (sender, session_id)).fetchone()
            if not row: raise ValueError('source runtime session must be bound')
            issue_id = row[0]
            body = dict(contract='linear-agent-handoff.v1', handoff_id=handoff_id, sender=sender, target=target,
                sender_app_user_id=self.policy['agents'][sender]['app_user_id'],
                target_app_user_id=self.policy['agents'][target]['app_user_id'], issue_id=issue_id,
                source_session_id=session_id, summary=summary, binding=self.policy['issues'][issue_id],
                state='requested', execution_authorized=False, human_approval_inferred=False)
            raw = encoded(body)
            old = db.execute('SELECT body FROM handoffs WHERE id=?', (handoff_id,)).fetchone()
            if old and old[0] != raw: raise ValueError('handoff key changed')
            db.execute('INSERT OR IGNORE INTO handoffs VALUES(?,?,?,?,?,?)', (handoff_id, sender, target, issue_id, session_id, raw))
        return body

    def handoffs(self, target, *, limit=20):
        if target not in ROLE_NAMES or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('bounded named recipient required')
        with self.connection() as db:
            rows = db.execute('SELECT body FROM handoffs WHERE target=? ORDER BY rowid LIMIT ?', (target, limit)).fetchall()
        return [decode(row[0]) for row in rows]

    def handoff_state(self, target, handoff_id, session_id, state):
        identifier(session_id)
        if state not in ('accepted', 'completed'): raise ValueError('explicit handoff state required')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            handoff = db.execute('SELECT target,issue FROM handoffs WHERE id=?', (handoff_id,)).fetchone()
            if not handoff or handoff[0] != target: raise ValueError('wrong handoff recipient')
            row = db.execute('SELECT s.issue FROM sessions s JOIN bindings b ON s.agent=b.agent AND s.session=b.session WHERE s.agent=? AND s.session=?',
                (target, session_id)).fetchone()
            if not row or row[0] != handoff[1]: raise ValueError('recipient runtime must bind same work')
            if state == 'completed' and not db.execute('SELECT 1 FROM handoff_events WHERE id=? AND state=?',
                    (handoff_id, 'accepted')).fetchone(): raise ValueError('acknowledge handoff first')
            body = dict(handoff_id=handoff_id, target=target, target_session_id=session_id, state=state,
                work_outcome_inferred=False, human_approval_inferred=False)
            raw = encoded(body)
            old = db.execute('SELECT body FROM handoff_events WHERE id=? AND state=?', (handoff_id, state)).fetchone()
            if old and old[0] != raw: raise ValueError('recipient handoff binding changed')
            db.execute('INSERT OR IGNORE INTO handoff_events VALUES(?,?,?)', (handoff_id, state, raw))
        return body


    def publication(self, agent, key, *, begin=False, receipt=None):
        if agent not in ROLE_NAMES: raise ValueError('unknown publisher')
        text(key)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            request = db.execute('SELECT request FROM activities WHERE agent=? AND key=?', (agent, key)).fetchone()
            if not request: raise ValueError('freeze the activity first')
            saved = db.execute('SELECT body FROM publication_receipts WHERE agent=? AND key=?', (agent, key)).fetchone()
            if saved:
                if receipt is not None and saved[0] != encoded(receipt): raise ValueError('receipt differs')
                return dict(state='recorded', receipt=decode(saved[0]))
            started = db.execute('SELECT 1 FROM publication_attempts WHERE agent=? AND key=?', (agent, key)).fetchone()
            if receipt is not None:
                if not started or receipt.get('agent') != agent or receipt.get('key') != key:
                    raise ValueError('exact existing publication attempt required')
                if receipt.get('activity_id') != decode(request[0])['variables']['input']['id']:
                    raise ValueError('wrong activity receipt')
                db.execute('INSERT INTO publication_receipts VALUES(?,?,?)', (agent, key, encoded(receipt)))
                return dict(state='recorded', receipt=receipt)
            if begin:
                if started: raise ValueError('publication uncertain; reconcile original activity ID, do not resend')
                db.execute('INSERT INTO publication_attempts VALUES(?,?)', (agent, key))
                return dict(state='started', request=decode(request[0]))
            return dict(state='uncertain' if started else 'ready', request=decode(request[0]))
