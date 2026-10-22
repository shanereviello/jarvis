# Stopped-worker finish reports and journal integration

Current installation and acceptance status: see [phase closeout](workflow-phase-closeout.md) and the [operator runbook](workflow-operator-runbook.md). The active release is `workflow-b51bcece0851`; finish/native observation, independent validation, managed draft publication and journal reads have been exercised. Descriptions of source slices and their original pending gates below are historical development context, not the current installation status. Closeout publication corrections still await their own release.

## Component design and historical delivery notes

This source slice connects protected managed launch receipts, stopped-worker result
custody and the workflow journal. It adds `finish-capture` and `finish-record` to the
operator interface. The currently installed immutable workflow release is unchanged;
these commands require a later reviewed package and isolated host acceptance before
production installation. No paid task or native lifecycle mutation is needed to test
this slice.

## Capture and record separately

`finish-capture --state CONTROL --authorization-id ID --destination ABSENT_CUSTODY`
requires the protected installed operator and a configured managed approval, matching
consumption/launch/result records and host-stop verification. It checks that the fixed
service slot is absent and UID996 idle both before and after reading worker bytes.
These are stop observations, not a distributed lock against unrelated root operators;
serialize launch/capture administration.

The capture reads bounded regular UID996-owned evidence through the existing guarded
worker-file reader. It checks native task/run context, exact assigned checkout root,
root-staged request and host/native/validation consistency. Exported results must bind
the reviewed request, repository/baseline, native task/run, workspace and all captured
artifact sizes/digests. Successful reports require an export. The custody directory
is fresh and0700; raw reports/exports remain private, with an exclusive hash manifest.
An existing/partial destination is never adopted, deleted or overwritten.

`finish-record --custody PROTECTED_CUSTODY` re-reads protected captured members and
checks their hashes and associations. It repairs missing protected capture/approval/
consumption journal facts, then records artifact, validation (when available) and
terminal/uncertain result facts. Stable event IDs make identical replay idempotent.
A write failure may leave a prefix of facts; repeating **recording**, not execution or
capture, repairs that prefix. Conflicting evidence for the same authorization refuses;
a later change of interpretation requires an explicit correction design, not silent
replacement. This slice does not automatically supersede an earlier uncertain capture.

A currently revoked configuration does not erase or prevent recording historical
captured work. No new execution authority is inferred. Recording reads protected
custody only; it never reads the mutable worker tree, retries a task, starts/stops a
service, changes native task state, fetches a credential, commits/pushes or calls GitHub.

## What the facts mean

Native runner reports are **imported claims**. Hash binding and root capture preserve
origin/consistency but do not independently authenticate everything a worker could
write. The source does not directly query the native board or rerun validation as a
trusted postprocessor. A self-reported result is not upgraded to observed or human
accepted success. The journal already labels such terminal states
`terminal_claim_recorded`, preserving their provenance.

A stopped native attempt with coherent completion and passed validation can record
an imported succeeded terminal claim. Coherent native/validation failures record
failed claims. Missing wait/terminal identity or an unverified worker stop remains
uncertain, with no terminal event. Missing/contradictory required fields refuse rather
than inventing a result. Host service return alone still never establishes success.
Early worker setup failure without a returned host result remains outside this slice.

The journal retains an operator-only capture-manifest artifact. Full private bytes
remain in custody; Jarvis sees only allowed structured facts/provenance after explicit
snapshot publication. No raw paths, report free text, logs or private artifact payloads
are published. Publication, PR opening, merge, deployment and release remain separate
facts and separate authority. The outbox still queues indexing; no delivery is added.

## Validation and following work

Source tests use real disposable Git repositories, launch receipt shapes and SQLite
journals, with explicit fixture-only ownership/service adapters. They cover successful,
failed and uncertain reports, task/run/path/boolean/stop mismatch refusal, export and
custody tampering, slot appearance, unchanged worker/control records, journal failure
and idempotent repair, configuration revocation and projection privacy. They do not
prove production root/UID996 boundaries; later packaging must include the required
custody modules and repeat model-free installed acceptance.

Next connect independently verified post-validation custody to review-commit/handoff
and exact branch/draft-PR receipts, preserving operator Git identity and keeping
GitHub credentials outside the worker. A trusted independent native-result observer,
full cancellation/recovery, installation and a separately approved real task remain
explicit follow-up work. See the [roadmap](workflow-roadmap.md).
