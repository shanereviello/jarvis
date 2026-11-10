"""Selected-source SpecStory adapter. No provider run, cloud login or hook edits."""
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import uuid

SPECSTORY_VERSION='2.17.0'
SPECSTORY_SHA256='25b8a1b7c13b6cccd514845608785057b980ad3d55029d75527a0d9aaf0603c4'
FLAGS=('--no-cloud-sync','--no-usage-analytics','--no-version-check','--no-telemetry-prompts','--no-stats')
HERMES_EXPORTER_SHA256='750953cd48cd8cf7435a1c7427f5ff3e1c5d10fda9519cc7a4d3889e7d1b2ffa'
HERMES_SESSION=r'[A-Za-z0-9][A-Za-z0-9_:-]{0,199}'


def local(name):
    spec=importlib.util.spec_from_file_location('selected_capture_'+name,Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def source_time(value):
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})',value):
        return None
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    except ValueError:return None


def authorization(value):
    if type(value) is not str or not value.strip() or len(value)>2048:
        raise ValueError('explicit selected-source authorization reference required')


def selected_hermes(existing_db,session,authorization_reference):
    """Use an already initialized native reader; never construct/migrate SessionDB.

    Compression lineage is the native conversation's lineage, not arbitrary
    children/forks. Bounds refuse oversized histories rather than truncate them.
    This entry point belongs inside the existing Hermes trust boundary.
    """
    authorization(authorization_reference)
    if type(session) is not str or not re.fullmatch(HERMES_SESSION,session):
        raise ValueError('exact native Hermes session required')
    first=existing_db.get_session(session)
    lineage=existing_db.get_compression_lineage(session) if first else []
    if (not first or type(lineage) is not list or not 1<=len(lineage)<=64 or
            session not in lineage or len(set(lineage))!=len(lineage) or
            any(type(x) is not str or not re.fullmatch(HERMES_SESSION,x) for x in lineage)):
        raise ValueError('bounded selected native compression lineage required')
    segments=[];count=0
    for identifier in lineage:
        meta=existing_db.get_session(identifier)
        if not meta or meta.get('id')!=identifier:raise ValueError('selected lineage changed during read')
        # Includes durable compacted display history, excludes rewound/deleted rows.
        messages=existing_db.get_messages(identifier,include_compacted=True,limit=10001-count)
        if type(messages) is not list or count+len(messages)>10000:
            raise ValueError('selected native messages exceed bounded export; retain source')
        count+=len(messages)
        segments.append(dict(id=identifier,messages=messages))
    return dict(id=session,title=first.get('title'),source=first.get('source'),
        started_at=first.get('started_at'),last_active=first.get('last_active'),
        lineage_session_ids=lineage,message_count=count,segments=segments)


def native_exporter(path):
    spec=importlib.util.spec_from_file_location('selected_native_hermes_export',path)
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native);return native


def codex_export_record(value):
    """Exclude identified private channels before any third-party rendering."""
    payload=value.get('payload',{});payload=payload if type(payload) is dict else {}
    kind=payload.get('type','')
    if value.get('type')=='turn_context':return None
    if (payload.get('channel',payload.get('phase')) in ('analysis','reasoning') or
            kind in ('reasoning','agent_reasoning','agent_reasoning_raw_content') or
            (type(kind) is str and kind.startswith('agent_reasoning'))):return None
    if value.get('type')=='response_item' and kind=='message' and payload.get('role') in ('system','developer'):return None
    item=payload.get('item',{})
    if type(item) is dict and (item.get('channel',item.get('phase')) in ('analysis','reasoning') or item.get('type') in ('Reasoning','AgentReasoning','reasoning')):
        return None
    private={'reasoning','reasoning_content','reasoning_details','codex_reasoning_items','encrypted_content',
        'base_instructions','developer_instructions','system_prompt','replacement_history'}
    def clean(item):
        if type(item) is dict:return {key:clean(child) for key,child in item.items() if key not in private}
        if type(item) is list:return [clean(child) for child in item]
        return item
    result=clean(value)
    if result.get('type')=='session_meta':result['payload'].pop('instructions',None)
    return result


def collect_hermes(spool,*,snapshot,exporter,scope,context,authorization_reference):
    """Render one explicitly selected native DTO; no native DB/config discovery."""
    authorization(authorization_reference)
    exporter=Path(exporter);info=exporter.lstat()
    if (not exporter.is_absolute() or exporter.resolve()!=exporter or not stat.S_ISREG(info.st_mode) or
            info.st_uid not in (0,os.getuid()) or info.st_mode&0o022 or
            hashlib.sha256(exporter.read_bytes()).hexdigest()!=HERMES_EXPORTER_SHA256):
        raise ValueError('reviewed pinned Hermes exporter required')
    if type(snapshot) is not dict or type(snapshot.get('id')) is not str or not re.fullmatch(HERMES_SESSION,snapshot['id']):
        raise ValueError('one selected native session dictionary required')
    source=spool.c.encoded(snapshot)
    if len(source)>local('capture_intake').MAX_EXPORT:raise ValueError('bounded native source required')
    source_sha=hashlib.sha256(source).hexdigest();session=dict(namespace='hermes',id=snapshot['id'])
    artifact='cap_'+uuid.uuid5(uuid.NAMESPACE_URL,json.dumps([scope,session,'hermes_native_export'],sort_keys=True)).hex
    with spool.connection() as db:
        prior=db.execute("SELECT request FROM items WHERE kind='artifact' AND artifact=? ORDER BY sequence DESC LIMIT 1",(artifact,)).fetchone()
    if prior:
        old=spool.c.decode(prior[0])
        if old['body']['source_range']['source_sha256']==source_sha and old['context']==context:
            return dict(changed=False,artifact_id=artifact,collection_scope='explicit_session_only')
    # Keep visible exchanges and tool diagnostics. Explicit reasoning channels,
    # system/developer prompts and private reasoning fields are not rendered.
    clean={k:snapshot.get(k) for k in ('id','title','source','started_at','last_active','lineage_session_ids')}
    clean['segments']=[];excluded=0;count=0
    segments=snapshot.get('segments')
    if type(segments) is not list or not 1<=len(segments)<=64:raise ValueError('bounded native segments required')
    for segment in segments:
        messages=[]
        if type(segment) is not dict or type(segment.get('messages')) is not list:raise ValueError('native messages required')
        for row in segment['messages']:
            count+=1
            if count>10000:raise ValueError('bounded native messages required')
            if (type(row) is not dict or row.get('role') not in ('user','assistant','tool') or
                    row.get('channel',row.get('phase')) in ('analysis','reasoning')):
                excluded+=1;continue
            messages.append({k:row[k] for k in ('role','content','tool_calls','tool_call_id','name','tool_name','created_at','timestamp') if k in row})
        clean['segments'].append(dict(id=segment.get('id'),messages=messages))
    clean['message_count']=sum(len(x['messages']) for x in clean['segments'])
    native=native_exporter(exporter)
    # Native force redaction precedes rendering; owned intake adds its own pass
    # over metadata, content and tool arguments before any retained export write.
    clean=native.redact_session_data(clean)
    rendered=native.render_session_markdown(clean).encode()
    gaps=['Native compacted display rows are included; rewound/deleted rows are excluded.',
        'System/developer prompts and explicitly identified reasoning channels/fields are excluded.',
        'Selected compression lineage is recorded; attachment/media completeness is unverified.',
        'Native redaction plus owned pattern redaction cannot prove arbitrary secrets are absent.']
    def native_time(value):
        if type(value) not in (int,float):return None
        try:return datetime.fromtimestamp(value,timezone.utc).isoformat().replace('+00:00','Z')
        except (ValueError,OverflowError,OSError):return None
    staged=spool.stage(rendered,scope=scope,context=context,session=session,collector='hermes_native_export',
        collector_version=native.EXPORTER_VERSION,source_sha256=source_sha,
        authorization_reference=authorization_reference,
        source_range=dict(start='message:0',end='message:'+str(count)),gaps=gaps,
        source_created_at=native_time(snapshot.get('started_at')),source_updated_at=native_time(snapshot.get('last_active')))
    return dict(changed=True,artifact_id=artifact,collection_scope='explicit_session_only',
        staged=staged,excluded_messages=excluded,visible_messages=clean['message_count'],models_started=0)


def collect_codex(spool,*,source,session,binary,scope,context,authorization_reference,source_gaps=(),source_segment=None):
    authorization(authorization_reference)
    binary=Path(binary);info=binary.lstat()
    if (not binary.is_absolute() or binary.resolve()!=binary or not stat.S_ISREG(info.st_mode) or
            info.st_uid not in (0,os.getuid()) or info.st_mode&0o022 or not info.st_mode&0o111 or
            hashlib.sha256(binary.read_bytes()).hexdigest()!=SPECSTORY_SHA256):
        raise ValueError('reviewed pinned collector executable required')
    association=dict(namespace='codex',id=session)
    artifact=local('capture_intake').artifact_identity(scope,association,'specstory',source_segment)
    pilot=local('capture_pilot');raw,rows=pilot.selected_source(source,session)
    source_sha=hashlib.sha256(raw).hexdigest()
    gaps=['Collector input relocates only session_meta.cwd into a private temporary Git repository.',
        'Original native source remains under its original owner; only the normalized export is ingested.',
        'Full tool, attachment and media coverage is not independently established.']
    gaps.append('Explicit system/developer/analysis/reasoning records and known private reasoning/instruction fields are excluded before collector input.')
    if type(source_gaps) not in (list,tuple) or len(source_gaps)>8 or any(type(value) is not str or not 1<=len(value.encode())<=4096 for value in source_gaps):
        raise ValueError('bounded source transport limitations required')
    gaps.extend(source_gaps)
    if source_segment is not None:gaps.append('This export covers only the selected native session segment '+source_segment+'.')
    with spool.connection() as db:
        latest=db.execute("SELECT request FROM items WHERE kind='artifact' AND artifact=? ORDER BY sequence DESC LIMIT 1",(artifact,)).fetchone()
    if latest:
        old=spool.c.decode(latest[0]);end=old['body']['source_range']['end']
        end_prefix='byte:' if source_segment is None else 'segment:'+source_segment+':byte:'
        if type(end) is str and end.startswith(end_prefix) and end[len(end_prefix):].isdigit():
            length=int(end[len(end_prefix):])
            if len(raw)<length or hashlib.sha256(raw[:length]).hexdigest()!=old['body']['source_range']['source_sha256']:
                gaps.append('Native prefix shortened or changed before the last observed cursor; prior export remains immutable and coverage may have a gap.')
        if old['body']['source_range']['source_sha256']==source_sha and old['context']==context:
            return dict(changed=False,source_sha256=source_sha,artifact_id=artifact,collection_scope='explicit_session_only')
    with tempfile.TemporaryDirectory(prefix='collector-',dir=spool.root) as folder:
        root=Path(folder);root.chmod(0o700)
        home=root/'home';repo=root/'repo';home.mkdir(mode=0o700);repo.mkdir(mode=0o700)
        sessions=home/'.codex/sessions/2026/11/07';sessions.mkdir(parents=True,mode=0o700)
        moved=[]
        for line in raw.splitlines(keepends=True):
            value=codex_export_record(json.loads(line))
            if value is None:continue
            if value.get('type')=='session_meta':
                value['payload']['cwd']=str(repo)
            moved.append((json.dumps(value,ensure_ascii=False)+'\n').encode())
        path=sessions/('rollout-2026-11-07T00-00-00-'+session+'.jsonl')
        with path.open('xb') as f:os.fchmod(f.fileno(),0o600);f.write(b''.join(moved))
        env=dict(HOME=str(home),PATH='/usr/bin:/bin',LANG='C.UTF-8',CI='1',DO_NOT_TRACK='1',
            GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null')
        git=subprocess.run(['/usr/bin/git','init','-q',str(repo)],env=env,capture_output=True,timeout=10)
        if git.returncode:raise ValueError('private collector scratch repository unavailable')
        output=root/'output';error=root/'error'
        with output.open('xb') as stdout,error.open('xb') as stderr:
            os.fchmod(stdout.fileno(),0o600);os.fchmod(stderr.fileno(),0o600)
            result=subprocess.run([str(binary),'sync','codex',*FLAGS,'--print','-s',session],cwd=repo,env=env,
                stdout=stdout,stderr=stderr,timeout=45,umask=0o077)
        if result.returncode:raise ValueError('selected collector failed; retain original source and report capture gap')
        limit=local('capture_intake').MAX_EXPORT
        if output.stat().st_size>limit:raise ValueError('selected export exceeds intake bound; retain original source')
        export=output.read_bytes();text=export.decode('utf-8')
        for row in rows:
            payload=row.get('payload') or {}
            if row.get('type')=='response_item' and payload.get('type')=='message' and payload.get('channel',payload.get('phase')) in ('analysis','reasoning'):
                for part in payload.get('content',[]):
                    excluded=part.get('text','')
                    if type(excluded) is str and len(excluded.strip())>=32 and excluded in text:
                        raise ValueError('collector included an explicitly excluded reasoning/analysis channel')
        coverage=pilot.response_coverage(rows,text)
        if coverage['unmatched_visible_or_unknown_messages']:
            gaps.append(str(coverage['unmatched_visible_or_unknown_messages'])+
                ' visible or unknown source messages were not found verbatim in the collector output; formatting or redaction may affect this comparison.')
        if not text.strip():gaps.append('Collector exited successfully but produced no readable conversation text.')
        range_prefix='byte:' if source_segment is None else 'segment:'+source_segment+':byte:'
        staged=spool.stage(export,scope=scope,context=context,session=association,collector='specstory',source_segment=source_segment,
            authorization_reference=authorization_reference,
            collector_version=SPECSTORY_VERSION,source_sha256=source_sha,
            source_range=dict(start=range_prefix+'0',end=range_prefix+str(len(raw))),gaps=gaps,
            source_created_at=source_time(rows[0].get('timestamp')),
            source_updated_at=source_time(rows[-1].get('timestamp')))
    return dict(changed=True,source_sha256=source_sha,collection_scope='explicit_session_only',
        collector_version=SPECSTORY_VERSION,coverage=coverage,staged=staged,models_started=0)
