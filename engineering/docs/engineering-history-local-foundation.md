# Local engineering-history foundation

This is the first implementation of the accepted separate-service design: strict
versioned records, a caller-owned SQLite library/CLI and deterministic private draft
documents. It is **source only**, not an installed daemon, network endpoint, hook,
Jarvis narrative reader, or protected approval replacement. The existing root journal
and operational workflow are unchanged. No sudo or provider call is needed to test it.

## Implemented boundary

- [Engineering contract](../contracts/engineering-history-v1.schema.json) is distinct
  from workflow-v1 and rejects unknown fields, claimed observed provenance and authority
  flags. Work intent includes rationale/criteria, exact relative paths and a known or
  explicitly unknown baseline. These are passive records, not repository enrollment.
- `tools/rras_history/contract.py` defines UTF-8 compact sorted JSON plus newline,
  SHA256, strict calendar timestamps when supplied, explicit unknown occurrence time,
  duplicate-key/non-finite/NUL/nesting/size refusal and operation-specific validation.
- `store.py` transactionally records immutable submissions, caller-attributed receipts,
  document bytes/manifests and pending index references. Same principal/operation/key
  plus same payload returns the original receipt; changed payload conflicts. Scope
  revisions use expected-head comparison, including concurrent writers. Repository
  identity cannot change across a work's revisions. Stale session/checkpoint/document
  submissions refuse instead of quietly attaching to a newer revision.
- `documents.py` renders the three fixed-section templates and stores exact Markdown
  bytes and content/template/renderer hashes. Caller fields cannot override injected
  work/document/repository identity. Document updates append sequential versions with
  the prior Markdown hash. Retrieval does not re-render old bytes with current code.
- `cli.py` exposes explicit `init`, `submit`, `history`, `document` and `outbox`
  operations. There is no shell/recipe executor, file/URL resolver, publication,
  approval, merge, deployment or authenticated service-role endpoint.

Every receipt identifies `transport=local_caller_store`, the actual writer UID,
`visibility=operator_private` and `authority_granted=false`. `human_reported` means a
caller-provided report, not an authenticated human click. Completion is only a
reported outcome. The local library refuses root/elevated execution; it requires a
caller-owned canonical0700 store and regular0600 database, refuses symlinks/hardlinks
and unsafe sidecars, and never opens the root workflow database.

The current caller owns the store and can ultimately replace its files or alter its
schema. Triggers/digests detect accidental/conflicting API/SQL changes, not malicious
owner rewriting. This is not accepted service containment, peer authentication,
cryptographic attestation or a universal activity monitor. Those require the later
reviewed daemon/export/client slices.

## Disposable demonstration

Use Python with `engineering/requirements-contracts.txt` already available. Paths
below are placeholders; use a fresh private directory outside any live service data.

```sh
mkdir -m 700 /absolute/private/history-fixture
python engineering/tools/rras_history/cli.py init --store /absolute/private/history-fixture
python engineering/tools/rras_history/cli.py submit --store /absolute/private/history-fixture \
  --request engineering/contracts/examples/history-local-work.json
python engineering/tools/rras_history/cli.py submit --store /absolute/private/history-fixture \
  --request engineering/contracts/examples/history-local-checkpoint.json
python engineering/tools/rras_history/cli.py submit --store /absolute/private/history-fixture \
  --request engineering/contracts/examples/history-local-document.json
python engineering/tools/rras_history/cli.py history --store /absolute/private/history-fixture
python engineering/tools/rras_history/cli.py document --store /absolute/private/history-fixture \
  --document-id doc_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
python engineering/tools/rras_history/cli.py outbox --store /absolute/private/history-fixture
```

All three inputs are synthetic examples, not actual engineering work, approvals or
admission configuration. Repeating the same submit returns the same receipt; repeating
`init` refuses. Request files must be bounded regular files, not FIFOs/symlinks. History
and Markdown output are private operator data; do not publish the raw output to Jarvis.
For actual work, choose a new wrk ID, explicit source and correct revision/content.

The request `expected_head` and non-work `work_revision_sha256` both identify SHA256
of the current canonical work body. A work revision increments `revision` and provides
the previous body digest as expected head; history preserves the full original
request (including that parent binding). Document versions bind the exact current
work digest and previous document Markdown digest, independently of work numbering.
Source occurrence timestamps are independent of server-assigned recording order.

## Limits and deferred components

Current source bounds:128KiB submission,32 JSON nesting levels,256KiB Markdown,
10,000 records per local store,100 rows/page. Whole-history consistency reads are
simple bounded scans; production-scale/performance acceptance and optimized indexes
remain future work. Do not truncate a store to evade capacity or silently change a
contract limit. No automatic deletion, outbox delivery/acknowledgment or off-host backup
is implemented. Pending references survive reopen and do not imply external indexing.

No browser/Unix-socket daemon, repository/client policy registry, peer-credential
checks, model summary generation, automatic session association, hooks, visibility
publication, narrative search, root receipt exporter or protected document approval
binding is installed by this slice. No existing operational records are migrated.
The data contracts are new; future migrations need explicit source/version/custody
review. Initial private draft rendering is not the later root-captured review package.

## Validation

`test_engineering_history_local.py` uses real disposable SQLite/Git-free fixtures and
subprocess CLI checks: retry/conflict, concurrent scope updates, transaction rollback,
commit/response loss, reopen/outbox, immutable SQL writes, modes/symlinks, malformed/
spoofed inputs, exact template field sets, version conflicts, deterministic/stored
bytes and bounds. Existing workflow record/journal tests verify the old format stays
unchanged. These are local source checks, not daemon/UID/host integration acceptance.

Next: review this source contract/storage boundary, then explicit interactive client
operations and a separately reviewed local authenticated service. Shared narrative
publication and root receipt export retain their own implementation/privacy gates.
