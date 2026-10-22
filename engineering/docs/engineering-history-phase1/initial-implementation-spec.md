# Initial implementation specification

Status: detailed design under the operator-accepted D1 separate-service direction.
No proposed account, path, socket or schema exists in production because of this file.
These choices define an initial implementation baseline, not deployment authorization.

## 1. Local topology and scope

Start with one service process and one service-owned SQLite database on this server.
The process exposes a local Unix-domain interface only after reviewed installation.
A CLI/library can exercise the same application operations against caller-owned
fixture stores before a daemon exists. Use a new dedicated unprivileged OS account,
not UID996/997, root, Hermes or the interactive user's account.

Proposed installation layout, to verify for collisions in the installation slice:

| Resource | Proposed location/role |
| --- | --- |
| Immutable code/templates | `/opt/rras-engineering/releases/history-<payload-id>`; protected release, no secrets. |
| Service data | `/var/lib/rras-engineering-history`; dedicated service owner0700. |
| Engineering database | `history.sqlite3` inside that root; service owner0600. |
| Runtime socket | `/run/rras-engineering-history/service.sock`; explicit peer allowlist, no default network listener. |
| Service configuration | `/etc/rras-engineering-history`; protected configuration with approved repository/client policies. |
| Optional local client spool | User-owned0700 outside repositories; bounded files0600; no raw transcript capture. |

The exact account name/UID, socket group and runtime directory permissions must be
checked against actual host identities before installation. Do not chmod existing
root journal/control directories or grant Docker/sudo/GitHub/provider credentials.
No direct database mount into Hermes, browser or worker. No Git document mirror or
activity-ledger activation in this first implementation.

## 2. Authority and registration

Engineering history enrollment is distinct from managed repository admission.
A caller may propose a record for an unknown repository but may not enable execution
or select an arbitrary host path for a privileged collector. A configured registry
maps stable repository IDs to permitted canonical/worktree roots and read policies.
Repository IDs are resolved server-side; no arbitrary path/URL fetching on intake.

Unix peer credentials authenticate the OS caller, followed by configured per-operation
and repository grants. Deny worker UIDs996/997 by default, even when socket filesystem
permissions would allow a connection. UID1000 agent submissions are user-account
reports, not proof the human personally accepted a document. No JSON field may
upgrade a caller to exporter, administrator or authenticated human decider.

Only a deliberately installed bounded exporter using the root role may submit
operational source receipts. That role cannot request paid execution through the
history service. The service does not read root-private files to validate requests;
the exporter selects and validates them before sending an allowlisted representation.
Export attribution means trusted transport/source custody, not proof of every fact
inside an imported GitHub/worker report. Preserve its original provenance.

## 3. Versioned envelope and identity rules

Introduce a separate `engineering-history.v1` contract namespace. Do not add fields
or kinds to `workflow-v1` or change how old approval hashes are computed.

The proposed submission envelope contains:

| Field | Meaning |
| --- | --- |
| `contract` | Exact engineering contract version. |
| `operation` | One admitted operation, not a command/executable name. |
| `client_event_key` | Bounded stable per-caller key for retries. |
| `expected_head` | Exact prior revision digest for mutable-intent changes, otherwise an explicit null when creation is intended. |
| `source` | Origin namespace/source identifier if actually available; claimed provenance scope. |
| `occurred_at` | Known UTC source time or null; never substitute ingestion time without labeling it. |
| `body` | Strict operation-specific record, bounded and without unknown fields. |

The server adds authenticated principal, received/recorded UTC time, payload digest,
resulting stream head and durable receipt ID. A receipt is returned only after
commit. Store the exact canonical submission and server envelope separately so
server time/identity does not change the client's deduplication digest.

Use the existing compact sorted UTF-8 JSON plus newline convention for compatibility
where reused, reject duplicate keys/NaN/NUL, and publish exact encoding test vectors.
Dates are validated, unknown values explicit, object IDs/digests have fixed syntax.
Proposed initial bounds:128KiB submission,256KiB rendered Markdown,128 file references,
32 evidence references per checkpoint,100 results/page. Freeze all limits in schema/
configuration with clear refusal errors; do not silently truncate evidence/documents.
Any increase requires validation and explicit supported capacity documentation.

Preserve wrk IDs on explicitly imported existing work using a verified mapping;
collision with different repository/origin refuses. New work can use the same UUID
style without pretending v1 validity. Scope revisions are sequential and immutable;
checkpoints/doc versions can be added without changing task scope. One repository
per work item; cross-repository initiative links group separate items. Session IDs
are source-namespace scoped and may be unavailable. Attaching a resumed/forked
session requires explicit work/revision context, not an inferred directory match.

## 4. Persistence and idempotency

Initial tables conceptually separate:

- Immutable submissions/server receipts and work/document/event revisions.
- Immutable content bytes by SHA256 (including structured content and exact Markdown).
- Session/evidence/relationship associations.
- Append-only policy/visibility changes and a derived current-access projection.
- Durable delivery/import checkpoints and outbox entries.

Persist small document/content bytes in SQLite initially, in the same transaction as
metadata and receipt. Use bounded SQLite transactions with foreign keys and explicit
schema versioning; immutable-record updates/deletes are refused. No filesystem object
store is necessary for the first bounded content type. Large binary/log payloads are
outside scope; retain safe external evidence identifiers rather than ingesting them.

The unique dedupe identity is (authenticated principal, operation, client_event_key).
Same key and canonical payload -> original receipt, including original timestamps.
Same key with different bytes -> conflict, never overwrite. Concurrent scope updates
with the same expected head cannot both succeed. Distinct checkpoints against one
revision may append in server sequence; event order is not occurrence-time order.
A process loss after commit/before response is recovered by retrying the same
idempotent intake key, never repeating a coding/merge/deployment action.

Search, HTML/Markdown browsing and generation manifests are derived from committed
data and authorized views. They can be rebuilt; committed approved Markdown bytes
cannot be silently regenerated with a new renderer. Intake/outbox failure has no
permission to repeat managed execution or mutate operational journal state.

## 5. Initial operation surface

CLI names below are proposed, not installed commands:

| Operation | Initial semantics |
| --- | --- |
| `history work create/revise` | Create or propose a revision with expected-head comparison; no admission/approval effects. |
| `history session attach` | Associate exact client session (or explicit unavailable ID) with selected work/revision. |
| `history checkpoint append` | Curated progress/handoff content with evidence attribution; private draft by default. |
| `history document render/show` | Render template-bound canonical content, return/store exact bytes and external digest manifest. |
| `history outcome record` | Completion/partial/failure summary; no automatic human acceptance, merge or deployment inference. |
| `history publication request` | Ask to share an exact narrative version with an audience; request alone does not publish. |
| `history work list/show` | Authorized bounded private/operator views with provenance and delivery state. |
| `history export/import` | Explicit bounded retrospective files with source/unknown-time labels and no arbitrary fetch. |

The initial fixture CLI runs as its caller against a caller-owned temporary store;
it must not impersonate service/root roles or claim socket authentication. The
installed daemon later replaces that fixture transport with authenticated identity.
No low-privilege CLI can write the existing root operational database.

## 6. Managed capture and standard documents

At first, deterministic renderer/library tests are isolated from live approval
controls. Later, a new versioned protected adapter fetches or receives exact proposed
content, validates/reconstructs the machine-enforced core, freezes the review document,
and returns a companion manifest/envelope. The root adapter does not trust unprivileged
content to supply verified baseline, profile hashes or execution limits.

Capture operation UUID may appear in Markdown. Its own final document hash does not.
The companion manifest binds content/template/renderer/Markdown digests; the approval
envelope binds that manifest plus the existing protected review/capture digest and
exact action. Hash dependencies are acyclic. Changing content/baseline/config/template
invalidates the applicable envelope; a new semantic revision/capture is required.

Interactive recording uses the same document sections but can have unknown/advisory
scope until real admission is performed. It neither creates nor consumes a managed
one-use approval. Scope and result acceptance are distinct recorded decisions; actor
claims from a model remain claims. Web-authenticated decisions arrive only after D2
and the separate action gateway implementation are approved and accepted.

## 7. Export, visibility and consistency

Keep operational and engineering streams separate and link them by work/revision,
source namespace/event ID, source event digest and capture/attempt references.
Never splice an engineering checkpoint into an existing operational event chain.
Exporter/importer deduplicate by source identity+digest and retain origin/ingestion
time/provenance. Same identity with changed bytes refuses pending investigation.

The present sanitized root projection lacks narrative/source references. A future
versioned exporter allowlist must explicitly select new receipt/content fields; do
not parse the private database from the history service, mount it into a client, or
scrape exception logs. Export lag and unavailable evidence are visible to readers.

Operator-private is the default for free text. Shared narrative publication requires
a trusted decision/policy for an exact version and audience. A model-set visibility
string is only a request. Search filtering happens before snippets/results. Sharing
withdrawal removes served content from views/indexes/caches; preserve minimal
supersession/withdrawal metadata without exposing the withdrawn text. A secret
incident may require separate removal/retention handling; immutable approval evidence
is not blanket authority to retain sensitive plaintext in every replica.

## 8. Acceptance before each boundary expands

Initial source slice: deterministic schema/hash vectors, real disposable SQLite
transactions, document rendering, private defaults, idempotent/conflicting retries,
revision concurrency, restart receipt recovery and explicit unknown provenance/time.
No network, root/worker account changes, hooks or paid tasks needed.

Daemon slice: actual peer-identity enforcement, denied UID996/997, no root DB/key
readability, bounded socket messages, service restart and pending spool delivery.
Root exporter/capture slice: isolated root/UID/systemd fixtures, no authority gained
by text fields, no consumed approval replay, exact document binding and source-byte
mismatch refusal. Existing records/reader behavior survive versioned rollout.

Before production data retention: isolated backup/restore of SQLite content+metadata,
manifest/reference consistency, policy/grant recovery and action execution disabled.
Select off-host target/retention and recovery objectives with the operator; exact
restoration of a history service must never replay an operational action.
Web/hook acceptance remains separately specified in the backlog. Existing production
workflow stays in service while these additive boundaries are tested and reviewed.
