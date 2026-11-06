# Project workspace implementation and operator handoff

This source change implements the accepted [architecture v0.2](engineering-project-workspace/JARVIS-PROJECTS-AND-WEB-UI-ARCHITECTURE-DRAFT-v0.2-20261106.md).
The source is for review; production migration, policy changes, installation and
activation require an explicit operator decision. No project assignments or private
history are seeded by installing the source.

## Data and lifecycle

- One repository or the sole initial non-Git category `jarvis-non-git` per project.
- One current primary project per assigned work; legacy work stays unassigned until
  explicitly associated. Reassignment/removal and design-reference changes append
  events; they do not revise existing work bytes or receipts.
- Project metadata revisions retain overview, intended outcome, scope/exclusions,
  optional owner and a change summary. Recorded lifecycle and archive state are
  independent. Closed projects require explicit reopening before modification.
- Architecture versions store exact Markdown, content digest, predecessor, source,
  project revision and baseline at creation. Saving a draft does not designate it.
  Work pins a design version; a later project designation does not retarget it.
- Git baseline versions bind one exact commit to the project's repository. Starting
  and current selection are explicit. Non-Git baselines are not applicable.
- Closeout requires dispositions for unresolved/current-scope work, a governing
  design for completion, and a Git baseline or omission reason where applicable.
  It preserves project/design/baseline/membership/work references and a signed
  snapshot boundary. Reopening does not rewrite an earlier closeout.

Private-history source provenance remains reported/imported. Project completion is
not independent acceptance, merge, deployment or verification. A recorded
`verified_at` on a baseline is explicitly source-reported information.

## Storage and explicit migration

The existing private `history.sqlite3` stays with its service owner. New empty
stores still initialize as schema v1. Normal service startup never upgrades a
database. The new runtime reads both v1 and v2; the former runtime refuses v2.

`projects.py` provides a read-only migration plan over exact legacy record/outbox
bytes and SQLite schema. Applying it requires that exact fingerprint in a single
write transaction. It adds immutable project submissions/outbox and a private
snapshot-key table, then sets `user_version=2`. Legacy rows and receipts are not
updated. Failure before commit rolls the added tables back with the transaction.

Per-scope view tokens bind the work/project stream boundaries with a local MAC.
They do not expose other scopes' counts and never substitute for authorization.
The snapshot key stays inside the private database. Complete backup/restore must
preserve that database; changing the key would invalidate historical tokens.

Existing record and response bounds remain. The project log has a separate
10,000-event bound, requests remain at most 128 KiB, and responses/closeout receipts
are bounded. Larger-scale indexing/performance is not claimed. Projections are
computed in the service, not by scanning unrelated records in the browser.

### Local owner-only procedure

Use a disposable caller-owned directory and local test runtime first. `$STORE`
and `$REQUEST` below are deliberately selected private paths, not defaults for
production. Keep source inputs outside Git with mode 0600 and parent mode 0700.

```sh
python engineering/tools/rras_history/project_entry.py migration-plan --store "$STORE"
python engineering/tools/rras_history/project_entry.py migrate --store "$STORE" \
  --expected-sha256 "$EXACT_REVIEWED_PLAN_SHA256"
```

In production, the store belongs to the service identity, not the interactive
operator. Do not change its owner/permissions or run a desktop SQLite client
against it. A separately reviewed stopped-service procedure must select the exact
release, plan and identity. Database downgrade/restore to repair deployment
receipts is not a rollback strategy; retain future history.

## Explicit authoring and recovery

`project_entry.py` is the vendored-runtime bootstrap for `project_cli.py`.
The CLI accepts complete private JSON envelopes from the versioned
`engineering-project-v1.schema.json` contract. It supports local owner mode or
authenticated Unix transport. It never consumes execution approvals or starts a
worker. Source examples under `engineering/contracts/examples/project-*.json`
are synthetic and must not be submitted as real history.

```sh
python engineering/tools/rras_history/project_entry.py submit \
  --service-socket /run/rras-engineering-history/service.sock --service-uid 995 \
  --request "$EXACT_PRIVATE_REQUEST"
python engineering/tools/rras_history/project_entry.py read \
  --service-socket /run/rras-engineering-history/service.sock --service-uid 995 \
  --request "$SCOPED_PRIVATE_QUERY"
```

Retain the complete request, its event key, returned receipt and new head digest.
An identical retry under the same caller/operation/key returns the original
receipt, including after a lost response. Never edit the saved request or allocate
a new key solely to recover telemetry. An edited input needs a new event key and
the appropriate current head. An abandoned request does not undo a committed row.

For each project, supported operations are:

| Operation | Required association |
| --- | --- |
| `project.create` / `project.revise` | Full metadata, revision and exact previous project head for revision. |
| `project.state` | New state, summary/reason, closeout dispositions and baseline omission where applicable. |
| `project.archive` | Explicit archive/unarchive state and reason. |
| `architecture.save` | Stable document ID, next version, predecessor content digest, exact Markdown and change summary. |
| `architecture.designate` | Exact saved version/content digest and reason. |
| `baseline.record` | Stable baseline ID, next version, predecessor digest, exact commit and source information. |
| `baseline.select` | Saved version/digest and starting/current role. Original starting selection is retained. |
| `membership.assign` | Work ID, current association head, target project head, previous project head if moving, and explicit current design pin. |
| `membership.remove` / `membership.designate` | Exact current association head and a reason. |

Read queries are `{scope, query}`, where `scope` is `{kind: repository, id: jarvis}`
or `{kind: non_git, id: jarvis-non-git}` and `query.view` selects `projects`,
`project`, `works`, `work`, `architecture`, `compare`, `history` or `document`.
Use exact IDs and the returned snapshot token on subsequent pages.

## Non-Git work and legacy compatibility

`engineering-history.v2` introduces an explicit `scope` in full work definitions.
It is enabled only after the migration. Non-Git work requires `baseline=null` and
empty Git paths; no repository ID is fabricated. Existing v1 work is interpreted
using its original `repository_id`, retaining original serialized bytes/digests.
Follow-up notes, outcomes and document operations retain their existing shapes.

The original `documents.py` and templates remain byte-identical. A separate
`scoped_documents.py` handles v2 work documents. Historical stored documents are
retrieved without re-rendering, and legacy intake retains its pinned renderer.

The interactive client can queue/start/attach the new work contract through its
existing explicit transport. Managed imports continue using the original exact
operational-work binding; project assignment is a separate passive association.
Curated Jarvis publication/retrieval remains unchanged and repository-scoped.

## Access and webpage

The service still accepts `engineering-history-access.v1`. To expose the non-Git
category, a reviewed v2 policy adds `category_read` and `category_write` arrays to
each principal, alongside existing `private_read` and `write` repository arrays.
Each category array is empty or contains only `jarvis-non-git`; write requires read.
Changing the policy is an explicit host action, not a source migration side effect.

The dashboard still accepts its v1 configuration. Optional v2 configuration adds
`categories` (empty or `jarvis-non-git`), intersected with actual service grants.
It can also serve a category-only configuration. New dashboard transports allow
only `workspace_scopes` and `project_read` in addition to prior reads. They never
allow `project_submit` or a migration method.

The page exposes only GET/HEAD routes, including:

```text
/api/workspace/scopes
/api/workspace/{view}?scope_kind=...&scope_id=...&...
```

It provides All projects, All work, Unassigned work, scope selection, project
state/archive filters, and Overview/Work/Architecture/Baselines/History tabs.
Exact architecture versions and closeouts have stable hash URLs. Architecture
content and diffs are text, with verified Markdown download. Work links retain
the existing detail views. Counts use distinct current work IDs. Prior-scope
outcomes are labeled rather than treated as current-scope completion.

Authentication/JWT validation, no-store headers, CSP and private-state clearing
remain in force. Category names, doc text and diff content never become HTML.
The user-facing design does not grant new browser action authority.

## Validation and production rollout gate

The accompanying tests cover actual disposable SQLite migration/replay, scope
denial, concurrent association conflicts, architecture history and digest checks,
Git baselines, non-Git intake, snapshot paging, and closeout/reopen behavior.
Signed ASGI tests exercise the production JWT verifier and read-only routes.
The optional Chromium test uses those same signed fixture routes and stores; it
does not contact real Cloudflare or read private host history.

```sh
python -m pytest -q engineering/tests/test_history_projects.py \
  engineering/tests/test_history_project_web.py
RRAS_UI_BROWSER_TESTS=1 python -m pytest -q \
  engineering/tests/test_history_project_browser.py
```

Chromium acceptance requires a separately provisioned Playwright test runtime and
browser; it adds no production dependency. The ordinary suite skips that test when
not explicitly enabled. A browser fixture is not live authenticated acceptance.

### Isolated host acceptance — November 6, 2026

The operator ran the pinned helper and supplied a successful
`isolated_dashboard_project_host_verified` result for source commit
`a4dcb6a98811acef108cfc55ce027adbd73b18ba`, with fixture manifest SHA-256
`496756c9b769a4853be7f2e284ebe9932304b3340755e47b4063092c0616dc3a`.
This documentation follow-up does not change the tested implementation or packages.

All 12 reported checks passed, covering hardened separate service/reader OS
identities, protected configuration, signed fixture authentication, scope and write
denials, explicit v1 migration, project reads, governing/draft architecture diffs,
non-Git baselines, and service outage/restart/revocation without cached history.
The result reports an unchanged fixture database, stopped units, removed temporary
identities, zero API calls and no production or Cloudflare changes. Subsequent
read-only host checks independently confirmed both fixture units inactive and
both temporary users/groups absent. The protected result file was not independently
read because noninteractive sudo still required a password; evidence attribution
is the operator's supplied result, not an independent reread of that file.

This synthetic rehearsal did not test real Cloudflare key fetching, the live
connector route or a real authenticated browser session. It does not authorize
production migration, policy changes, installation or activation.

Source package allowlists include the new contracts/modules. Their manifests and
disabled deployment flags remain enforced. No old protected fixture directory or
activation receipt should be reused for a new release. Production rollout must
select the exact reviewed runtime packages and target identities, preserve the
accepted rehearsal receipts, and obtain the required operator decision for the
stopped-service migration/configuration/restart procedure and forward recovery.
After activation, live authenticated browser/connector acceptance remains. The existing live
services, database, permissions and Cloudflare route remain unchanged by this PR.
