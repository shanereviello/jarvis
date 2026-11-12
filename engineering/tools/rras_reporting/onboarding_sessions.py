"""Protected, short-lived planning dispatch registry.

Only a trusted ingress may register a dispatch. Native verification happens
both when registering and when looking up a dispatch; the database contains
identity metadata, not a bearer token. This module does not expose a listener.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import time


def drafts():
    spec=importlib.util.spec_from_file_location('onboarding_sessions_drafts',Path(__file__).with_name('onboarding_drafts.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def encode(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')


class Sessions:
    def __init__(self,connection,grants,verify_native,is_active,clock=time.time):
        if (type(grants) is not dict or not grants or not callable(verify_native) or
                not callable(is_active) or not callable(clock)):
            raise ValueError('protected planning verification required')
        self.connection,self.grants,self.verify_native,self.is_active,self.clock=connection,grants,verify_native,is_active,clock

    @staticmethod
    def initialize(db):
        db.execute('CREATE TABLE planning_sessions (dispatch TEXT PRIMARY KEY, peer INTEGER NOT NULL, '
                   'origin BLOB NOT NULL, sha256 TEXT NOT NULL, expires INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)')
        db.commit()

    def register(self,peer,dispatch,expires):
        d=drafts();d.identifier(dispatch)
        now=int(self.clock())
        if (type(peer) is not int or peer not in self.grants or type(expires) is not int or
                not now<expires<=now+3600 or self.is_active(peer,dispatch) is not True):
            raise ValueError('bounded planning registration required')
        origin=d.authorize(self.grants,lambda _:self.verify_native(dispatch),peer,None)
        raw=encode(origin);sha=hashlib.sha256(raw).hexdigest()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT peer,origin,sha256,expires,revoked FROM planning_sessions WHERE dispatch=?',(dispatch,)).fetchone()
            if row is not None:
                if tuple(row)!=(peer,raw,sha,expires,0):raise ValueError('planning registration differs')
                return dict(registered=False,expires=expires,execution_authorized=False)
            db.execute('INSERT INTO planning_sessions VALUES(?,?,?,?,?,0)',(dispatch,peer,raw,sha,expires))
            db.commit()
        return dict(registered=True,expires=expires,execution_authorized=False)

    def lookup(self,peer,dispatch):
        d=drafts();d.identifier(dispatch)
        with self.connection() as db:
            row=db.execute('SELECT peer,origin,sha256,expires,revoked FROM planning_sessions WHERE dispatch=?',(dispatch,)).fetchone()
        if (row is None or type(peer) is not int or row[0]!=peer or row[4] or int(self.clock())>=row[3] or
                hashlib.sha256(row[1]).hexdigest()!=row[2] or self.is_active(peer,dispatch) is not True):
            raise ValueError('active planning session required')
        saved=json.loads(row[1]);current=d.authorize(self.grants,lambda _:self.verify_native(dispatch),peer,None)
        if current!=saved:raise ValueError('native planning identity changed')
        return current

    def revoke(self,dispatch):
        drafts().identifier(dispatch)
        with self.connection() as db:
            db.execute('UPDATE planning_sessions SET revoked=1 WHERE dispatch=?',(dispatch,));db.commit()
