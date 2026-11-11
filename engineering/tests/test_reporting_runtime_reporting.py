"""Automatic work-start and terminal reports without asking an operator to log."""
import copy
import importlib.util
from pathlib import Path
import pytest
from test_reporting_capture_intake import store,projects,evidence,reporting,sender,events
from test_history_reporting import request as history_request
from test_reporting_codex_runtime import m as runtime_module,Client,uid

ROOT=Path(__file__).resolve().parents[1]/'tools/rras_reporting'
spec=importlib.util.spec_from_file_location('automatic_runtime_reporting_test',ROOT/'runtime_reporting.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def setup(tmp_path,projects):
    ctx=history_request(projects,'checkpoint.report')['context'];issue=uid(3)
    policy=dict(contract='codex-runtime-policy.v1',organization_id=uid(1),app_user_id=uid(2),
        execution_authorized=True,execution_authority_reference='Synthetic model-free runtime only',
        binary=str(tmp_path/'synthetic-codex'),cwd=str(tmp_path),sandbox='read-only',issues={issue:dict(project_id=ctx['project_id'],
            work_id=ctx['work']['work_item_id'],plan_id='SHRR-03',work_revision_sha256=ctx['work']['work_revision_sha256'],
            architecture_version=ctx['architecture']['version'],architecture_sha256=ctx['architecture']['markdown_sha256'])})
    intake=m.local('capture_intake');spool=intake.Spool(tmp_path/'spool',create=True)
    config=dict(contract='codex-runtime-reporting.v1',spool=str(spool.root),scope=dict(kind='repository',id='jarvis'),
        contexts={issue:ctx},host_identity='synthetic-host',oauth_client_id=None,capture=None)
    reporter=m.Reporter(config,policy)
    request=dict(contract='codex-dispatch.v1',dispatch_id=uid(4),organization_id=uid(1),app_user_id=uid(2),
        session_id=uid(5),issue_id=issue,message='Synthetic task, no model',binding=policy['issues'][issue])
    return policy,config,spool,reporter,request


def test_start_is_staged_before_native_generation_and_terminal_is_automatic(tmp_path,projects,evidence,reporting):
    policy,config,spool,reporter,request=setup(tmp_path,projects)
    class Observed(Client):
        def call(self,method,params):
            if method=='turn/start':
                with spool.connection() as db:
                    saved=[spool.c.decode(x[0]) for x in db.execute('SELECT request FROM items')]
                assert any(x['operation']=='attempt.record' and x['body']['phase']=='started' for x in saved)
                assert any(x['operation']=='checkpoint.report' for x in saved)
            return super().call(method,params)
    client=Observed();runtime=runtime_module.Runtime(tmp_path/'runtime',policy,create=True,client_factory=lambda *a:client,reporter=reporter)
    try:
        runtime.dispatch(request);client.finish('completed');runtime.status(uid(4))
        assert spool.flush(sender(reporting))['pending']==0
        rows=[r for r,_ in events(reporting)]
        assert rows[0]['operation']=='attempt.record' and rows[0]['body']['phase']=='started'
        assert any(r['operation']=='attempt.record' and r['body']['phase']=='completed' for r in rows)
        metadata=next(r['body'] for r in rows if r['operation']=='session.describe')
        assert metadata['native_session_tree_id']=='root-lineage-1'
        assert metadata['linear_agent_session_id']==uid(5) and metadata['actor']['source_actor_id']==uid(2)
        assert metadata['tokens'] is None and metadata['cost_usd'] is None and metadata['model'] is None
        assert not any(r['operation'] in ('decision.observe','mapping.record') for r in rows)
        before=len(rows);runtime.status(uid(4));assert spool.flush(sender(reporting))['delivered']==0
        assert len(events(reporting))==before
    finally:runtime.close()


def test_history_outage_replay_preserves_start_and_honest_terminal_reports(tmp_path,projects,evidence,reporting):
    policy,config,spool,reporter,request=setup(tmp_path,projects);client=Client()
    runtime=runtime_module.Runtime(tmp_path/'runtime',policy,create=True,client_factory=lambda *a:client,reporter=reporter)
    try:
        runtime.dispatch(request)
        assert spool.flush(lambda _:(_ for _ in ()).throw(OSError('fixture outage')))['pending']
        client.finish('interrupted');runtime.status(uid(4))
        assert spool.flush(sender(reporting))['pending']==0
        rows=[r for r,_ in events(reporting)]
        assert any(r['operation']=='attempt.record' and r['body']['phase']=='interrupted' for r in rows)
        assert sum(k=='turn/start' for k,_ in client.calls)==1
        assert any('not' in r['body']['validation'][0]['description'] for r in rows if r['operation']=='checkpoint.report')
    finally:runtime.close()


def test_issue_workspace_is_retained_in_session_metadata(tmp_path,projects,evidence,reporting):
    policy,config,spool,_,request=setup(tmp_path,projects)
    policy['contract']='codex-runtime-policy.v2';policy['workspaces']={uid(3):str(tmp_path/'issue-workspace')}
    reporter=m.Reporter(config,policy);client=Client()
    runtime=runtime_module.Runtime(tmp_path/'runtime-v2',policy,create=True,client_factory=lambda *a:client,reporter=reporter)
    try:
        runtime.dispatch(request);client.finish('completed');runtime.status(uid(4))
        assert spool.flush(sender(reporting))['pending']==0
        metadata=next(r['body'] for r,_ in events(reporting) if r['operation']=='session.describe')
        assert metadata['workspace_identity']==policy['workspaces'][uid(3)]
    finally:runtime.close()


def test_reporting_capacity_failure_does_not_rerun_or_block_authorized_work(tmp_path,projects,evidence,reporting,monkeypatch):
    policy,config,spool,reporter,request=setup(tmp_path,projects)
    monkeypatch.setattr(reporter.intake,'MAX_ITEMS',0);client=Client()
    runtime=runtime_module.Runtime(tmp_path/'runtime',policy,create=True,client_factory=lambda *a:client,reporter=reporter)
    try:
        assert runtime.dispatch(request)['state']=='running'
        with runtime.connection() as db:
            saved=[runtime_module.json.loads(x[0]) for x in db.execute('SELECT body FROM events')]
        assert any(x['method']=='adapter/reportingGap' for x in saved)
        monkeypatch.setattr(reporter.intake,'MAX_ITEMS',10000)
        runtime.status(uid(4));client.finish('completed');runtime.status(uid(4))
        assert spool.flush(sender(reporting))['pending']==0
        assert sum(k=='turn/start' for k,_ in client.calls)==1
    finally:runtime.close()


def test_unknown_work_context_refused_before_runtime_or_source_capture(tmp_path,projects,reporting):
    policy,config,spool,reporter,request=setup(tmp_path,projects)
    changed=copy.deepcopy(config);changed['contexts'][uid(3)]['work']['work_revision_sha256']='0'*64
    with pytest.raises(ValueError,match='pin differs'):m.Reporter(changed,policy)


def test_exact_native_capture_job_registered_without_scanning_or_running_collector(tmp_path,projects,reporting):
    policy,config,spool,reporter,request=setup(tmp_path,projects)
    native=tmp_path/'native';native.mkdir(mode=0o700);jobs=tmp_path/'jobs';jobs.mkdir(mode=0o700)
    config['capture']=dict(binary=str(tmp_path/'pinned-specstory'),native_root=str(native),jobs=str(jobs),
        authorization_reference='Synthetic installed selected-runtime capture only',service_socket=str(tmp_path/'history.sock'),service_uid=995)
    reporter=m.Reporter(config,policy);row=dict(session=uid(5),issue=uid(3),thread=uid(6))
    metadata=dict(path=str(native/'selected.jsonl'))
    assert reporter.register_capture(row,metadata)
    assert not (native/'selected.jsonl').exists() and len(list(jobs.glob('*.json')))==1
    assert reporter.register_capture(row,metadata) and len(list(jobs.glob('*.json')))==1
    with pytest.raises(ValueError):reporter.register_capture(row,dict(path=str(tmp_path/'unrelated-private.jsonl')))
