# Engineering History Workspace — v0.2 implementation reconciliation

This is the final implementation design for the accepted v0.2 requirements, not
a new feature scope. It is intended as the next retained architecture version
after the original v0.1 draft and approved v0.2 design. Its eventual designation,
exact release baseline and closeout are explicit project records, not assertions
created by placing this file in Git.

The governing requirements remain
`JARVIS-PROJECTS-AND-WEB-UI-ARCHITECTURE-DRAFT-v0.2-20261106.md`, SHA-256
`23752a4bcc5591459bd5418513e7917c35ee6405d3bb3dfca19b2b9bb0ed97d4`.
The retained review and both earlier architecture files remain unchanged.

## Purpose and scope

Group bounded engineering work into a durable project under exactly one
repository or the sole initial category `jarvis-non-git`. Preserve why the project
exists, which work belongs to it, the architecture governing that work and exact
Git baselines as the effort changes and closes. The operator webpage is read-only.
Recording and source provenance remain explicit; future conversations are not
automatically scraped, classified or treated as accepted work.

The real Engineering History Workspace project belongs to Jarvis and has one
primary current-conversation work item. The operator separately approved grouping
14 older items into Engineering History Foundation and Dashboard (12) and Managed
Coding Workflow Documentation (2). Those retrospective memberships retain actual
recording times and reasons, without inventing an original project lifecycle,
governing architecture or baseline for the older work.

## Authoritative data and relationships

The existing service-owned SQLite database remains authoritative. Its unprivileged
service identity owns the database; callers use a Unix socket authenticated by
kernel peer UID. No desktop client connects directly to production SQLite.

| Collection | Immutable content and relationships |
| --- | --- |
| `submissions` / `outbox` | Original work definitions/revisions, sessions, checkpoints, reported outcomes and work documents. Existing bytes, receipts and document digests survive project/scope upgrades. |
| `project_submissions` / `project_outbox` | Project metadata/state/archive history; architecture save/designate; Git baseline record/select; membership assign/remove/designate; closeout/reopen effects. Every event binds a scope, project ID, request digest, receipt and expected head. |
| `project_metadata` | Private local snapshot key. Preserved across upgrade so historical signed view tokens remain verifiable. It is never returned through the service. |
| `scope_submissions` / `scope_outbox` | Scope kind/ID, display name, description, optional credential-free repository URL, metadata revision, previous head, change summary and submitting/source provenance. Metadata creates no permissions or execution admission. |

Project/scope records carry their own versioned contracts rather than fabricated
work records. Append-only triggers and transactional service validation preserve
history. Projections are rebuilt from authoritative events; no larger-scale
indexing/performance claim is made beyond the bounded first implementation.

Each current work membership has one project in its own scope and an explicitly
pinned architecture version, or recorded absence. Assignment/reassignment checks
the association head and affected project heads atomically. Design changes do not
rewrite work scope or silently move old work to a newer architecture. Counts use
distinct work IDs, with reported outcomes distinguished from project state and
outcomes for an earlier work revision distinguished from the current revision.

## Architecture and baselines

Each project has one logical architecture ID. Consecutive saved versions retain
exact UTF-8 Markdown, content/predecessor digests, title/change summary, project
revision, baseline/applicability state, source reference and attribution. Saving a
draft and designating a governing version are separate events. Designation history
retains exact version/digest, reason, principal and recording/source times.

Git baseline versions retain one exact commit in the project's repository,
optional observed/ref label, prior baseline digest, reason and source/verification
limits. Starting/current selection and closeout references are explicit. The
starting baseline is never overwritten; architecture/work references stay pinned.
Reported commit provenance does not independently establish object membership or
release verification. Non-Git baselines/URLs remain not applicable, without a
fabricated repository or commit.

## Explicit storage upgrades and snapshots

New stores initialize as v1. The explicit project upgrade adds project tables and
sets schema v2. The explicit scope upgrade fingerprints the existing schema,
work/project rows/outboxes and snapshot key, adds the scope tables and sets v3 in
one transaction. Both require the exact owner-reviewed fingerprint; neither
service startup nor a browser request migrates a database. Pre-commit failure
rolls back. Retain compatible runtimes and all subsequent history during recovery;
do not downgrade/restore the database to repair deployment metadata.

V3 views bind per-scope work, project and scope-metadata boundaries with a MAC.
Counts do not reveal other scopes. Valid old two-stream signed snapshots remain
usable, showing scope metadata as unrecorded because they predate the scope log.
New historical views retain the exact scope-name revision. Scope metadata updates
do not change the stable ID or grant access. JSON object order/whitespace does not
affect a token; duplicate/unknown fields, booleans, invalid bounds and altered MACs
remain rejected.

## Read-only webpage and authoring

Authorized scope -> project -> work remains the primary path. All projects, All
work and per-scope Unassigned work are retained. Friendly names include stable
IDs; other repositories retain their actual identity. A separate read-only scope
details view exposes metadata revisions and source attribution. Only configured
and granted scopes appear; recording repository metadata does not widen access.

| Project tab | Delivered reader behavior |
| --- | --- |
| Overview | Intent, scope/exclusions, owner, project state, architecture identity, governing/latest draft, baselines, current-revision outcome counts, earlier-revision outcomes and closeout summaries. |
| Work | Distinct assigned work with revision, reported outcome and exact outcome revision, design pin and last recorded activity. Existing detail remains available. |
| Architecture | Every saved version, exact hash/view/download, text diff, explicit designation history, source/principal/recording/occurrence attribution, per-version work and closeout-pinned versions. |
| Baselines | Starting/current/closeout Git selections and immutable source/commit/ref/reason history; honest not-recorded/not-applicable states. |
| History | Metadata/state/archive changes, membership and design changes, baseline events and closeout/reopen. |

Existing work Overview/Timeline/Documents/Evidence tabs and stable identity-based
URLs remain. Historical headers identify the closeout recording date and sequence.
Source times remain unknown where not recorded. Scope-filter reloads clear stale
list cards before the next result; authorization/service failures clear private
state, and sign-out retains no browser history cache fallback. Markdown/diffs and
scope text are rendered as text, with no-store/CSP/JWT protections retained.

Authoring uses the existing private operator/service interface. New
`scope_entry.py` commands provide exact scope requests and owner-only v2-to-v3
migration; project/work commands retain their durable requests, keys and receipts.
The dashboard transport never allows project/scope authoring or migration.

## Closure, recovery and acceptance

Project completion is explicitly recorded after a governing design and current
Git baseline (or recorded omission) exist. Every unresolved/current-scope work
item needs a recorded disposition. A closeout captures exact metadata, membership,
architecture, baseline, work revisions/outcomes and snapshot boundaries. Reopening
appends an event; later notes/reassignments/renames cannot retarget the old view.
Closeout dates are projected from immutable receipt times, including older events,
without rewriting those receipts. Completion is not an inferred merge, deployment
or independently authenticated acceptance claim.

Validation covers immutable v2-to-v3 migration/rollback, snapshot key preservation,
old/new snapshot compatibility, scoped metadata history/denials, credential-free
URLs, distinct/old-revision outcome counts, closeout dates and actual Unix peer
authorization. Signed API tests use canonical wire encoding. Chromium exercises
Jarvis, robot_ws, another repository, the non-Git category, scope rename/history,
all project/work tabs, exact documents/diffs, historical closeout/reopen context,
and failure/sign-out clearing. A fresh isolated privileged fixture uses dedicated
temporary identities/paths and synthetic records for migration and cross-UID HTTP
reads. Actual privileged acceptance and production receipts are recorded separately.

Release and private-input manifests are pinned for deployment. A stopped-service
procedure preserves a private pre-upgrade copy and exact records, upgrades only as
the owner, selects immutable runtimes, and verifies reader boundaries before
activation. Failures retain evidence without automatic retry or database rollback.
After activation, actual authenticated browser acceptance and the final baseline,
architecture designation, work outcome and closeout must be explicitly recorded.

## Retained limitations and deferred scope

- Exactly one scope per project, one primary project per assigned work and one
  initial non-Git category. Cross-scope project moves require a later design.
- Git-only baselines; broader document/state baseline types remain deferred.
- Browser editing, automatic chat collection, broad visual redesign, rich Markdown
  rendering and whole-history/document search remain outside this v0.2 slice.
- Separate explicit access grants and curated publication are retained. No wider
  Jarvis MCP access, operational execution approval or paid task follows from data
  recording, design designation, project completion or source merge.
- Record/event/response bounds and replay projections remain first-version
  constraints. No fake project/design/baseline is created to fill unknown history.

This reconciliation resolves the completion audit's capability gaps while keeping
the seven accepted v0.2 decisions and earlier design bytes intact.
