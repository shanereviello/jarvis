# Durable workflow journal foundation

Current installation and acceptance status: see [phase closeout](workflow-phase-closeout.md) and the [operator runbook](workflow-operator-runbook.md). The active release is `workflow-b51bcece0851`; finish/native observation, independent validation, managed draft publication and journal reads have been exercised. Descriptions of source slices and their original pending gates below are historical development context, not the current installation status. Closeout publication corrections still await their own release.

## Component design and historical delivery notes

`workflow_journal.py` stores passive shared-contract records and local artifacts in
a private SQLite database. It queues references for future indexing in the same
transaction. It does not register a repository, authenticate a claimed actor, approve
execution, invoke a recipe, fetch a reference, contact a model or start the ledger.
This source slice is the storage/read foundation of roadmap step3, not automatic
observation of all work. The source [managed adapter](managed-journal-and-reader.md) now supplies journal
write ordering and receipt reconciliation when configured; production installation
and actual-container/host acceptance remain pending.

## Ownership and durability

The caller must deliberately create an absolute, non-symlink directory owned by its
OS UID with mode0700. `init` creates `workflow.sqlite3` exclusively with mode0600;
existing files are refused, including incomplete initialization. Inspect/preserve
an incomplete store rather than overwriting it. Later opens require the same owner,
mode and regular database file with no hard links. SQLite rollback journals stay
inside the private directory. Installation must additionally protect ancestors and
separate root writer/private storage from the Hermes/Jarvis read principal.

Writers use SQLite `BEGIN IMMEDIATE`, rollback journaling and `synchronous=FULL`.
A batch commits record bytes, immutable artifact bytes and pending outbox rows
atomically. A process crash before commit rolls back the whole batch; a committed
batch survives reopen. This relies on the local filesystem honoring SQLite locking
and fsync; it is not an off-host backup or a distributed storage guarantee.

Record SHA-256 identities and existing complete-history validation reject conflicting
identities, revision gaps, broken links, conflicting event sequences and artifact
metadata changes. SQL triggers disallow record/artifact updates and deletes. Replaying
the same records is idempotent and preserves original ingestion metadata. Corrections
append new events referencing earlier events; original evidence remains. Hashes detect
inconsistency, not malicious database-owner replacement or tail deletion without an
external head anchor. The store is not an authenticated signature service.

Local artifact bytes must accompany their references or already exist under the exact
SHA-256. Artifacts are immutable and private; missing bytes, digest mismatches, orphan
payloads and visibility changes under the same artifact ID are refused. Make a new
explicit artifact reference to reclassify sharing. No recursive import or arbitrary
file fetching occurs. Limits: 256 records per batch, 10,000 records per store, 4MiB
per artifact and 16MiB of supplied artifacts per batch. These are initial bounds,
not production scale/performance acceptance. Do not rotate/truncate a store to bypass
its limits; extend the implementation deliberately.

## Source CLI

Use an interpreter with `engineering/requirements-contracts.txt` installed. Paths
below are placeholders, not instructions to initialize production state.

```sh
python engineering/tools/rras_native/workflow_journal.py init --store /private/store
python engineering/tools/rras_native/workflow_journal.py append \
  --store /private/store --records /private/records.json \
  --artifact EXACT_SHA256=/private/explicit-artifact.txt
python engineering/tools/rras_native/workflow_journal.py import-interactive \
  --store /private/store --records /private/interactive-records.json
python engineering/tools/rras_native/workflow_journal.py status \
  --store /private/store --repository-id jarvis --offset 0 --limit 100
python engineering/tools/rras_native/workflow_journal.py history \
  --store /private/store --work-id wrk_EXACT32HEX --after 0 --limit 100
python engineering/tools/rras_native/workflow_journal.py summary \
  --store /private/store --work-id wrk_EXACT32HEX --after 0 --limit 100
python engineering/tools/rras_native/workflow_journal.py outbox \
  --store /private/store --offset 0 --limit 100
```

Record files are JSON arrays of shared-contract registrations, work revisions,
attempts and events. Existing linked records may be omitted from a later batch;
validation includes the committed history. `append` is an owner/operator ingestion
interface, never a worker/chat endpoint. Ingestion records the OS UID, UTC receipt
time and source kind separately from the record's claimed actor/provenance. Operator
entry is not independent verification of the claims inside a record.

`import-interactive` requires imported or human-reported provenance on all supplied
records and interactive work/attempts. Events must link interactive work. It accepts
the same explicit `--artifact SHA256=FILE` option. It refuses observed provenance;
importing a chat does not observe or authorize its described actions. There is no
automatic chat scraping, session discovery, external-URL fetching or reinterpretation
of conversation instructions. Imports must explicitly describe the evidence actually
available and retain unknown fields as the contracts allow.

`artifact --store ... --sha256 ... --output /private/export/file` writes exact bytes
to an absent file in a caller-owned private output directory outside the store.
Operator history can include private event summaries/references; do not publish its
raw output. Status lists work by repository and includes unfinished attempts and
terminal claims with provenance. A terminal claim is not verified deliverable success.
Corrections targeting a terminal event conservatively remove it from that status
projection until further evidence is recorded.

## Work summaries and release facts

Summary pages retain all facts and correction references rather than collapsing them
into an unqualified success state. Execution, validation, artifacts, branch publication,
PR creation, merge, deployment, verification and human decisions are separate stages.
Every fact retains observed/imported/human-reported provenance and ingestion kind.
`release_status` remains `not_inferred`: reported deployment and an unmerged branch
must never become an automatically claimed release. This is a structured, reviewable
work/release history, not generated natural-language release notes or human acceptance.
Queries return bounded pages and continuation cursors; follow them to retrieve a full
history. Concurrent commits can add new pages, so a pagination cursor is not a frozen
multi-page audit snapshot.

## Jarvis reads and privacy

A writer/operator explicitly publishes a separate, structured per-work summary page:

```sh
python engineering/tools/rras_native/workflow_journal.py publish-jarvis \
  --store /private/store --work-id wrk_EXACT32HEX \
  --output /private/projection-directory/work-page.json --after 0 --limit 100
python engineering/tools/rras_native/workflow_journal.py jarvis-read \
  --view /read-only-projection/work-page.json
```

The output parent must initially be caller-owned0700 and outside the database tree.
Publication writes a temporary file, fsyncs, atomically replaces the projection and
fsyncs its directory. Only an existing valid projection can be replaced; unrelated
files and symlinks are refused. Files are mode0440. A failed replacement preserves
the previous complete view. Production packaging must expose only these sanitized
files through a deliberate read-only mount/group arrangement; source tests do not
establish container/UID permissions. Do not mount the database directory into Hermes.

The Jarvis projection includes repository/work identity, mode/revision and bounded
event identities, outcomes, timestamps,
provenance, stages and explicitly shared artifact IDs/digests/purposes. It omits
objectives, event free text, actor/source/reference payloads, paths, argv, session
configuration, raw artifact bytes and operator-only artifact references. Visibility
labels authorize only selection into this metadata export, not access to the private
blob store. Richer human-approved shared text requires a later explicit policy; there
is no claim of automatic secret redaction. Keep repository/record IDs suitable for
sharing. `jarvis-read` validates a strict allowlist and never opens the private store.
It does not grant write, approval or execution access. Freshness is explicit: exports
are snapshots; publishing new pages is not automatic synchronization.

## Outbox and remaining integration

Every inserted record queues one private pending digest atomically. Reopen and duplicate
replay preserve those entries. No network delivery, acknowledgment/removal or ledger
schema/grant change is implemented. Future indexing must select an appropriate payload
and explicit credentials/permissions, use digest idempotency and acknowledge only a
confirmed durable external receipt. A failed index write must not launch/retry coding.
Never send the entire private store to a ledger as an indexing shortcut.

The source [managed adapter and projection-only MCP](managed-journal-and-reader.md)
now provide control-event writes/reconciliation and a reader. Before installation,
require a configured journal, publish a complete projection generation and run
actual-container plus isolated root/UID996/systemd permission acceptance. Package
code/schema/dependencies/config together.
No production ledger activation, model call or migration is required for these checks.
