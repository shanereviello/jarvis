# Workflow managed acceptance

This walkthrough describes the installed Jarvis coding workflow from an operator
acceptance perspective. It summarizes the custody and review steps around one
coding run without claiming that any specific run has already passed.

Managed acceptance is narrower than task success. Mechanical checks can prove
that a bounded step completed as designed, while task success still depends on
the worker's actual changes, the human review outcome, and any later decisions.
Likewise, some records are direct observations by trusted local tooling and
others are imported reports from a worker or operator; treat them differently.

## 1. Proposal arrives from Hermes

Hermes prepares a proposal that identifies the admitted repository, allowed
paths, validation command, timeouts, and task metadata. The proposal is not an
execution grant: it must keep both `execution_authorized` and
`publication_authorized` false. Its digest becomes the immutable submission id
used throughout the run.

At this stage the proposal is a mutable request waiting for trusted capture.
Nothing in the worker payload, prompt text, or model output can authorize code
execution, publication, merge, deployment, or later paid activity by itself.

## 2. Protected capture and operator review

A trusted capture step verifies that the proposal digest matches its contents,
that repository admission and allowed paths still match policy, that the named
validation command is admitted, and that the canonical baseline repository is
clean. It then snapshots the reviewed request together with the exact baseline
commit, profile/config digests, and assigned review branch into root-controlled
state.

This capture converts a mutable Hermes proposal into a protected review record.
Operators review the protected snapshot, not the original mutable proposal.
That review establishes what was actually approved: repository, scope, baseline,
branch, limits, and validation command.

## 3. Explicit one-use execution approval

Execution needs a separate operator action that writes a durable one-use
approval for the captured review. The approval is consumed by exactly one
worker launch. Replay is refused after use, and a busy slot preserves an
unconsumed approval rather than silently spending it elsewhere.

This approval authorizes only the reviewed execution attempt. It does not imply
that the task will succeed, that validation will pass, that publication is
allowed, or that any future paid run may begin. Any later run needs its own
fresh approval.

## 4. Worker run and finish capture

The approved worker runs inside the admitted task contract and produces task
artifacts such as the export bundle, finish result, and bounded execution
records. When the worker finishes, trusted finish capture records what the
worker reported together with the protected handoff identities for that exact
submission, branch, and export.

Finish capture is evidence collection, not a declaration of success. Worker-
reported fields such as task outcome, validation outcome, push status, or PR
status remain reported claims until a trusted step independently verifies the
parts it is designed to verify. The journal should preserve that distinction
instead of inferring extra success facts.

## 5. Independent whitespace validation

The installed workflow requires an independent post-worker validation gate.
For this task contract, the required validation is separate whitespace checking
for the reviewed export, rather than trusting the worker's own statement about
validation. A successful validation release proves that the protected verifier
ran the admitted command against the exact reviewed handoff and recorded the
result durably.

This is a mechanical validation gate only. It can show that the admitted check
passed or failed for the exact captured export, but it does not prove that the
change solves the task, that the diff is desirable, or that all worker claims
are true.

## 6. Human diff review

After finish capture and independent validation, a human reviews the actual diff
on the assigned review branch or reconstructed review checkout. The reviewer is
checking the substantive change: scope, correctness, omissions, policy fit,
and whether the observed edits match the task request.

This human review is where task success is decided in practice. Passing the
mechanical validation gate does not replace human judgment, and a good-looking
diff does not retroactively turn an unverified worker claim into an observed
fact.

## 7. Draft PR publication

If publication is authorized for the reviewed handoff, source preparation
reconstructs the exact review commit from the protected baseline plus admitted
changes, then a named operator can push that commit to the assigned review
branch and open or update a draft PR. Protected receipt capture records the
bounded operator transport outcome and any normalized draft PR report.

Draft PR publication is still not merge. A recorded push or draft PR is an
operator report with protected provenance, not proof of human acceptance,
production installation, or deployment. Merge remains a separate explicit human
decision.

## 8. Sanitized journal and history tracking

The workflow stores root-private operational detail separately from the
sanitized journal/history presented to Jarvis and other readers. Sanitized
records keep stable identities, event kinds, outcomes, and limited provenance
without exposing raw credentials, private paths, mutable receipts, or free-text
runtime logs.

Journal entries should distinguish:

- observed local facts, such as a protected capture succeeding or a trusted
  validation command exiting with a specific code
- imported reports, such as a worker-declared task result or operator-reported
  draft PR state
- non-inference boundaries, such as "release status not inferred" when no
  trusted step has established merge or deployment

That separation lets later readers understand what the system actually observed
versus what another actor reported.

## 9. What acceptance does not authorize

Managed acceptance of one coding run does not by itself authorize:

- merge of the review branch or draft PR
- deployment, installation, service activation, or release
- additional paid coding runs or retries
- treating mechanical validation as proof of task success
- treating worker or operator reports as independently observed facts unless a
  trusted verifier recorded them as such

Each of those actions requires its own explicit approval path.
