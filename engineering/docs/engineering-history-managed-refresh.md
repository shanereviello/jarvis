# Operator-driven managed history refresh

This sequence links a fresh snapshot of one operational work revision to an
existing engineering work revision. It is an explicit operator procedure, not a
scheduler, root hook or coding retry. It reuses the protected root fact exporter
and installed `rras-history-managed-sync` receiver; document export is separate.

## Prepare the export proposal without root

Select a private copy of the exact operational `work_item` record and the explicit
engineering `work.create`/`work.revise` envelope. Keep both out of Git. Their work
ID, repository, baseline and ordered allowed paths must match. Their revision
numbers are separate namespaces; the resulting plan binds the full operational
record digest rather than assuming revision numbers or titles identify the work.

Use a fresh 32-character lowercase hex capture ID for each export and the stable
operator-selected journal ID. Under the validated source Python environment:

```text
managed_export_plan_cli.py prepare --destination PRIVATE_NEW_PROPOSAL_DIRECTORY --operational-work PRIVATE_OPERATIONAL_WORK_JSON --engineering-work PRIVATE_ENGINEERING_WORK_JSON --journal-id JOURNAL_ID --capture-id FRESH_CAPTURE_ID
managed_export_plan_cli.py inspect --plan PRIVATE_NEW_PROPOSAL_DIRECTORY/plan.json
```

The destination's parent must already be private and caller-owned. The new directory
is exclusive 0700 with 0600 plan/review files. The plan digest uses the root exporter's
canonical encoding. No root data, service, Git remote, provider or task is contacted.
Local input assertions are not authenticated source records: actual protected
export must verify the selected digest exists and its baseline/scope match.

The plan contains only the exact IDs/digest, scope, baseline and fixed reader UID1000.
It excludes objective/narrative, actor/provenance claims, credentials, full configs,
artifact payloads and raw logs. A plan hash is a selection of bytes, not approval.
Review the private proposal before requesting the protected export.

## Obtain the protected snapshot

Use the reviewed, pinned root fact-export helper/procedure with the selected tools
manifest, exact plan path and plan hash. Read-only preflight precedes the separately
approved export. This source slice does not install a new root command, automatically
invoke sudo, infer export permission or change the existing protected reader.
The exporter opens the fixed operational journal read-only, validates its records,
selects the exact work digest and makes one consistent snapshot. It retains a root
original and transfers a completed private handoff to UID1000. A reused capture ID
refuses. Preserve partial evidence on failure; never repair telemetry by rerunning
coding or reusing a consumed execution grant.

## Review and deliver the handoff

The exact engineering work must already exist. For a new receiver state:

```text
rras-history-managed-sync init --state PRIVATE_SYNC_STATE --work-request PRIVATE_ENGINEERING_WORK_JSON --handoff PRIVATE_HANDOFF --socket /run/rras-engineering-history/service.sock --service-uid 995
```

For every handoff, inspect the complete snapshot and review its returned digest
before applying it:

```text
rras-history-managed-sync inspect --state PRIVATE_SYNC_STATE --handoff PRIVATE_HANDOFF
rras-history-managed-sync apply --state PRIVATE_SYNC_STATE --handoff PRIVATE_HANDOFF --capture-sha256 REVIEWED_CAPTURE_SHA256
rras-history-managed-sync status --state PRIVATE_SYNC_STATE
```

Each later full export must retain previously completed event claims and cannot
regress the cursor. Overlapping events reuse stable idempotency keys and original
receipts. A new scope/work revision requires explicit re-binding, not silent adoption.
Imported decisions and observations remain quoted source claims; this recording
never authenticates a human approval or establishes task success/deployment.

If interrupted, preserve private state, inspect pending delivery, diagnose and then
explicitly resume the same reviewed frozen capture:

```text
rras-history-managed-sync resume --state PRIVATE_SYNC_STATE --capture-sha256 REVIEWED_CAPTURE_SHA256
```

No saved receipt can still mean the server committed before its response was lost.
Pending status shows acknowledged local receipts, not proof that absent receipts
mean absent server rows. Resume reconciles rather than duplicating. Even complete
status says source freshness is not polled; a fresh root snapshot is a new operation.

## Rollout boundary

The installed receiver and protected export engine already exist. The new plan
builder is source tooling requiring its validated dependencies; it is not installed
in an immutable release by this change. A real fresh export and import each retain
explicit selection/review. The next acceptance should use an already recorded task
without a new paid worker run, checking source unchanged, prior history preserved,
new-event coverage, stable replay receipts and unchanged approval/worker state.
Automatic lifecycle delivery and curated Jarvis historical retrieval remain later.
