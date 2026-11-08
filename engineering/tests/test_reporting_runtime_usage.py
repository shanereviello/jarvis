"""Native numeric usage summaries remain distinct from billing and turn totals."""
import copy
from test_reporting_runtime_reporting import setup,m,projects,store,reporting,evidence,sender,events
from test_reporting_codex_runtime import m as runtime_module,Client,uid


def usage(turn='turn-1'):
    return dict(method='thread/tokenUsage/updated',params=dict(threadId='thread-1',turnId=turn,tokenUsage=dict(
        total=dict(inputTokens=100,outputTokens=20,cachedInputTokens=40,reasoningOutputTokens=5,totalTokens=120,reasoning='EXCLUDED-REASONING-TEXT'),
        last=dict(inputTokens=10,outputTokens=2,cachedInputTokens=0,totalTokens=12),private_detail='EXCLUDED-REASONING-TEXT')))


def test_configured_model_and_late_usage_are_retained_without_reopening_terminal_attempt(tmp_path,projects,evidence,reporting):
    policy,config,spool,reporter,request=setup(tmp_path,projects)
    class Configured(Client):
        def call(self,method,params):
            result=super().call(method,params)
            if method in ('thread/start','thread/resume'):result.update(model='synthetic-configured-model',modelProvider='fixture')
            return result
    client=Configured();runtime=runtime_module.Runtime(tmp_path/'runtime',policy,create=True,reporter=reporter,client_factory=lambda *a:client)
    try:
        runtime.dispatch(request);client.finish('completed');runtime.status(uid(4))
        assert spool.flush(sender(reporting))['pending']==0
        before=[r for r,_ in events(reporting)]
        assert next(r['body'] for r in before if r['operation']=='session.describe')['model']=='synthetic-configured-model'
        client.waiting.append(usage());runtime.status(uid(4));assert spool.flush(sender(reporting))['pending']==0
        after=[r for r,_ in events(reporting)];metadata=[r['body'] for r in after if r['operation']=='session.describe']
        assert len(metadata)==2 and metadata[-1]['tokens']==dict(input=100,output=20,cached_input=40,reasoning_output=5,total=120)
        assert metadata[-1]['last_reported_tokens']==dict(input=10,output=2,cached_input=0,total=12)
        assert metadata[-1]['tokens_basis']=='native_thread_summary' and metadata[-1]['usage_native_turn_id']=='turn-1'
        assert metadata[-1]['cost_usd'] is None and 'cache_write_input' not in metadata[-1]['tokens']
        assert sum(r['operation']=='attempt.record' and r['body']['phase']=='completed' for r in after)==1
        with runtime.connection() as db:assert b'EXCLUDED-REASONING-TEXT' not in b''.join(x[0] for x in db.execute('SELECT body FROM events'))
        client.waiting.append(usage());runtime.status(uid(4));assert spool.flush(sender(reporting))['delivered']==0
        continued=dict(request,dispatch_id=uid(8));runtime.dispatch(continued)
        assert spool.flush(sender(reporting))['pending']==0
        latest=[r['body'] for r,_ in events(reporting) if r['operation']=='session.describe'][-1]
        assert latest['tokens']==metadata[-1]['tokens'] and latest['usage_native_turn_id']=='turn-1'
        assert sum(method=='turn/start' for method,_ in client.calls)==2
    finally:runtime.close()


def test_numeric_projection_refuses_bad_counters_and_drops_private_payloads():
    projected=runtime_module.journal_event(usage())
    assert 'EXCLUDED-REASONING-TEXT' not in str(projected)
    for value in (True,-1,2**53,'100'):
        bad=usage();bad['params']['tokenUsage']['total']['inputTokens']=value
        assert runtime_module.journal_event(bad) is None
    assert runtime_module.journal_event(dict(method='item/reasoning/textDelta',params=dict(delta='EXCLUDED')) ) is None
