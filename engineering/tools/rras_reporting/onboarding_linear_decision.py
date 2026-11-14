"""Verify a narrow, explicit native Linear comment as a human decision.

The caller supplies protected readers and a reviewed proposal stored outside the
agent's authority. This verifier is one supported decision source; other direct
human conversations require their own independently verified source adapter.
"""
import hashlib
import importlib.util
from pathlib import Path
import re


def local(name):
    spec=importlib.util.spec_from_file_location('linear_decision_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class Verifier:
    def __init__(self,read_comment,read_review,verify_authorship,organization_id,viewer_id,human_ids):
        d=local('onboarding_drafts')
        if not callable(read_comment) or not callable(read_review) or not callable(verify_authorship) or type(human_ids) is not list or not human_ids:
            raise ValueError('protected native decision readers and human grant required')
        for item in [organization_id,viewer_id,*human_ids]:d.identifier(item)
        if viewer_id in human_ids or len(set(human_ids))!=len(human_ids):raise ValueError('distinct human identities required')
        self.read_comment,self.read_review,self.verify_authorship=read_comment,read_review,verify_authorship
        self.organization_id,self.viewer_id,self.humans=organization_id,viewer_id,set(human_ids)

    def verify(self,evidence):
        d=local('onboarding_drafts')
        if type(evidence) is not dict or set(evidence)!={'comment_id','review_id'}:raise ValueError('exact source and review required')
        d.identifier(evidence['comment_id']);d.identifier(evidence['review_id'])
        review=self.read_review(evidence['review_id'])
        keys={'organization_id','linear_project_id','team_id','issue_id','scope','project_id','document_id','version',
              'markdown_sha256','expected_governing_version','expected_project_head'}
        if type(review) is not dict or set(review)!=keys or review['organization_id']!=self.organization_id:
            raise ValueError('protected exact review required')
        for k in ('linear_project_id','team_id','issue_id'):d.identifier(review[k])
        if type(review['version']) is not int or review['version']<1 or not re.fullmatch('[0-9a-f]{64}',str(review['markdown_sha256'])):
            raise ValueError('exact reviewed version and digest required')
        response=self.read_comment(evidence['comment_id'])
        if type(response) is not dict or set(response)!={'viewer_id','organization_id','comment'} or response['viewer_id']!=self.viewer_id or response['organization_id']!=self.organization_id:
            raise ValueError('native reader identity differs')
        comment=response['comment']
        fields={'id','author_id','author_is_app','issue_id','team_id','project_id','body','created_at',
                'edited_at','bot_actor','external_user','on_behalf_of','archived_at'}
        if type(comment) is not dict or set(comment)!=fields or comment['id']!=evidence['comment_id']:
            raise ValueError('exact native comment required')
        if (comment['author_id'] not in self.humans or comment['author_is_app'] is not False or
                comment['issue_id']!=review['issue_id'] or comment['team_id']!=review['team_id'] or
                comment['project_id']!=review['linear_project_id'] or comment['bot_actor'] is not None or
                comment['external_user'] is not None or comment['on_behalf_of'] is not None or comment['archived_at'] is not None):
            raise ValueError('human or project attribution differs')
        if (type(comment['created_at']) is not str or not comment['created_at'] or
                comment['edited_at'] is not None):
            raise ValueError('edited or unverifiable decision refused')
        expected=f"I approve architecture version {review['version']} sha256 {review['markdown_sha256']}"
        if type(comment['body']) is not str or comment['body'].strip()!=expected:
            raise ValueError('explicit exact-version approval required')
        # A missing on-behalf-of actor can mean inaccessible attribution and
        # user-authorized integrations may act as users. Native user fields
        # alone cannot establish a direct human decision.
        if self.verify_authorship(comment,review) is not True:
            raise ValueError('independent direct human authorship required')
        value={k:review[k] for k in ('organization_id','linear_project_id','scope','project_id','document_id','version',
                'markdown_sha256','expected_governing_version','expected_project_head')}
        value.update(human_actor_id=comment['author_id'],source_id=comment['id'],source_namespace='linear_comment',
                     source_sha256=hashlib.sha256(comment['body'].encode('utf-8')).hexdigest(),decision_text=comment['body'])
        return value
