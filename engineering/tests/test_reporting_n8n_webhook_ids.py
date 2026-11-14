"""CLI-imported webhook nodes must retain unique direct-route registration IDs."""
from test_reporting_n8n_codex import m as codex, config as codex_config
from test_reporting_n8n_handoff import m as handoff, configuration
from test_reporting_n8n_linear_observer import m as linear, config as linear_config
from test_reporting_native_handoff import uid


def test_all_eight_webhooks_have_distinct_stable_registration_ids():
    c=configuration()
    policy=c['policy']
    package=codex.render(codex_config.__wrapped__())['workflows']
    workflows=list(package.values())+list(handoff.local('n8n_handoff').render(c)['workflows'].values())
    context=handoff.local('n8n_hermes_context')
    workflows.extend([context.render(c),context.checkpoint(c),linear.render(linear_config())])
    pin=next(iter(policy['issues'].values()))
    project=pin['project_id']
    selected=dict(contract='native-handoff-history-source.v1',policy=policy,scope=dict(kind='repository',id='jarvis'),
        contexts={next(iter(policy['issues'])):[dict(binding=pin,context=dict(project_id=project,
            architecture=dict(document_id='doc_'+'3'*32,version=pin['architecture_version'],markdown_sha256=pin['architecture_sha256']),
            work=dict(work_item_id=pin['work_id'],work_revision_sha256=pin['work_revision_sha256'],assignment_sha256='a'*64)))]})
    workflows.append(handoff.local('n8n_handoff_history').render(selected,'fixture-pg','fixture-reader'))
    workflows.append(handoff.local('n8n_hermes_history').render(dict(selected,contract='hermes-runtime-history-source.v1'),'fixture-pg','fixture-reader'))
    webhooks=[node for workflow in workflows for node in workflow['nodes'] if node['type']=='n8n-nodes-base.webhook']
    assert len(webhooks)==8
    assert all(node['webhookId']==node['id'] for node in webhooks)
    assert len({node['webhookId'] for node in webhooks})==8
    assert len({node['parameters']['path'] for node in webhooks})==8
