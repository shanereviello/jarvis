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
        if (type(value) is not dict or set(value)!={'contract','projects'} or
                value['contract']!='hermes-planning-project-scopes.v1' or type(value['projects']) is not dict or
                not 1<=len(value['projects'])<=512):
            raise ValueError('exact protected project scopes required')
        for key,scope in value['projects'].items():drafts.identifier(key);drafts.selected_scope(scope)
        if project_id not in value['projects']:raise ValueError('project scope is not configured')
        return drafts.selected_scope(value['projects'][project_id])
