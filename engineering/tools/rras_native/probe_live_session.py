"""Model-free native session initialization; no turn/start or credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

SESSION_SHA = '6788277acd880a900faaedfdf948caca5bcad7f33e8fa2db3815cd47b7d7c651'


def probe(source, binary, config, work, uid, expected_instructions=None):
    source, binary, config = (Path(p).resolve(strict=True) for p in (source, binary, config))
    work = Path(work).resolve(strict=True)
    if os.getuid() != uid or work.stat().st_uid != uid or work.stat().st_mode & 0o077:
        raise ValueError('wrong identity or non-private work directory')
    if hashlib.sha256((source/'agent/transports/codex_app_server_session.py').read_bytes()).hexdigest() != SESSION_SHA:
        raise ValueError('native session source pin changed')
    # Refuse inherited credentials/bypass flags; never inspect their values.
    allowed = {'PATH','HOME','LANG','HERMES_HOME','PYTHONDONTWRITEBYTECODE'}
    if set(os.environ) - allowed:
        raise ValueError('launch with the documented empty environment')
    home, hermes, workspace = (work/n for n in ('codex-home','hermes-home','workspace'))
    for p in (home, hermes, workspace):
        p.mkdir(mode=0o700)
    (home/'config.toml').write_bytes(config.read_bytes())
    os.chmod(home/'config.toml',0o600)
    os.environ.update(HOME=str(work), HERMES_HOME=str(hermes), CODEX_HOME=str(home))
    os.chdir(workspace)
    sys.path.insert(0,str(source))
    from agent.transports.codex_app_server_session import CodexAppServerSession
    result = {'scope':'live-native-session-no-turn','uid':uid,'api_calls':0,
              'inference_requests':0,'success':False,'cases':[]}
    session = CodexAppServerSession(cwd=str(workspace),codex_bin=str(binary),codex_home=str(home))
    process = None
    try:
        session.ensure_started()
        process = session._client._proc
        reply = session._client.request('config/read', {'includeLayers':False}, timeout=15)
        c = reply['config']
        # Retain only selected non-secret policy, never provider/auth configuration.
        policy = {k:c.get(k) for k in ('sandbox_mode','approval_policy','sandbox_workspace_write')}
        result['policy'] = policy
        result['configured_mcp_names'] = list((c.get('mcp_servers') or {}).keys())
        checks = {
            'native_thread_started':bool(session._thread_id),
            'private_codex_home': b'CODEX_HOME='+str(home).encode() in Path(f'/proc/{process.pid}/environ').read_bytes().split(b'\0'),
            'admitted_cwd': Path(f'/proc/{process.pid}/cwd').resolve()==workspace,
            'no_configured_apps':not c.get('apps'),
            'workspace_write':c.get('sandbox_mode')=='workspace-write',
            'on_request':c.get('approval_policy')=='on-request',
            'network_off':(c.get('sandbox_workspace_write') or {}).get('network_access') is False,
            'no_mcp':not c.get('mcp_servers'),
        }
        if expected_instructions is not None:
            checks['full_native_developer_instructions']=c.get('developer_instructions')==expected_instructions
        result['cases'] = [{'name':n,'passed':v} for n,v in checks.items()]
        result['success'] = all(checks.values())
    except Exception as e:
        # Errors can contain endpoint/auth text; retain type only.
        result['error_type'] = type(e).__name__
    finally:
        if process is None and session._client is not None:
            process = session._client._proc
        session.close()
        result['app_server_stopped'] = process is not None and process.poll() is not None
        result['success'] = result['success'] and result['app_server_stopped']
        with (work/'evidence.json').open('x') as f:
            os.chmod(work/'evidence.json',0o600)
            json.dump(result,f,indent=2);f.write('\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','binary','config','work'):
        p.add_argument('--'+n,required=True)
    p.add_argument('--uid',required=True,type=int)
    a=p.parse_args()
    r=probe(a.source,a.binary,a.config,a.work,a.uid)
    print(json.dumps(r));sys.exit(0 if r['success'] else 1)
