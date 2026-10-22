# Read-only native board observations

Current installation and acceptance status: see [phase closeout](workflow-phase-closeout.md) and the [operator runbook](workflow-operator-runbook.md). The active release is `workflow-a3f3c05a536a`; finish/native observation, independent validation, managed draft publication and journal reads have been exercised. Descriptions of source slices and their original pending gates below are historical development context, not the current installation status. Closeout publication corrections are installed and independently checked.

## Component design and historical delivery notes

This source slice observes stored native task/run state directly, alongside the
imported runner result from finish custody. It does not independently authenticate
worker behavior, rerun validation or establish deliverable acceptance. The current
production workflow release remains unchanged; installation and host acceptance are
separate decisions.

## Capture

`native-observe --finish-custody PROTECTED_FINISH --destination ABSENT_DIRECTORY`
requires root-owned installed code, protected managed finish custody and a captured
native context. The only board location is the approved launch work directory's
`home/kanban/kanban.db`. The observer pins the existing native-10 `kanban_db.py` source
by digest; it does not import that module, initialize/migrate a board or invoke native
show/complete/recovery operations.

The fixed service slot must be absent and UID996 idle before/after worker-file reads.
These are observations, not a global lock over unrelated root operators; serialize
launch and observation administration. Bounded regular worker files use the existing
UID996/ancestor guards. Any nonempty WAL, rollback journal or shared-memory sidecar
refuses: copying only the main file must not silently ignore pending data. Missing or
incomplete sidecar handling is not a checkpoint/recovery implementation. Source
files and sidecars are never opened by SQLite or modified.

The raw board bytes are copied once into fresh root-private custody. The captured
copy is opened with SQLite `mode=ro&immutable=1`, connection query-only/trusted-schema
off, attached-database and value-size limits, an instruction budget and an integrity
check. Only ordinary tables and fixed mechanical columns are queried; no task body,
result prose, log, metadata, plugin or worker-selected SQL is executed or exported.
The one-task/one-run expectation follows the current fresh per-execution board and
zero-retry launcher. Extra attempts/tasks, mismatched profile/workspace/IDs, unknown
states and invalid timestamps refuse rather than adopting new native work.

A complete stored state requires the exact done task/run, completed outcome, coherent
start/completion/end times and cleared task/run owner/claim fields. Closed failures
and incomplete ownership remain distinct. The observer compares this state with the
captured wait report. Mismatch/incomplete observations are retained as uncertain,
without changing either native state or the prior imported result. Corrupt/unsupported
snapshots preserve a private partial capture for inspection, with no completed receipt.

## Record and replay

`native-record --finish-custody PROTECTED_FINISH --observation PROTECTED_OBSERVATION`
checks root-protected snapshot bytes, source pin, finish/task/authorization association
and recomputed facts. It repairs missing finish journal records and adds an observed
`artifact.recorded` fact. It does **not** write an observed `attempt.finished` success
or replace the imported terminal claim. Repeating recording repairs a missing write
without another worker/board read or task execution. Conflicting observations for the
same authorization refuse; refreshing/superseding observations needs an explicit
correction interface rather than silent replacement.

Raw board bytes stay only in private observation custody. A bounded operator-only
journal artifact stores selected mechanical facts and snapshot/source digests. Jarvis
gets only allowed structured event/provenance fields after explicit snapshot
publication; raw database contents and source paths are not shared.

## Meaning and validation

`observed` means the trusted observer directly read those snapshot contents. The
native board is worker-owned; a worker able to fabricate its database could fabricate
those contents too. This channel checks agreement with the separately captured
report, not independent authenticity of execution. It grants no publication, merge,
deploy, paid-task retry or validation authority. Independent post-validation execution,
authenticated draft-PR creation, dependency packaging, root/UID model-free acceptance
and a later separately approved real task remain follow-up work.

Source tests use disposable SQLite boards and actual workflow journals with explicit
ownership/slot adapters. They cover completion, disagreement, stale ownership,
task/run/profile/path/time mismatch, extra attempts, view impersonation, corrupt
capture retention, WAL refusal, active-slot refusal, changed source/snapshot, replay
and projection privacy. An optional local check extracts the pinned native schema as
an AST string (without importing native code), builds a disposable board and verifies
compatibility. No live worker board, provider key, service or native lifecycle is used.
