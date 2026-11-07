"""Private, per-app PKCE installation custody. No model calls or app registration.

Only a local administrator begins installation/refresh/revocation. Public HTTP
handles a previously issued, expiring state. Tokens never leave this module via
status/CLI/HTTP. Each app has a separate vault and independent availability.
"""
from contextlib import contextmanager
import base64
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError


def local(name):
    spec = importlib.util.spec_from_file_location('reporting_oauth_' + name, Path(__file__).with_name(name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


core = local('linear_agents')
publication = local('linear_publication')
SCOPES = ['read', 'write', 'app:mentionable', 'app:assignable']
IDENTITY = {'query': 'query ReportingInstallation { viewer { id app active name } organization { id } }'}


def configuration(value):
    keys = {'contract', 'agent', 'organization_id', 'oauth_client_id', 'public_origin',
            'expected_actor_id', 'excluded_actor_ids'}
    if type(value) is not dict or set(value) != keys or value['contract'] != 'linear-agent-oauth.v1':
        raise ValueError('exact OAuth configuration required')
    if value['agent'] not in core.ROLE_NAMES: raise ValueError('unknown agent')
    core.identifier(value['organization_id']); core.identifier(value['oauth_client_id'])
    if value['expected_actor_id'] is not None: core.identifier(value['expected_actor_id'])
    excluded = value['excluded_actor_ids']
    if type(excluded) is not list or not 1 <= len(excluded) <= 32 or len(set(excluded)) != len(excluded):
        raise ValueError('other app/human actors must be explicitly excluded')
    for actor in excluded: core.identifier(actor)
    if value['expected_actor_id'] in excluded: raise ValueError('contradictory app binding')
    if local('linear_setup').setup(value['public_origin'])['public_origin'] != value['public_origin']:
        raise ValueError('canonical public origin required')
    return core.decode(core.encoded(value))


def token_text(value):
    if type(value) is not str or not 1 <= len(value) <= 4096 or any(not 33 <= ord(c) <= 126 for c in value):
        raise ValueError('bounded credential required')
    return value


class TokenRefused(ValueError): pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


class TokenEndpoint:
    """Fixed Linear endpoints, bounded response, no redirects, no secret errors."""
    def __call__(self, operation, form):
        if operation not in ('token', 'revoke'): raise ValueError('unknown token operation')
        message = Request('https://api.linear.app/oauth/' + operation, data=urlencode(form).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
        try:
            with build_opener(NoRedirect).open(message, timeout=5) as response:
                raw = response.read(64 * 1024 + 1)
                if len(raw) > 64 * 1024: raise ValueError('bounded token response required')
                return {} if operation == 'revoke' else core.decode(raw)
        except HTTPError as error:
            if error.code in (400, 401, 403): raise TokenRefused('authorization refused; retain custody') from None
            raise ValueError('token endpoint unavailable; retain uncertain operation') from None
        except Exception:
            raise ValueError('token endpoint unavailable; retain uncertain operation') from None


class Vault:
    def __init__(self, root, selected, *, create=False, endpoint=None, identity=None):
        self.config = configuration(selected)
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.resolve(strict=False) != self.root:
            raise ValueError('canonical private OAuth root required')
        self.endpoint = endpoint or TokenEndpoint()
        self.identity = identity or (lambda token: publication.Client(token)(IDENTITY))
        if create: self.root.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.check_root()
        self.path = self.root / 'oauth.sqlite3'
        self.lock_path = self.root / 'custody.lock'
        if create:
            for path in (self.path, self.lock_path):
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600); os.close(fd)
            with self.connection() as db:
                db.executescript('''
                    CREATE TABLE configuration(body BLOB NOT NULL);
                    CREATE TABLE installation(id INTEGER PRIMARY KEY CHECK(id=1),body BLOB NOT NULL);
                    CREATE TRIGGER config_no_update BEFORE UPDATE ON configuration BEGIN SELECT RAISE(ABORT,'fixed OAuth policy'); END;
                    CREATE TRIGGER config_no_delete BEFORE DELETE ON configuration BEGIN SELECT RAISE(ABORT,'fixed OAuth policy'); END;
                ''')
                db.execute('INSERT INTO configuration VALUES(?)', (core.encoded(self.config),))
                self.save(db, dict(phase='empty', generation=0))
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        with self.connection() as db:
            if db.execute('SELECT body FROM configuration').fetchone()[0] != core.encoded(self.config):
                raise ValueError('OAuth policy differs; preserve custody')

    def check_root(self):
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private caller-owned OAuth directory required')

    @contextmanager
    def connection(self):
        self.check_root()
        # Advisory per-app process lock covers remote calls as well as atomic writes.
        # A crash releases the lock but leaves the committed uncertain phase.
        core.private_file(self.lock_path, 1)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        db = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            core.private_file(self.path, 4 * 1024 * 1024)
            for path in (Path(str(self.path) + '-journal'), Path(str(self.path) + '-wal'), Path(str(self.path) + '-shm')):
                if path.exists() or path.is_symlink(): core.private_file(path, 4 * 1024 * 1024)
            db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=2)
            db.execute('PRAGMA synchronous=FULL'); db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA trusted_schema=OFF')
            yield db
            db.commit()
        finally:
            if db is not None: db.close()
            os.close(fd)

    def read(self, db): return core.decode(db.execute('SELECT body FROM installation WHERE id=1').fetchone()[0])

    def save(self, db, value):
        db.execute('INSERT OR REPLACE INTO installation VALUES(1,?)', (core.encoded(value),)); db.commit()

    def summary(self, value):
        return dict(agent=self.config['agent'], organization_id=self.config['organization_id'],
            oauth_client_id=self.config['oauth_client_id'], phase=value['phase'], generation=value['generation'],
            app_user_id=value.get('app_user_id'), expires_at=value.get('expires_at'), execution_enabled=False)

    def status(self):
        with self.connection() as db: return self.summary(self.read(db))

    def begin(self, *, now=None):
        now = time.time() if now is None else now
        with self.connection() as db:
            current = self.read(db)
            if current['phase'] not in ('empty', 'revoked', 'denied') and not (
                    current['phase'] == 'pending' and current['state_expires_at'] < now):
                raise ValueError('existing installation or pending operation; reconcile before replacement')
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            current = dict(phase='pending', generation=current['generation'], verifier=verifier,
                state_sha256=hashlib.sha256(state.encode()).hexdigest(), state_expires_at=now + 600)
            self.save(db, current)
            params = dict(client_id=self.config['oauth_client_id'], redirect_uri=self.callback_url(),
                response_type='code', scope=','.join(SCOPES), state=state, actor='app',
                code_challenge=challenge, code_challenge_method='S256')
            return dict(agent=self.config['agent'], authorization_url='https://linear.app/oauth/authorize?' + urlencode(params),
                expires_at=current['state_expires_at'], execution_enabled=False)

    def callback_url(self): return self.config['public_origin'] + '/oauth/' + self.config['agent'] + '/callback'

    def credentials(self, response, now):
        if (type(response) is not dict or type(response.get('token_type')) is not str or
                response['token_type'].lower() != 'bearer'):
            raise ValueError('bearer token pair required')
        token_text(response.get('access_token')); token_text(response.get('refresh_token'))
        expiry = response.get('expires_in')
        if type(expiry) is not int or not 1 <= expiry <= 366 * 86400: raise ValueError('reported token expiry required')
        scope = response.get('scope')
        if type(scope) is str: scope = re.split(r'[ ,]+', scope.strip())
        if type(scope) is not list or set(scope) != set(SCOPES): raise ValueError('unexpected token scopes')
        return now + expiry

    def verify(self, value, now):
        expiry = self.credentials(value['credentials'], now)
        identity = self.identity(value['credentials']['access_token'])
        if type(identity) is not dict or type(identity.get('viewer')) is not dict or type(identity.get('organization')) is not dict:
            raise ValueError('bounded app identity required')
        viewer = identity.get('viewer', {})
        actor = core.identifier(viewer.get('id'))
        if (viewer.get('app') is not True or viewer.get('active') is not True or
                identity.get('organization', {}).get('id') != self.config['organization_id'] or
                actor in self.config['excluded_actor_ids'] or
                self.config['expected_actor_id'] not in (None, actor) or
                value.get('app_user_id') not in (None, actor)):
            raise ValueError('wrong workspace or app actor; preserve quarantined credentials')
        value.update(phase='active', app_user_id=actor, expires_at=expiry, generation=value['generation'] + 1)
        return value

    def callback(self, parameters, *, now=None):
        now = time.time() if now is None else now
        if type(parameters) is not dict or not set(parameters) <= {'state', 'code', 'error', 'error_description'}:
            raise ValueError('exact callback required')
        state = token_text(parameters.get('state'))
        if ('code' in parameters) == ('error' in parameters): raise ValueError('one callback outcome required')
        code = token_text(parameters.get('code', parameters.get('error')))
        if 'code' in parameters and 'error_description' in parameters: raise ValueError('conflicting callback')
        code_sha = hashlib.sha256((('error:' if 'error' in parameters else 'code:') + code).encode()).hexdigest()
        with self.connection() as db:
            value = self.read(db)
            if not secrets.compare_digest(value.get('state_sha256', ''), hashlib.sha256(state.encode()).hexdigest()):
                raise ValueError('callback state refused')
            if value.get('code_sha256') == code_sha and value['phase'] in ('active', 'denied'):
                return self.summary(value)  # Exact completed callback; never exchange twice.
            if value['phase'] != 'pending' or not now <= value['state_expires_at']:
                raise ValueError('state expired or already consumed; retain operation')
            value.update(code_sha256=code_sha, phase='denied' if 'error' in parameters else 'exchanging')
            self.save(db, value)  # Consume before remote effects; crashes cannot replay exchange.
            if 'error' in parameters:
                value.pop('verifier', None); self.save(db, value); return self.summary(value)
            response = self.endpoint('token', dict(grant_type='authorization_code', code=code,
                code_verifier=value['verifier'], redirect_uri=self.callback_url(), client_id=self.config['oauth_client_id']))
            value.update(credentials=response, phase='verifying', received_at=now); value.pop('verifier', None)
            self.save(db, value)  # Retain the pair even if validation/identity lookup fails.
            self.verify(value, now); self.save(db, value)
            return self.summary(value)

    def reconcile_identity(self, *, now=None):
        with self.connection() as db:
            value = self.read(db)
            if value['phase'] != 'verifying': raise ValueError('no retained identity verification pending')
            # Keep original receipt time; a delayed identity check cannot extend expiry.
            self.verify(value, value['received_at'])
            self.save(db, value); return self.summary(value)

    def refresh(self, *, recover=False, now=None):
        now = time.time() if now is None else now
        with self.connection() as db:
            value = self.read(db)
            if recover:
                if value['phase'] != 'refreshing' or not 0 <= now - value['refresh_started_at'] < 29 * 60:
                    raise ValueError('explicit refresh recovery window unavailable')
            else:
                if value['phase'] != 'active': raise ValueError('active installation required')
                value.update(phase='refreshing', refresh_started_at=now); self.save(db, value)
            try:
                response = self.endpoint('token', dict(grant_type='refresh_token',
                    refresh_token=value['credentials']['refresh_token'], client_id=self.config['oauth_client_id']))
            except TokenRefused:
                value['phase'] = 'invalid'; self.save(db, value); raise
            value.update(credentials=response, phase='verifying', received_at=now); self.save(db, value)
            self.verify(value, now); self.save(db, value)
            return self.summary(value)

    def invalidate(self, generation):
        """A caller observing authentication refusal blocks only its token generation."""
        with self.connection() as db:
            value = self.read(db)
            if value['generation'] == generation and value['phase'] == 'active':
                value['phase'] = 'invalid'; self.save(db, value)
            return self.summary(value)

    def revoke(self):
        with self.connection() as db:
            value = self.read(db)
            if value['phase'] == 'revoked': return self.summary(value)
            if 'credentials' not in value or value['phase'] == 'refreshing':
                raise ValueError('no known current credential; reconcile uncertain refresh first')
            value['phase'] = 'revoking'; self.save(db, value)
            self.endpoint('revoke', dict(token=token_text(value['credentials'].get('access_token')), token_type_hint='access_token'))
            value = dict(phase='revoked', generation=value['generation'], app_user_id=value.get('app_user_id'))
            self.save(db, value); return self.summary(value)

    def access(self, actor, *, now=None):
        """Private in-process caller only. Never expose the returned credential in CLI/HTTP."""
        now = time.time() if now is None else now
        with self.connection() as db:
            value = self.read(db)
            if value['phase'] != 'active' or value['app_user_id'] != core.identifier(actor) or now + 60 >= value['expires_at']:
                raise ValueError('app authorization unavailable; explicit renewal or reconciliation required')
            return value['credentials']['access_token'], value['generation']


class ScopedClient:
    """An explicit publisher can use custody without exporting a loose token file.

    A 401 blocks the matching credential generation. No implicit refresh, replay,
    credential substitution or retry of an uncertain GraphQL mutation occurs.
    """
    def __init__(self, vault, actor, *, client_factory=None):
        self.vault, self.actor = vault, core.identifier(actor)
        self.client_factory = client_factory or publication.Client

    def __call__(self, request):
        token, generation = self.vault.access(self.actor)
        try: return self.client_factory(token)(request)
        except publication.AuthenticationRefused:
            self.vault.invalidate(generation)
            raise ValueError('app authorization blocked; reconcile before publication') from None
