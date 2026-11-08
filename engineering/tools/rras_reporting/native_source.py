"""Selected native source reads through a separate credential-free App Server.

No file discovery or agent-supplied path is admitted. The parent registration and
installed root select the exact native file. The native coding account retains
its original files; the private adapter receives no broad filesystem ACL.
"""
import base64
import importlib.util
import os
from pathlib import Path
import tempfile

MAX_SOURCE=32*1024*1024


def local(name):
    spec=importlib.util.spec_from_file_location('selected_native_source_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


runtime=local('codex_runtime')


class Client(runtime.SocketAppServer):
    # Only the disposable, network-isolated source reader uses this larger
    # response bound. Coding/control RPC and outgoing frames retain 1 MiB.
    READ_FRAME_LIMIT=4*((MAX_SOURCE+2)//3)+4096

    def call(self,method,params):
        if method not in ('initialize','fs/getMetadata','fs/readFile'):raise ValueError('native source reader exposes no coding methods')
        return super().call(method,params)


def path(value,root):
    p=Path(value);base=Path(root)
    if (not p.is_absolute() or not base.is_absolute() or str(p)!=os.path.normpath(str(p)) or str(base)!=os.path.normpath(str(base)) or
            not p.is_relative_to(base) or p==base or p.suffix!='.jsonl' or len(p.parts)-len(base.parts)>16 or len(p.parts)>64):
        raise ValueError('one registered native JSONL source under the installed root required')
    return p,base


def read(client,source,root,session):
    p,base=path(source,root);runtime.identifier(session)
    # Resolve metadata as the native account. Do not follow even an intermediate
    # symlink into a different source tree, credential directory or repository.
    targets=list(reversed(base.parents))+[base]+list(reversed(p.parents[:len(p.parts)-len(base.parts)-1]))+[p]
    for target in targets:
        value=client.call('fs/getMetadata',dict(path=str(target)))
        if (type(value) is not dict or value.get('isSymlink') is not False or
                value.get('isFile') is not (target==p) or value.get('isDirectory') is not (target!=p)):
            raise ValueError('registered native source metadata differs')
    value=client.call('fs/readFile',dict(path=str(p)))
    if type(value) is not dict or set(value)!={'dataBase64'} or type(value['dataBase64']) is not str or len(value['dataBase64'])>4*((MAX_SOURCE+2)//3):
        raise ValueError('bounded selected native source response required')
    raw=base64.b64decode(value['dataBase64'],validate=True)
    if not 1<=len(raw)<=MAX_SOURCE:raise ValueError('native source exceeds transport bound; retain source and report gap')
    return local('capture_pilot').source_bytes(raw,session)[0]


def collect(spool,job,configuration,*,client=None):
    own=client is None
    if own:client=Client(configuration['source_socket'],configuration['source_peer_uid'],timeout=20)
    try:raw=read(client,job['source'],configuration['native_root'],job['session'])
    finally:
        if own:client.close()
    # Scratch belongs in the passive unit's bounded private /tmp. Validate the
    # session before materializing it; no arbitrary response is persisted.
    with tempfile.TemporaryDirectory(prefix='rras-selected-native-') as folder:
        root=Path(folder);root.chmod(0o700);snapshot=root/'source.jsonl'
        fd=os.open(snapshot,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw)
        args={k:v for k,v in job.items() if k not in ('source','id')}
        args['source']=str(snapshot)
        return local('capture_collectors').collect_codex(spool,**args,source_gaps=[
            'Selected native source was read across Unix identities through a separate read-only filesystem RPC adapter; no broad filesystem ACL was granted.',
            'Native filesystem transport is bounded at 32 MiB per source; larger sources remain retained with a capture gap rather than truncation.',
            'Filesystem RPC does not attest source inode ownership, hardlinks or modes; native records are imported evidence, not independent actor verification.'])
