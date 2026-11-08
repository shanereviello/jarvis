"""Write-only checkpoint broker for a different native coding UID.

The socket dispatcher supplies the single active runtime context. The native
caller receives no journal, policy, bridge token, history scope or work selector.
"""
import os
import sqlite3
from pathlib import Path
import importlib.util


def local(name):
    spec=importlib.util.spec_from_file_location('checkpoint_broker_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


transport=local('codex_runtime').history_unix()


class Access:
    def __init__(self,runtime,configuration,native_uid):
        transport.uid(native_uid)
        if native_uid==os.getuid() or os.geteuid()!=os.getuid():raise ValueError('distinct unprivileged native identity required')
        self.runtime=runtime;self.configuration=configuration;self.grants={native_uid:True}

    def dispatch(self,caller,message):
        if caller not in self.grants or type(message) is not dict or set(message)!={'method','arguments','session_id','dispatch_id'} or message['method']!='checkpoint':
            raise ValueError('only scoped checkpoint recording is available')
        native=local('codex_runtime');native.identifier(message['session_id']);native.identifier(message['dispatch_id'])
        with self.runtime.connection() as db:
            rows=db.execute("SELECT session FROM turns WHERE dispatch=? AND session=? AND state IN ('preparing','running','uncertain','interrupt_requested')",
                (message['dispatch_id'],message['session_id'])).fetchall()
        if len(rows)!=1:raise ValueError('one actual active runtime context required')
        recorder=local('runtime_checkpoint_mcp').Checkpoints(self.runtime.root,self.configuration,rows[0]['session'])
        if recorder.policy!=self.runtime.policy:raise ValueError('actual runtime policy differs')
        return recorder.record(message['arguments'])


class Server(transport.Server):
    def __init__(self,path,runtime,configuration,native_uid,*,on_bound=None):
        transport.uid(os.getuid());self.path=transport.endpoint(path)
        self.access=Access(runtime,configuration,native_uid)
        self.listener=None;self.identity=None;self.on_bound=on_bound


def acl_on_bound(path,native_uid):
    intake=local('capture_intake');production=intake.local('production_entry')
    production.set_acl(path.parent,[native_uid],directory=True);production.set_acl(path,[native_uid],directory=False)
