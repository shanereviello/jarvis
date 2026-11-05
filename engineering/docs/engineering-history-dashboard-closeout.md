# Engineering-history foundation and read-only dashboard closeout

Status: deployed milestone; final browser acceptance and documentation merge pending.
This closes the foundation/read-only scope, not the entire original architecture.
The operator requested separate future UI tasking and explicitly deferred broader
Jarvis access design into that backlog. No runtime change is included here.

## Delivered scope and evidence

| Capability | Evidence and practical limit |
| --- | --- |
| Private structured engineering history | UID995 SQLite service, scoped Unix peers, durable receipts/spool, immutable documents; isolated cross-UID/hardened-unit acceptance passed. |
| Interactive work continuity | Explicit recording/resume; operator-designated A/B/C preserved the work and records. Native Codex session identity remains unverified; no automatic chat capture. |
| Managed records/documents | Installed allowlisted export, exact-document intake and explicit event sync/review. Imported claims retain provenance; freshness is snapshot-specific. |
| Jarvis retrieval | Curated reader/writer and Hermes MCP deployed; three selected summaries published/read back. No blanket private-history grant. |
| Dashboard source | PR80–87 merged; JWT validation, read-only pages, protected startup/package/install and exact activation controller. Final focused suite:172passing tests. |
| Host boundaries | Eight isolated server/history cases, seven protected-package cases and four synthetic connector-route cases passed. Fixture evidence retained; no paid coding run required. |
| Production origin | Exact release `history-web-9e150671dcfa`, manifest `1b9f387b5e9dfb9436d4e5144fcfab372b5622c67e8bc5daa22032fb72d19da0`; inactive install then separately approved activation. UID993 active/enabled, read-only grant, unsigned denial and live public keys verified. |
| Browser access | Operator reports work list and overview/timeline/documents/evidence tabs visible. Operator also confirms actual Markdown view/download and working sign-out. Evidence-link and post-sign-out refresh checks remain unverified. |

The dashboard reads the private engineering service, not Git checkouts, live GitHub,
raw conversations, the root operational database or a PostgreSQL activity ledger.
Recorded intent, imported outcome, source merge, deployment and verification remain
distinct facts. Work IDs correlate each scope; parent initiative grouping is deferred.

## Final acceptance checklist

- [x] Explicit inactive-install and origin-activation decisions; completed receipts.
- [x] Independent active/enabled service status and unsigned origin403.
- [x] Operator confirms authenticated dashboard/work-list/tab visibility.
- [x] Operator confirms actual Markdown opening and download.
- [ ] Operator follows an evidence link to its intended destination.
- [x] Operator reports webpage sign-out worked.
- [ ] Explicit refresh-after-sign-out denial confirmation.
- [ ] Closeout source reviewed and explicitly approved for merge.

Do not turn pending checks into observed facts. Historical isolated browser/source
checks do not establish a real Cloudflare login/sign-out outcome. A current work
count is an observation, not an acceptance requirement. No new paid execution is
needed to close this milestone.

## Operating handoff

Use the [operator runbook](engineering-history-operator-runbook.md) for explicit
recording/resume, pending delivery, managed refresh and deliberate curated sharing.
See [implementation status](engineering-history-implementation-status.md) for the
original numbered sections. Protected installation/activation evidence stays on the
host; private notes/configuration and raw diagnostics do not belong in this PR.

Existing isolated restart, replay, revocation, outage and workflow-upgrade evidence
covers its tested boundaries. This milestone does not claim a rehearsed upgrade or
restore of the newly combined history/dashboard deployment. Preserve future history
on rollback; never restore old data merely to repair a publication/install receipt.

## Deferred backlog

These are proposals for separate agreed work plans, not deployment authorization.

1. **Expanded web UI:** operator-led requirements, navigation and useful engineering
   views; parent initiative grouping/correlation across per-repository work items.
2. **Broader Jarvis MCP retrieval:** decide whether Jarvis may read all `jarvis`
   engineering history or selected categories/documents, including exclusions,
   withdrawal and cross-repository policy. Prefer scoped search/work/timeline/
   document read APIs with provenance, evidence and freshness; direct arbitrary SQL
   is not the default. Current SQLite storage need not change; PostgreSQL is a
   separate decision if justified. Define explicit versus automatic synchronization,
   indexing, failure/replay behavior and actual Hermes acceptance. Retain current
   three-entry curated access until separately approved rollout.
3. **Protected browser decisions (original Section8):** exact-target authenticated
   action requests; stale/revoked approvals, duplicate clicks, lost responses,
   one-use execution and separate publication/merge/deployment authority.
4. **Optional lifecycle integration (Section6):** trusted minimal session metadata,
   convenient explicit capture and actual client acceptance; no universal transcript
   collection or invented native session authentication.
5. **Routine lifecycle orchestration:** managed export/import freshness and continued
   interactive-to-managed identity/evidence coverage. Integration must never retry
   coding to repair telemetry or silently publish private notes.
6. **Remaining Section9 resilience:** combined-service upgrade/rollback rehearsal,
   consolidated two-mode acceptance coverage, consistent encrypted backup/isolated
   restore with actions disabled, plus off-host retention and RPO/RTO decisions.
   Backup verification remains explicitly operator-deferred, not completed.
7. **Broader automation:** autopilot/delegation enforcement, multiple workers, budget
   controls and richer repository/robot recipes remain outside this milestone.

Immediate handoff after final acceptance is a separate requirements/work-plan
conversation, not automatic Section8 implementation or widened Jarvis access.
