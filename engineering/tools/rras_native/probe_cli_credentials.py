"""Native CLI construction with harmless credential; never run a conversation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys

SENTINEL=b'RRAS-NONSECRET-OFFLINE-FIXTURE\n'


def read_fixture(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular fixture credential required')
    if path.stat().st_size != len(SENTINEL) or path.read_bytes()!=SENTINEL:
        raise ValueError('only the exact harmless fixture is accepted')
    return SENTINEL.decode().strip()


def probe(source, config, work, credential, uid, protected_source=None, codex_config=None):
    work=Path(work).resolve(strict=True)
    if os.getuid()!=uid or work.stat().st_uid!=uid or work.stat().st_mode & 0o077:
        raise ValueError('wrong UID or non-private fixture')
    allowed={'PATH','HOME','LANG','LC_CTYPE','PYTHONDONTWRITEBYTECODE','CREDENTIALS_DIRECTORY'}
    if set(os.environ)-allowed:
        raise ValueError('empty documented environment required')
    token=read_fixture(credential)
    source_denied=False
    if protected_source is not None:
        try:
            with open(protected_source,'rb'):
                pass
        except PermissionError:
            source_denied=True
        if not source_denied:
            raise ValueError('original fixture credential must be unreadable')
    delivery=os.environ.get('CREDENTIALS_DIRECTORY')
    if delivery and Path(credential).resolve().parent!=Path(delivery).resolve():
        raise ValueError('credential must belong to the systemd delivery directory')
    if delivery and protected_source is None:
        raise ValueError('systemd fixture requires original-source access check')
    home=work/'hermes';home.mkdir(mode=0o700)
    codex=work/'codex';codex.mkdir(mode=0o700)
    if codex_config is not None:
        (codex/'config.toml').write_bytes(Path(codex_config).read_bytes())
        os.chmod(codex/'config.toml',0o600)
    c=json.loads(Path(config).read_text())
    (home/'config.yaml').write_text(json.dumps(c))
    os.environ.update(HERMES_HOME=str(home),CODEX_HOME=str(codex),
                      OPENAI_API_KEY=token,RRAS_OPENAI_API_KEY=token)
    os.chdir(work)
    attempts=[]
    result_traces=[]
    def deny(*args,**kwargs):
        import traceback
        attempts.append('network')
        result_traces.append([f'{x.filename}:{x.lineno}:{x.name}' for x in traceback.extract_stack(limit=35)])
        raise RuntimeError('offline fixture forbids network')
    socket.socket.connect=deny;socket.create_connection=deny
    sys.path.insert(0,str(Path(source).resolve(strict=True)))
    result={'scope':'native-cli-construction-offline-sentinel','uid':uid,
            'success':False,'real_credentials_used':False,'model_turns':0,'api_calls':0,
            'systemd_delivery':bool(delivery),'cases':[]}
    cli=None
    try:
        from agent.transports.codex_app_server import CodexAppServerClient
        original=CodexAppServerClient.request
        def guarded(self,method,*args,**kwargs):
            if method=='turn/start':
                attempts.append('turn/start');raise RuntimeError('inference forbidden')
            return original(self,method,*args,**kwargs)
        CodexAppServerClient.request=guarded
        from run_agent import AIAgent
        def forbidden(*args,**kwargs):
            attempts.append('conversation');raise RuntimeError('conversation forbidden')
        AIAgent.run_conversation=forbidden
        from cli import HermesCLI
        cli=HermesCLI(model=c['model']['default'],provider=c['model']['provider'],
                      toolsets=['kanban','skills'],ignore_rules=True)
        ok=cli._init_agent()
        agent=cli.agent
        from tools.approval import is_approval_bypass_active
        checks={'native_agent_constructed':bool(ok and agent),
                'app_server_mode':getattr(agent,'api_mode',None)=='codex_app_server',
                'no_inference_attempt':not any(a in ('conversation','turn/start') for a in attempts),
                'network_guard_installed':socket.socket.connect is deny,
                'no_network_attempt':not attempts,
                'narrow_cli_toolsets':set(cli.enabled_toolsets)=={'kanban','skills'},
                'approval_bypass_off':not is_approval_bypass_active(),
                'fixture_delivery':os.environ['OPENAI_API_KEY']==os.environ['RRAS_OPENAI_API_KEY']==token}
        if delivery:
            checks['original_source_unreadable']=source_denied
        result['cases']=[{'name':n,'passed':v} for n,v in checks.items()]
        result['success']=all(checks.values())
    except Exception as exc:
        result['error_type']=type(exc).__name__
    finally:
        if cli is not None and getattr(cli,'agent',None):
            cli.agent.close()
        result['blocked_attempts']=attempts
        result['blocked_call_sites']=result_traces
        with (work/'evidence.json').open('x') as f:
            os.chmod(work/'evidence.json',0o600);json.dump(result,f,indent=2);f.write('\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','config','work','credential'):p.add_argument('--'+n,required=True)
    p.add_argument('--uid',type=int,required=True)
    p.add_argument('--protected-source')
    p.add_argument('--codex-config')
    a=p.parse_args();r=probe(a.source,a.config,a.work,a.credential,a.uid,a.protected_source,a.codex_config)
    print(json.dumps(r));sys.exit(0 if r['success'] else 1)
