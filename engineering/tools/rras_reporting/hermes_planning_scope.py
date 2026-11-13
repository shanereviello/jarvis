"""Resolve project scope from protected configuration, never agent text."""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('hermes_scope_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Resolver:
    def __init__(self,path):
        self.path=Path(path)
        if not self.path.is_absolute():raise ValueError('protected scope configuration required')

    def __call__(self, project_id):
        drafts=local('onboarding_drafts');drafts.identifier(project_id)
        value=local('protected_config').decode(self.path,require_root=True,maximum=65536)
        if (type(value) is not dict or set(value) not in ({'contract','projects'},{'contract','projects','fallback_scope'}) or
                value['contract']!='hermes-planning-project-scopes.v1' or type(value['projects']) is not dict or
                len(value['projects'])>512):
            raise ValueError('exact protected project scopes required')
        for key,scope in value['projects'].items():drafts.identifier(key);drafts.selected_scope(scope)
        fallback=value.get('fallback_scope')
        if fallback is not None:
            fallback=drafts.selected_scope(fallback)
            if fallback['kind']!='non_git':raise ValueError('fallback must be a protected non-Git scope')
        if project_id in value['projects']:return drafts.selected_scope(value['projects'][project_id])
        if fallback is None:raise ValueError('project scope is not configured')
        return fallback
