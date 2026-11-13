"""Normalize one independently read native Linear issue for admission."""
import importlib.util
from pathlib import Path


def local(name):
    spec = importlib.util.spec_from_file_location('linear_issue_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


QUERY = '''query AdmissionNativeIssue($id: String!) {
 viewer { id organization { id } }
 issue(id: $id) { id team { id } project { id } }
}'''


class Reader:
    def __init__(self, graphql, viewer_id, organization_id):
        identifier = local('onboarding_drafts').identifier
        identifier(viewer_id);identifier(organization_id)
        if not callable(graphql):raise ValueError('protected native issue transport required')
        self.graphql, self.viewer_id, self.organization_id = graphql, viewer_id, organization_id

    def __call__(self, issue_id):
        identifier = local('onboarding_drafts').identifier
        identifier(issue_id)
        result = self.graphql({'query':QUERY, 'variables':{'id':issue_id}})
        if type(result) is not dict or result.get('errors') or type(result.get('data')) is not dict:
            raise ValueError('native issue unavailable')
        data = result['data'];viewer = data.get('viewer');issue = data.get('issue')
        if (type(viewer) is not dict or viewer.get('id') != self.viewer_id or
                type(viewer.get('organization')) is not dict or viewer['organization'].get('id') != self.organization_id or
                type(issue) is not dict or issue.get('id') != issue_id or
                type(issue.get('team')) is not dict or type(issue.get('project')) is not dict):
            raise ValueError('native issue identity differs')
        team = issue['team'].get('id');project = issue['project'].get('id')
        identifier(team);identifier(project)
        return dict(organization_id=self.organization_id, team_id=team, linear_project_id=project, issue_id=issue_id)
