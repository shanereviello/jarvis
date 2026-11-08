"""Read the actual bound native API run, without environment or agent selectors."""
import hashlib
import importlib.util
from pathlib import Path
import re
import uuid

SESSION_CONTEXT_SHA256='07525c03a72c47081b34ecc8d174aaea003e2a15f9da841fa9797345b02766aa'


def parse(platform,session,key):
    if platform!='api_server' or type(session) is not str or type(key) is not str or not re.fullmatch('run_[0-9a-f]{32}',key):
        raise ValueError('actual native API run required')
    parts=session.split(':')
    if len(parts)!=3 or parts[0]!='linear':raise ValueError('actual native Linear session required')
    for value in parts[1:]:
        if str(uuid.UUID(value))!=value:raise ValueError('canonical actual native identity required')
    return dict(organization_id=parts[1],session_id=parts[2],hermes_session_id=session,run_id=key)


def actual():
    from gateway import session_context as native
    if hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()!=SESSION_CONTEXT_SHA256:
        raise ValueError('native session context changed; review compatibility')
    values=[]
    for key in ('HERMES_SESSION_PLATFORM','HERMES_SESSION_ID','HERMES_SESSION_KEY'):
        variable=native._VAR_MAP.get(key)
        if variable is None:raise ValueError('native bound context unavailable')
        value=variable.get()
        # The public compatibility accessor can fall back to os.environ. This
        # integration requires task-local bindings and deliberately refuses it.
        if value is native._UNSET:raise ValueError('actual native context is not bound')
        values.append(value)
    return parse(*values)
