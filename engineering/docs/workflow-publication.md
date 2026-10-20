# Finish custody to review publication and journal receipts

This source slice connects the finish capture to existing local commit preparation
and named-operator Git bundle handoff, then records publication reports in the same
workflow journal. It is not installed in the current immutable workflow release.
No new GitHub identity, token, SDK, remote API client or worker authority is added.

## Supported source operations

1. `publication-prepare --finish-custody DIRECTORY --policy FILE --destination ABSENT_CLONE --package ABSENT_PACKAGE --operator NAME`
   requires protected successful finish custody and a root-protected publication
   policy matching the admitted registration remote. Existing publication code
   reconstructs the scoped change from the captured export in a fresh clone,
   verifies the exact baseline and assigned review branch, creates a local review
   commit and emits the protected prepared record and source-only Git bundle.
   This makes no remote connection. The bundle includes reachable repository
   history, so repository admission must permit handing that history to the operator.
2. The named operator uses the existing `publication_handoff.py` import/review/publish
   interfaces and their existing SSH identity. Its transport verifies the prepared
   clone, attempts the non-forced assigned branch push once, verifies the remote
   branch and retains started/outcome receipts. A lost response stays unknown and
   must not be retried. No GitHub credential enters the coding worker. These existing
   operations do not create a draft PR automatically.
3. A human/operator client can open the draft PR through the existing GitHub
   connection and save the normalized response described below. This slice accepts
   that receipt; it does not implement an authenticated GitHub PR-creation client.
4. `publication-capture --finish-custody DIRECTORY --package PACKAGE --workspace OPERATOR_WORKSPACE --destination ABSENT_CUSTODY [--pr-receipt FILE]`
   checks the root-owned bundle/manifest, finish task/run/export/baseline/branch and
   admitted remote. It captures the named operator's bounded private transport
   started/outcome files and optional normalized PR receipt into new root-private
   custody. Receipt ancestors must be owned by root or the named operator and not
   group/world writable; receipt files must be private, regular, non-symlink and
   single-link. Capture is not an MCP capability and makes no remote contact.
5. `publication-record --finish-custody DIRECTORY --custody PUBLICATION_CUSTODY`
   validates captured hashes and associations, repairs missing finish journal facts,
   and records branch and optional PR reports. It never reads the mutable operator
   workspace or re-pushes. Stable identities permit recording the PR later with the
   same branch receipt, without duplicating the branch event. Partial journal writes
   can be repaired by repeating recording alone. Conflicting reports refuse.

The first prepare/capture operations require new destinations. Preserve partial
outputs rather than deleting/adopting them. Root command invocation, protected
policy/configuration and the task-assigned branch remain the authority boundary;
model-supplied dictionaries do not grant publication rights.

## Normalized draft-PR receipt

The named operator's private JSON file must contain exactly these fields:

```json
{
  "schema_version": 1,
  "repository": "OWNER/REPOSITORY",
  "head_repository": "OWNER/REPOSITORY",
  "head_branch": "codex/ASSIGNED_BRANCH",
  "head_commit": "EXACT_40_HEX_REVIEW_COMMIT",
  "base_branch": "REVIEWED_BASE_BRANCH",
  "number": 123,
  "url": "https://github.com/OWNER/REPOSITORY/pull/123",
  "draft": true,
  "merged": false,
  "state": "open"
}
```

Repository, head repository, branch, head commit, base, positive integer PR number
and URL must match the protected handoff. Fork mismatch, changed head/base, non-draft,
closed/merged PRs, boolean numbers or inconsistent URLs refuse. Current remote syntax
for PR reports is the existing `git@github.com:OWNER/REPOSITORY.git` form. Other
Git hosts/remote forms require a separately reviewed client/normalization extension.
Capture does not refresh a PR later: this is a report of its state at observation,
not a claim about its state forever.

## Claims, privacy and limits

Transport and API receipts are **imported named-operator reports**, not independently
observed GitHub state. Protected capture establishes provenance/consistency; the
operator can still supply a false report. Unknown push outcomes record an uncertain
recovery fact, never a successful branch or PR opening. Neither a push nor a draft PR
establishes human acceptance, merge, deployment or release. The journal continues to
report release status as not inferred.

Source preparation verifies captured export consistency and reconstructed commit
scope. It does not independently query the native board or rerun validation under a
new trusted verifier. It retains the existing publication policy's evidence contract;
independent native-result observation remains follow-up work.

Full operator receipts remain root-private. Journal artifacts contain bounded
operator-only identities/digests; Jarvis receives allowed event kinds, outcomes and
provenance through explicit sanitized publication, without raw paths, receipts,
remote credentials or free-text logs. Pending index outbox entries are still local.

Source tests use disposable Git repositories and real local review commits/bundles,
synthetic operator/GitHub receipts, explicit fixture ownership adapters and real
SQLite journals. Existing local bare-remote transport tests cover actual push/replay
behavior. This does not establish authenticated GitHub end-to-end or production
root/UID acceptance. Future packaging must include the finish/publication/custody
modules and repeat model-free host acceptance before installation. GUI/autopilot,
paid execution, automatic PR creation, independent native observation, final human
review/merge/deployment receipt adapters and ledger delivery remain separate work.
