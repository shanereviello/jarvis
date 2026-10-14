"""Offline native provider routing with a clearly harmless credential fixture."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys


def probe(source, config, work):
    work=Path(work).resolve(strict=True)
    if work.stat().st_uid!=os.getuid() or work.stat().st_mode & 0o077:
        raise ValueError('private owned fixture required')
    if set(os.environ)-{'PATH','HOME','LANG','LC_CTYPE','PYTHONDONTWRITEBYTECODE'}:
        raise ValueError('empty environment required')
    home=work/'hermes';home.mkdir(mode=0o700)
    credential=work/'harmless-credential'
    with credential.open('x') as f:
        os.chmod(credential,0o600)
        f.write('RRAS-NONSECRET-OFFLINE-FIXTURE\n')
    # Local file delivery only: this does not claim systemd LoadCredential acceptance.
    token=credential.read_text().strip()
    os.environ.update(HERMES_HOME=str(home),OPENAI_API_KEY=token,RRAS_OPENAI_API_KEY=token)
    c=json.loads(Path(config).read_text())
    (home/'config.yaml').write_text(json.dumps(c))
    def deny(*args,**kwargs):
        raise RuntimeError('network forbidden in offline fixture')
    socket.socket.connect=deny
    socket.create_connection=deny
    sys.path.insert(0,str(Path(source).resolve(strict=True)))
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from hermes_cli.tools_config import _get_platform_tools
    r=resolve_runtime_provider(requested=c['model']['provider'],target_model=c['model']['default'])
    tools=sorted(_get_platform_tools(c,'cli'))
    checks={'app_server_selected':r['api_mode']=='codex_app_server',
            'api_platform_provider':r['provider']=='openai-api',
            'narrow_toolsets':tools==['kanban','skills'],
            'same_fixture_delivery':r['api_key']==token==os.environ['RRAS_OPENAI_API_KEY']}
    e={'scope':'native-full-provider-resolver-offline-fixture','success':all(checks.values()),
       'api_calls':0,'real_credentials_used':False,'cli_agent_constructed':False,
       'systemd_credential_delivery_tested':False,'checks':checks,
       'provider':r['provider'],'api_mode':r['api_mode'],'toolsets':tools}
    with (work/'evidence.json').open('x') as f:
        os.chmod(work/'evidence.json',0o600);json.dump(e,f,indent=2);f.write('\n')
    return e


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','config','work'):p.add_argument('--'+n,required=True)
    a=p.parse_args();e=probe(a.source,a.config,a.work)
    print(json.dumps(e));sys.exit(0 if e['success'] else 1)
