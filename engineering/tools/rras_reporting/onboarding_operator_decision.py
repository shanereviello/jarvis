"""Compose protected decision recording and immutable review binding.

If binding fails after designation, the recorded decision remains retained and
admission must fail closed until the same operation is reconciled. This
coordinator must be hosted only by the protected operator process.
"""


class Coordinator:
    def __init__(self,recorder,reviews):
        self.recorder,self.reviews=recorder,reviews

    def approve(self,evidence):
        if type(evidence) is not dict or set(evidence)!={'comment_id','review_id'}:
            raise ValueError('exact decision evidence required')
        result=self.recorder.approve(evidence)
        self.reviews.bind_decision(result['decision_receipt_sha256'],evidence['review_id'])
        return result
