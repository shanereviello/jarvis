# Engineering history implementation status

As-built checkpoint: October29,2026. This supplements the accepted
[architecture](engineering-history-phase1/architecture.md) and
[ordered backlog](engineering-history-phase1/backlog-and-acceptance.md); their
original proposal/pending language records the design baseline, not current rollout.
Source merge, installation and execution permissions remain separate.

| Backlog slice | Current position | Remaining work |
| --- | --- | --- |
| 0. Design baseline | Accepted separate unprivileged service/store, preserved root operational authority. | Browser decision D2 remains open. |
| 1. Contracts | Implemented structured work/session/checkpoint/document envelopes, deterministic encoding and provenance rules. | Extend additively when a reviewed need requires it. |
| 2. Durable intake/storage | Dedicated private SQLite service deployed; authenticated Unix peers, scoped policy, receipts/outbox and host boundary tests. | Backup/restore verification remains explicitly operator-deferred. |
| 3. Templates/protected binding | Immutable rendering and protected managed review binding deployed. First real review document exported/imported with exact-byte readback. | Continued workflow coverage; document creation is not mandatory for every legacy capture. |
| 4. Explicit interactive client | Explicit recording client and durable spool implemented; private history service deployed. | Convenient session integration and real multi-session acceptance; no universal chat observation. |
| 5. Operational export/retrieval | Allowlisted event exporter and durable receiver implemented; one real task's events imported. Protected review export/intake commands deployed separately. | Routine operator event sync deployment, managed lifecycle orchestration and curated Jarvis history lookup. |
| 6. Optional hooks | Not deployed. | Actual client/event acceptance and minimal trusted metadata design after explicit-client integration. |
| 7. Read-only web | Not deployed. | Resolve D2 network/authentication before any listener, then authorized timeline/document/evidence UI. |
| 8. Web decisions | Not deployed. | Separate authenticated action bindings after read-only web. |
| 9. Closeout | Individual source/host/deployment checks and runbooks retained. | Consolidated two-mode acceptance, upgrade/restore coverage and deferred backup work. |

## Installed review command boundary

`rras-history-review-export` and `rras-history-review-document` use the protected
passive release `history-review-tools-6e024a608121`. They do not automatically export
task events, start recording interactive conversations, share narratives with Jarvis,
or create execution approvals. History work creation stays explicit through the
existing client. The history service and operational journal remain independent.

## Current Section 5 source slice

The managed-event receiver gains complete-handoff initialization and explicit
pending-capture status. The offline tools bundle gains an `events` dispatch mode
for the existing init/inspect/apply/resume/status CLI. This source slice is not
installed by the previously deployed two wrappers; staged releases are immutable.
Its new command path needs its own package/host/deployment review before use.

A pending capture reports its frozen source cursor/event count and verified locally
saved receipt count. An unavailable response can leave a committed server record
with no local receipt; status does not invent delivery or current source freshness.
Explicit resume uses stable event keys and the original receipt. Finished cursors
remain snapshot-specific and do not imply task success, merge or deployment.

The next unfinished Section5 outcomes are production access to repeatable event
sync, lifecycle integration and curated Jarvis search/read. Automatic hooks and
browser access remain later slices. No new paid coding task is required for these
passive data/permission checks.
