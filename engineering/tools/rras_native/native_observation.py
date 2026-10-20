"""Read-only observation of a protected copy of one stopped native board.

Observes stored facts, not authenticated worker behavior or validated deliverables.
No native import, lifecycle mutation, model, validation recipe, network or retry.
"""
import importlib.util
import os
from pathlib import Path
import sqlite3
import stat

SOURCE = Path('/opt/rras-engineering/releases/native-10/hermes/hermes_cli/kanban_db.py')
SOURCE_SHA256 = 'e5974182db556462b7cf85719ed5b40045aea7ea8f648ff82305c8e3b674603c'
LIMIT = 16 * 1024 * 1024
TASK_STATUSES = {'todo','ready','running','review','blocked','done','cancelled','triage'}
RUN_STATUSES = {'running','done','blocked','crashed','timed_out','failed','released','reclaimed'}
OUTCOMES = {None,'completed','blocked','crashed','timed_out','spawn_failed','gave_up','reclaimed'}


def local(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def decode(raw):return local('workflow_journal').decode(raw)


def inspect_snapshot(path,host,evidence,context):
    """Select only fixed mechanical fields; never import native code or free text."""
    if not context or not isinstance(evidence.get('wait'),dict):
        raise ValueError('bound native context and wait report required')
    expected = Path(host['work'])/'home/kanban/kanban.db'
    if context['board']!=str(expected) or context['task']!=evidence['native_task'] or context['run_id']!=evidence['native_run']:
        raise ValueError('native observation context mismatch')
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('exact snapshot path required')
    db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=1)
    try:
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA query_only=ON')
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH,1024*1024)
        db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED,0)
        budget=[0]
        def progress():
            budget[0]+=1
            return int(budget[0]>2000)
        db.set_progress_handler(progress,1000)
        if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('native snapshot integrity failed')
        for table in ('tasks','task_runs'):
            schema=db.execute('SELECT type,sql FROM sqlite_schema WHERE name=?',(table,)).fetchall()
            if len(schema)!=1 or schema[0][0]!='table' or not schema[0][1].lstrip().upper().startswith('CREATE TABLE'):
                raise ValueError('ordinary native tables required')
        if db.execute('SELECT count(*) FROM tasks').fetchone()!=(1,) or db.execute('SELECT count(*) FROM task_runs').fetchone()!=(1,):
            raise ValueError('single-task single-run board required')
        tasks=db.execute('SELECT id,status,assignee,workspace_path,current_run_id,completed_at,worker_pid,claim_lock,claim_expires FROM tasks WHERE id=?',(context['task'],)).fetchall()
        runs=db.execute('SELECT id,task_id,profile,status,outcome,started_at,ended_at,worker_pid,claim_lock,claim_expires FROM task_runs WHERE id=?',(context['run_id'],)).fetchall()
        if len(tasks)!=1 or len(runs)!=1:raise ValueError('exact task/run absent from snapshot')
        t,r=tasks[0],runs[0]
        if t[2]!='rras-engineering' or r[1]!=t[0] or r[2]!='rras-engineering' or t[3]!=evidence['workspace']:
            raise ValueError('native task profile/workspace mismatch')
        if t[1] not in TASK_STATUSES or r[3] not in RUN_STATUSES or r[4] not in OUTCOMES:
            raise ValueError('unreviewed native status')
        if type(r[0]) is not int or type(r[5]) is not int or r[5]<0 or (r[6] is not None and (type(r[6]) is not int or r[6]<r[5])):
            raise ValueError('invalid run identity/time fields')
        if t[5] is not None and (type(t[5]) is not int or t[5]<0):raise ValueError('invalid task completion time')
        owners_clear=all(v is None for v in (t[4],t[6],t[7],t[8],r[7],r[8],r[9]))
        completed=owners_clear and t[1]=='done' and r[3]=='done' and r[4]=='completed' and r[6] is not None and t[5] is not None
        if completed and not r[5]<=t[5]<=r[6]:raise ValueError('native completion timestamp outside run')
        closed_failure=owners_clear and r[3] not in {'running','done'} and r[4] not in (None,'completed') and r[6] is not None and t[1]!='done'
        state='completed' if completed else 'failed' if closed_failure else 'incomplete'
        wait=evidence['wait']
        agrees=wait.get('native_status')==t[1] and type(wait.get('success')) is bool and wait['success']==completed
        return {'schema_version':1,'native_task':t[0],'native_run':r[0],'task_status':t[1],
            'run_status':r[3],'run_outcome':r[4],'run_started_at':r[5],'run_ended_at':r[6],
            'task_completed_at':t[5],'ownership_fields_clear':owners_clear,'stored_state':state,
            'agrees_with_captured_wait_report':agrees,'worker_behavior_authenticated':False,
            'independent_validation_performed':False,'release_status':'not_inferred'}
    finally:db.close()


def capture(finish_custody,destination):
    finish,review,members=local('workflow_finish').load(finish_custody)
    evidence=decode(members['evidence.json'])
    if 'native-context.json' not in members:raise ValueError('no bound native context to observe')
    context=decode(members['native-context.json']);host=decode(members['host-result.json'])
    board=Path(host['work'])/'home/kanban/kanban.db'
    if context['board']!=str(board):raise ValueError('native board outside assigned run')
    read_root=local('publication_custody').root_bytes;a=local('activity')
    if a.digest(read_root(SOURCE,1024*1024))!=SOURCE_SHA256:raise ValueError('pinned native schema source changed')
    destination=Path(destination)
    if not destination.is_absolute():raise ValueError('absolute observation destination required')
    local('approved_launch').trusted(destination.parent)
    if destination.exists() or destination.is_symlink():raise ValueError('fresh native observation required')
    slot=local('approved_launch').slot;read_worker=local('publication_capture').worker_bytes
    slot()
    # Read raw bytes once. Never open SQLite against the worker tree, checkpoint,
    # repair or discard a journal. Nonempty sidecars require explicit recovery.
    for suffix in ('-wal','-journal','-shm'):
        sidecar=Path(str(board)+suffix)
        if sidecar.exists() or sidecar.is_symlink():
            if read_worker(sidecar,1024*1024):raise ValueError('native sidecar requires separate consistent-snapshot recovery')
    raw=read_worker(board,LIMIT)
    slot()
    destination.mkdir(mode=0o700);a.fsync_directory(destination.parent)
    a.absent(destination/'board.sqlite3',raw)
    facts=inspect_snapshot(destination/'board.sqlite3',host,evidence,context)
    receipt={'schema_version':1,'authorization_id':finish['authorization_id'],'review_id':finish['review_id'],
        'finish_capture_sha256':a.digest(a.encoded(finish)),'source_sha256':SOURCE_SHA256,
        'snapshot_sha256':a.digest(raw),'facts':facts}
    a.absent(destination/'observation.json',a.encoded(receipt))
    return {'captured':True,'stored_state':facts['stored_state'],'agrees_with_report':facts['agrees_with_captured_wait_report'],
        'native_database_changed':False,'execution_retried':False,'task_success_established':False}


def record(finish_custody,observation):
    finish,review,members=local('workflow_finish').load(finish_custody)
    a=local('activity');root=Path(observation);read=local('publication_custody').root_bytes
    local('approved_launch').trusted(Path(__file__))
    if not root.is_absolute() or stat.S_IMODE(root.stat().st_mode)!=0o700:raise ValueError('private native observation required')
    receipt=decode(read(root/'observation.json',1024*1024));raw=read(root/'board.sqlite3',LIMIT)
    if (receipt.get('schema_version')!=1 or receipt['authorization_id']!=finish['authorization_id'] or receipt['review_id']!=finish['review_id'] or
            receipt['finish_capture_sha256']!=a.digest(a.encoded(finish)) or receipt['source_sha256']!=SOURCE_SHA256 or
            receipt['snapshot_sha256']!=a.digest(raw)):
        raise ValueError('native observation association changed')
    facts=inspect_snapshot(root/'board.sqlite3',decode(members['host-result.json']),decode(members['evidence.json']),decode(members['native-context.json']))
    if facts!=receipt['facts']:raise ValueError('native observation facts changed')
    local('workflow_finish').record(finish_custody)
    events=local('managed_events');store=events.journal(review);actor={'type':'service','id':'native-state-observer'}
    auth=finish['authorization_id'];work=review['admission']['work_item'];payload=a.encoded(receipt);sha=a.digest(payload)
    # Never replace the imported terminal claim with an authenticated-success claim.
    event={'event_id':events.stable('evt_',auth,'native-state-observed'),'work_item_id':work['work_item_id'],
        'work_item_sha256':review['admission']['work_item_sha256'],'attempt_id':events.stable('att_',auth),
        'actor':actor,'provenance':{'kind':'observed','source':{'namespace':'external','id':'native-board-snapshot:'+sha},'source_sha256':sha,'recorded_by':actor},
        'event_type':'artifact.recorded','outcome':'succeeded' if facts['agrees_with_captured_wait_report'] and facts['stored_state']!='incomplete' else 'uncertain',
        'summary':'Read-only native database snapshot observed; stored state does not authenticate worker behavior, validation or release.',
        'artifacts':[{'artifact_id':events.stable('art_',auth,'native-state-observation'),'sha256':sha,'media_type':'application/json','visibility':'operator_only','purpose':'execution'}],
        'references':[{'namespace':'authorization','id':auth},{'namespace':'native_task','id':facts['native_task']},{'namespace':'native_run','id':str(facts['native_run'])}],
        'corrects_event_id':None,'decision_subject':None}
    store.append([],{sha:payload},transition=(event,None))
    return {'recorded':True,'stored_state':facts['stored_state'],'agrees_with_report':facts['agrees_with_captured_wait_report'],
        'worker_behavior_authenticated':False,'execution_retried':False,'task_success_established':False}
