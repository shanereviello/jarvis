# One-work production export preparation

PR51 defines the passive link bridge; PR52's actual isolated root/distinct-UID
acceptance passed all eight groups. This slice packages the production read-only
export and handoff. It does not import into history, run coding or install a timer.
Source merge and actual staging/export remain separately approved operations.

The stdlib-generated helper pins a minimal tool release containing only exporter,
validators, schemas and vendored dependencies. The exact export plan is separately
SHA-pinned. It names a fresh capture ID, journal label, one work/repository ID,
exact operational work-record digest, baseline and ordered relative scope. Reader
UID1000 is fixed; no plan can choose another root database or receiver account.
No real task IDs, plans, packets or private operational artifacts enter Git.

## Preflight and capture

Root `--check-only` verifies payload/plan bytes, protected tool/source paths,
private source DB custody and unused capture/handoff destinations. It does not open
the database or stage files. Execution then creates only a new protected tools
release and root-private `/var/lib/rras-history-exports/export-<capture-id>` journal.
The plan is frozen in that journal before the reader runs.

The reader is UID0 to read `/var/lib/rras-workflow/journal`, with capabilities and
supplementary groups cleared, no-new-privileges, private network and explicit
credential-free environment. All its executable/dependency/schema bytes come from
the protected pinned release. It opens the journal mode=ro/query_only, validates a
single consistent snapshot and closes the connection. Every bounded export page
is produced from those same frozen rows; it never rereads a changing source between
pages. Selected work ID/repository/baseline/scope must exactly match the plan.

Only allowlisted metadata defined by engineering-managed-export.v1 is written.
Raw source artifacts, prompts, summaries, actors, configs and approval payloads are
omitted. Artifact hashes can still be private metadata; this is operator-private,
not a Jarvis/public publication. No URL is fetched. Concurrent source writers are
not paused; this tool claims no source row writes, not global source inactivity or
a cross-store atomic transaction.

## Private handoff

The root original packets and digest manifest remain in the protected journal.
Root creates a new root-owned0700 directory beneath root-owned0711
`/var/lib/rras-history-handoffs`, writes only fixed packet names, result manifest
and approved plan as private600 files, fsyncs them and only then transfers directory
ownership to UID/GID1000. There are no root writes inside the receiver-owned
directory after that transfer. This prevents a live receiver from redirecting root
writes via mutable parent paths. Packet names/digests are rechecked before copying.

The user copy is editable by its owner and is not cryptographic proof of source
authenticity. The retained root original supports later explicit comparison. As
already designed, imported packets grant no observed/human/execution authority.
Future history intake still labels the linked claims imported and checks the exact
engineering revision, receipts, cursors and source digest references.

The result reports `history_records_written=false` and
`history_import_authorized=false`. No history service/socket call, protected
approval, coding run, GitHub action, Hermes change, credential access, service
restart or boot configuration occurs. No synthetic fixture data is imported.

Failure preserves release, capture, partial receiver state and root-private reader
stdout/stderr. No automatic retry, cleanup, source recovery or import is performed.
Existing completed/partial capture names refuse; another deliberate capture requires
a new explicit plan ID. Existing identical protected tool releases can be verified
and reused; their contents are never overwritten.

## Validation and next decision

Disposable SQLite tests exercise one snapshot for all pages, unchanged source DB,
reviewed binding refusal, exact helper validation, no import/control route and
populate-before-directory-transfer ordering. These are source tests; actual
production preflight/export still needs the separately pinned sudo procedure.

After export: review the allowlisted task packet and a curated engineering work
request with the same stable ID. Obtain explicit passive import approval, then
create the work revision and deliver linked checkpoints with exact readback and
receipt verification. Automatic lifecycle export wiring and standard protected
review-document binding are subsequent work, not delivered by this package.
