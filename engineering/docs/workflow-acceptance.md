# Workflow acceptance: October19,2026

PRs15–19 are merged. The new workflow remains source-only: no production operator
release/configuration, journal, history mount or MCP entry has been activated by
these checks. Acceptance is not deployment or paid-task approval.

## Actual Hermes reader

`probe_workflow_reader.py` ran as UID1000 inside the unchanged running Hermes
container using its existing Python3.13.5 and MCP2.0.0. It copied hash-checked source,
schema and synthetic projection files into a temporary directory, performed real
stdio list/read/refusal calls, and removed the fixtures. The container ID, image,
restart count and start metadata were unchanged; no live configuration was read or
changed and no coding worker/model was invoked.

Passed: exact source hashes, exactly two read tools, page listing, readback, private
field omission, invalid work identity refusal and unavailable cursor refusal.

A disposable container from the same existing image additionally ran
`probe_workflow_reader_readonly.py` with a synthetic bundle at `/acceptance`, read-only
root filesystem, UID1000, dropped capabilities, no-new-privileges, bounded resources
and network disabled. Only the fixture tree was bind-mounted, read-only. File creation
on that mount failed with EROFS; actual MCP readback and private-field omission passed.
The disposable container was removed. This tests the proposed reader mount boundary,
not a completed production mount/configuration cutover.

## Actual host/systemd acceptance

A hash-checked helper staged a separate protected acceptance release with the exact
synthetic worker from `probe_approved_launch.py`, the new source, and offline copies
of its existing schema-validation dependencies. No dependency installation or version
change occurred in native-10 or Hermes. A root-run probe used a harmless sentinel
instead of a provider key and a separate transient acceptance unit with PrivateNetwork
and restricted address families. The fake worker runs as UID996; it imports no model
client, native Hermes session or task transport.

Acceptance manifest SHA-256:
`21c2ea94539dfb08a0a5e4e9103a4f2eb2f6113f056ebf4da5564dc11c3b5eb9`.
The 165-file candidate and probe bytes match the saved success result.

Passed14 checks:

- Protected capture and durable approval recording.
- Sentinel delivery through systemd to the real UID996 fake worker.
- Slot exclusion and preservation of an unconsumed approval while busy.
- Verified host stop and one-use replay refusal.
- Idempotent journal reconciliation and configuration revocation.
- Private journal/control denial for both UID996 and UID1000.
- UID1000 read access to the sanitized projection with write denied.
- Pending outbox retention after reopen.
- Fake service success remains an unfinished task, without inferred task success.

The result was `offline_workflow_host_verified`, API calls0, real credentialsfalse,
production unit usedfalse, records9. Subsequent read-only verification found the
acceptance unit and production coding unit both not-found, no UID996 processes, and
Hermes still running at the same image/container identity with restart count0.

Fixture/evidence roots are retained under a separate acceptance release and
`/var/lib/rras-workflow-acceptance-20261019`. They are not a production deployment or
an admitted real task. Do not repurpose the fake worker release as a real launcher,
reuse its synthetic approvals, rerun its absent-only installer, clear fences or delete
evidence as an installation shortcut. Private journals, complete runtime records and
credential files are excluded from Git; only probe source and bounded validation
summaries are retained here.

## Limits and next installation gate

This acceptance establishes real container transport/read-only binds and host role/
systemd boundaries for the specific reviewed fixture source. It does not prove a
model-backed task, native finish/validation/custody/publication integration, a live
production mount, ledger delivery or full cancellation/recovery. Existing runtime
pins and previously retained evidence remain unchanged.

Next prepare one immutable production code/schema/dependency bundle from merged source,
require a protected journal setting, initialize private storage deliberately, and
prepare explicit sanitized projection generation/publication plus the read-only Hermes
entry/mount change. Review exact files, permissions, active paths, rollback and
model-free post-install verification before requesting a separate installation decision.
Source merge alone does not authorize that installation. No paid task or production
ledger activation is needed to finish the packaging/installation checks.

Production packaging and explicit snapshot publication are now prepared in the [next source slice](workflow-production-package.md). Its changed publisher still needs the inactive protected preflight and a separately reviewed final activation procedure; no production installation is implied by these acceptance results.
