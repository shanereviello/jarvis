"""Planning-only Jarvis tools bound to the actual native Linear run.

The protected transport must resolve and reverify the run on every operation.
This adapter cannot designate an architecture or authorize execution.
"""
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator


def local(name):
    spec = importlib.util.spec_from_file_location('hermes_planning_'+name,Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Adapter:
    def __init__(self, call, *, actual=None, allow_create=False, allow_review=False):
        if not callable(call) or type(allow_create) is not bool or type(allow_review) is not bool:
            raise ValueError('protected planning transport and explicit tool scope required')
        self.call,self.actual = call,actual or local('hermes_native_context').actual
        self.allow_create,self.allow_review = allow_create,allow_review

    def schemas(self):
        m = local('onboarding_mcp');values = dict(m.SCHEMAS)
        if self.allow_create:values['engineering_draft_issue'] = m.CREATE_SCHEMA
        if self.allow_review:values['engineering_prepare_review'] = m.REVIEW_SCHEMA
        return values

    def invoke(self, name, arguments):
        schemas = self.schemas()
        if name not in schemas:raise ValueError('planning operation unavailable')
        Draft202012Validator(schemas[name]).validate(arguments)
        native = self.actual();context = local('hermes_native_context')
        if (type(native) is not dict or set(native) != {'organization_id','session_id','hermes_session_id','run_id'} or
                context.parse('api_server',native['hermes_session_id'],native['run_id']) != native):
            raise ValueError('actual native Linear run required')
        # This transport is operator-configured and must consult native run
        # state; agent arguments cannot supply identities or origin evidence.
        origin = self.call('resolve',dict(contract='hermes-planning-native.v1',native=native))
        if type(origin) is not dict or set(origin) != {'dispatch_id','origin','execution_authorized'} or origin['execution_authorized'] is not False:
            raise ValueError('protected planning origin unavailable')
        drafts = local('onboarding_drafts');dispatch = drafts.identifier(origin['dispatch_id']);verified = drafts.verified(origin['origin'])
        if (verified['agent'] != 'jarvis' or verified['organization_id'] != native['organization_id'] or
                verified['source_session'] != native['session_id']):
            raise ValueError('native planning origin differs')
        operation = {'engineering_draft_project':'draft.project','engineering_draft_work':'draft.work',
                     'engineering_draft_issue':'draft.issue','engineering_prepare_review':'review.prepare'}[name]
        message = dict(operation=operation,dispatch_id=dispatch,**arguments)
        result = self.call('submit',dict(contract='hermes-planning-submit.v1',native=native,message=message))
        if type(result) is not dict or result.get('execution_authorized') is not False:
            raise ValueError('planning outcome unconfirmed')
        return result


def register(ctx, adapter_factory, *, allow_create=False, allow_review=False):
    if not callable(adapter_factory):raise ValueError('configured protected adapter required')
    template = Adapter(lambda *_:None,allow_create=allow_create,allow_review=allow_review)
    def handle(name, arguments):
        try:return json.dumps(adapter_factory().invoke(name,arguments))
        except Exception:return json.dumps({'error':'Planning request refused or unconfirmed; inspect retained state before retry.',
                                            'execution_authorized':False})
    for name,schema in template.schemas().items():
        ctx.register_tool(name=name,toolset='engineering_planning',schema=dict(name=name,
            description='Retain or link a proposed architecture or work item for this verified Jarvis session; no approval or execution is granted.',
            parameters=schema),handler=lambda arguments,_name=name,**_:handle(_name,arguments))


def register_configured(ctx, config_path):
    protected=local('protected_config');config=protected.decode(config_path,require_root=True,maximum=65536)
    if (type(config) is not dict or set(config)!={'contract','origin','token_file','allow_create','allow_review'} or
            config['contract']!='hermes-planning-config.v1' or type(config['allow_create']) is not bool or
            type(config['allow_review']) is not bool):
        raise ValueError('exact protected planning configuration required')
    register(ctx,lambda:local('hermes_planning_transport').configured(config_path),
        allow_create=config['allow_create'],allow_review=config['allow_review'])
