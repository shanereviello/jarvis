"""Normalize one native Linear comment from a protected GraphQL transport.

This reader performs no writes and never treats model-authored JSON as a
native response. Its injected transport must authenticate the configured
Linear application and must not expose credentials to a planning agent.
"""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('linear_comment_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


QUERY='''query ArchitectureDecisionComment($id: String!) {
 viewer { id organization { id } }
 comment(id: $id) {
  id body createdAt editedAt archivedAt
  botActor { type } externalUser { id } onBehalfOf { id }
  user { id app } issue { id team { id } project { id } }
 }
}'''


class Reader:
    def __init__(self,graphql,viewer_id,organization_id):
        d=local('onboarding_drafts');d.identifier(viewer_id);d.identifier(organization_id)
        if not callable(graphql):raise ValueError('protected native GraphQL transport required')
        self.graphql,self.viewer_id,self.organization_id=graphql,viewer_id,organization_id

    def __call__(self,comment_id):
        local('onboarding_drafts').identifier(comment_id)
        result=self.graphql({'query':QUERY,'variables':{'id':comment_id}})
        if type(result) is not dict or result.get('errors') or type(result.get('data')) is not dict:
            raise ValueError('native comment unavailable')
        data=result['data'];viewer=data.get('viewer');comment=data.get('comment')
        if (type(viewer) is not dict or viewer.get('id')!=self.viewer_id or
                type(viewer.get('organization')) is not dict or viewer['organization'].get('id')!=self.organization_id or
                type(comment) is not dict or comment.get('id')!=comment_id):
            raise ValueError('native reader identity differs')
        required={'id','body','createdAt','editedAt','archivedAt','botActor','externalUser','onBehalfOf','user','issue'}
        if not required<=comment.keys():raise ValueError('incomplete native comment')
        user=comment['user'];issue=comment['issue']
        if (type(user) is not dict or set(user)!={'id','app'} or type(issue) is not dict or
                type(issue.get('team')) is not dict or type(issue.get('project')) is not dict):
            raise ValueError('native comment attribution unavailable')
        def actor(value):
            if value is None:return None
            if type(value) is not dict or not value:raise ValueError('malformed native actor')
            return True
        normalized=dict(id=comment['id'],author_id=user['id'],author_is_app=user['app'],issue_id=issue.get('id'),
            team_id=issue['team'].get('id'),project_id=issue['project'].get('id'),body=comment['body'],
            created_at=comment['createdAt'],edited_at=comment['editedAt'],archived_at=comment['archivedAt'],
            bot_actor=actor(comment['botActor']),external_user=actor(comment['externalUser']),
            on_behalf_of=actor(comment['onBehalfOf']))
        return dict(viewer_id=self.viewer_id,organization_id=self.organization_id,comment=normalized)
