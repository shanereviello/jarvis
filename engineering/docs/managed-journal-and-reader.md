# Managed journal events and read-only history transport

This source slice connects protected operator receipts to the journal and adds a
separate projection-only MCP server. It does not install either component, change
Hermes configuration, activate the ledger or authorize a coding task.

## Managed recording

Add an absolute `journal` directory to the protected operator configuration. Initialize
the root-owned0700 store deliberately through the reviewed journal interface first;
normal capture/approval/launch never creates or replaces it. Configuration reads check
its protected path and database permissions. Capture binds the journal location and
registration snapshot into the review, along with the existing code/schema/configuration
hashes. Removing/changing that setting invalidates approval. Omission is retained only
for compatibility with the previous source-only interface; production packaging must
require the journal for the new managed workflow. Legacy Hermes receipt launch remains
separate and does not gain automatic journal coverage.

Managed events record what the protected operator actually observes:

- Capture: a protected review was saved; no execution authorization.
- Approval: an explicit one-use authorization receipt exists.
- Consumption: authorization was consumed; service/model execution is uncertain.
- Staging: protected launch inputs exist; service acceptance remains uncertain.
- Service return: the protected result records service exit/host-stop facts; coding
  success, independent validation and deliverable acceptance are not inferred.

Consumption/staging/return use uncertain recovery facts rather than claiming that a
worker started or a task finished. An immutable attempt links exact registration,
work revision and authorization. It remains unfinished until a separately validated
native result/finish adapter supplies an appropriate terminal fact. That later
finish/custody/publication slice remains deferred on the roadmap.

Stable event/attempt identities make receipt replay idempotent. The journal assigns
event sequence/previous hash and attempt number inside the same SQLite write transaction
as the records/artifacts/outbox. Two cooperating writers cannot allocate the same next
sequence. Conflicting replay is refused rather than replacing recorded evidence.
Service-result artifacts contain only service exit and host-stop booleans/integers;
stdout, credentials, private session configuration and arbitrary worker files are not
imported by this adapter. Provenance records observation of protected control receipts,
not independent observation of every action those receipts describe. Receipt
reconciliation uses the time of recording, not an invented original action time.

## Ordering and failures

Review and approval receipt files are written before their journal facts. The launcher
repairs missing capture/approval facts before consumption and refuses to proceed if
those writes fail. After exclusive consumption it must durably record consumption,
then stage inputs and record staging, before contacting systemd. Journal failure at
any of these boundaries prevents service contact; a consumed authorization stays
consumed even when recording fails. Receipt writes and consumption now fsync their
parent directories as well as file bytes before later side effects.

Service return is first saved in a protected result receipt, then journaled. An error
at that final write does not authorize another execution. A lost client leaves the
attempt uncertain and all existing fences/evidence intact. SQLite and receipt files
are separate stores, so interruption can leave one ahead of the other; reconciliation
is explicit instead of pretending there is a distributed transaction.

```sh
python /protected/operator_control.py reconcile \
  --state /protected/control --authorization-id EXACT_UUID32
```

This root-only command validates protected receipt associations and idempotently fills
missing journal facts. It does not require the old live configuration/baseline to still
be admitted, since historical evidence must remain recoverable after revocation. It
uses the protected review's original journal binding. It never calls systemd, probes/
stops/adopts a worker, changes native lifecycle, clears a consumption marker or retries
execution. An incomplete/corrupt receipt chain is refused for operator inspection.
If capture or approval returns an error after writing its receipt, inspect root-private
records; do not create another approval merely to recover an output ID. Capture can
be replayed against unchanged inputs; an existing authorization is reconciled by its ID.

## Projection-only MCP

`workflow_read_stdio.py --directory /read-only/projections` exposes exactly:

- `workflow_pages(offset=0, limit=100)`: available repository/work identities, modes,
  revisions and page cursors, explicitly marked as snapshot data.
- `workflow_history(work_item_id, after=0)`: one already exported sanitized page.

It never opens the private database or artifact blobs and has no write/approval/
execution/publication tools. Inherited credentials are removed before serving. The
fixed directory contains an operator-published index plus the sanitized pages produced
by `workflow_journal.py publish-jarvis`. The index shape is:

```json
{
  "schema_version": 1,
  "pages": [
    {
      "work_item_id": "wrk_00000000000000000000000000000001",
      "after": 0,
      "file": "work-page-0.json"
    }
  ]
}
```

At most256 entries are admitted. File names must be simple JSON basenames; paths,
symlinks, duplicate cursors, mismatched work IDs, malformed projections and missing
pages are refused. Query callers supply only a work ID/cursor, never a file path.
Each read revalidates the index and strict projection allowlist. Pages expose no
objectives, event free text, raw references/logs, session contents, argv, private
artifact references or bytes. Sharing identifiers must still be chosen deliberately;
this is a structured projection, not a general secret-redaction engine.

Publish complete versioned page sets before atomically replacing their index or
exposing a new generation. No automatic index builder, refresh timer or mount cutover
is installed by this slice. A published page can be stale; absence is not evidence
that no work exists. Index pages are bounded snapshots, not a coherent live database
query across generations. Native outcome/validation/publication facts not yet imported
remain unknown. The operator retains full private journal views separately.

The server follows the existing locally inspected MCP1/2 transport branches. Actual
MCP1 stdio list/read/refusal and legacy preparation tests pass in the development
environment. Sandbox asyncio thread wakeups prevented both unchanged and new stdio
handshakes there; these model-free tests passed outside the sandbox. This does not
establish MCP2 compatibility inside the actual Hermes container, read-only mount
permissions or UID996/systemd boundaries. Those are required acceptance checks before
installing a reviewed release and adding the read-only MCP entry. Keep the database,
authority/control directories and provider/GitHub credentials unmounted in this reader.
