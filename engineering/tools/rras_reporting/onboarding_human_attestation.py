"""Reverify a retained human decision against its protected native source.

The review lookup must be a protected operator-side binding from an immutable
history receipt to its review reference. This adapter is not an approval
source by itself and performs no history writes or policy changes.
"""


class Verifier:
    def __init__(self,lookup_review,verify_source):
        if not callable(lookup_review) or not callable(verify_source):
            raise ValueError('protected review and source readers required')
        self.lookup_review,self.verify_source=lookup_review,verify_source

    def __call__(self,record):
        if type(record) is not dict or type(record.get('submission')) is not dict or type(record.get('receipt')) is not dict:
            raise ValueError('retained decision receipt required')
        submission=record['submission'];body=submission['body'];source=body['source_reference'];context=submission['context']
        receipt=record['receipt']['request_sha256']
        if (submission['operation']!='decision.observe' or body['kind']!='architecture' or body['state']!='approved' or
                body['attribution']!='imported_source' or body['attributed_author']['role']!='human' or
                body['attributed_author']['runtime']!='linear' or source['namespace']!='linear_comment'):
            raise ValueError('exact attributable linear decision required')
        review_id=self.lookup_review(receipt)
        verified=self.verify_source({'review_id':review_id,'comment_id':source['id']})
        if (type(verified) is not dict or verified['project_id']!=context['project_id'] or
                verified['scope']!=submission['scope'] or
                verified['document_id']!=context['architecture']['document_id'] or
                verified['version']!=context['architecture']['version'] or
                verified['markdown_sha256']!=context['architecture']['markdown_sha256'] or
                verified['human_actor_id']!=body['attributed_author']['source_actor_id'] or
                verified['source_namespace']!=source['namespace'] or verified['source_id']!=source['id'] or
                verified['source_sha256']!=source['sha256'] or verified['decision_text']!=body['decision_text']):
            raise ValueError('retained decision differs from current native source')
        return True
