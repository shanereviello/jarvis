# Ordered implementation backlog and acceptance specification

No implementation slice starts from a document saying 'approved' alone. D1 direction is accepted;
review source/fixtures, separately approve installation/activation and keep paid-task
approval separate. D2 must be resolved before browser deployment. Estimates/task
assignment can follow decisions; no arbitrary delivery dates are promised.

| Slice | Dependencies | Concrete deliverable | Exit checks |
| --- | --- | --- | --- |
| 0. Finalize Phase1 design baseline | D1 direction accepted | ADR, template/authority/privacy invariants, named web/backup decision gates | Detailed specification and draft templates source-reviewed; D2 remains an explicit web-deployment gate. |
| 1. Engineering contracts | 0 | Versioned new work/session/document/claim envelopes plus v1 adapters and deterministic encoding | Cross-repo/mode/revision rules, unknown timestamps, duplicate/conflict semantics; v1 fixtures still valid. No production migration. |
| 2. Durable intake/storage | 1,D1 | Chosen store/writer, bounded idempotent intake, atomic content+receipt/outbox, explicit private/shared policy | Restart/crash/concurrent-write cases; service principal cannot read root DB/key or perform actions; known limits/backup fixture. |
| 3. Templates and protected binding | 1,2 | Review/checkpoint/completion renderer, immutable bytes/manifests, exact managed capture/approval binding | Rendering determinism, stale template/content/scope invalidation, no changed approval for old captures, recorded criteria/evidence limits. |
| 4. Explicit interactive client | 2,3 | Start/attach/checkpoint/handoff/finish, private bounded spool, durable receipts | Multi-session resume/fork association; unavailable intake -> visible pending; no automatic paid execution or raw chat collection. |
| 5. Operational export and retrieval | 2,3 | Allowlisted root fact/content exporter, import checkpoints, curated Jarvis search/read | Export outage+replay safe, source digests/permissions verified, no evidence-provenance promotion, missing source/time visible. |
| 6. Optional lifecycle hooks | 4 | Trusted minimal hook metadata + explicit-capture skill/tool guidance, if actual client acceptance succeeds | Real desktop/server events tested, no trust bypass, no transcript parser dependency, no guaranteed close-on-crash claim. |
| 7. Read-only web | 3,5,D2 | Authenticated inbox/document/timeline/evidence pages | Reader isolation, private snippet denial, Markdown safety, withdrawn content and stale views; no execution permission. |
| 8. Protected web decisions | 7 | Narrow authenticated action requests and exact target bindings | Duplicate clicks, expired/revoked/changed scope, lost responses and action/result uncertainty; ordinary clients cannot approve as human. |
| 9. Rollout and closeout | Earlier slices | Consistent backup/restore, rehearsed upgrade/rollback, maintained runbook and evidence matrix | Isolated restoration with actions disabled, existing root records intact, client opt-in, actual two-mode acceptance, separate installation/paid grants. |

## Required scenarios

| Scenario | Required behavior |
| --- | --- |
| Work spans three sessions | Same work ID, explicit session links and current revision; no fabricated continuous observation. |
| Scope changes after approval | New revision/document digest; old one-use grant cannot approve the new revision. |
| Interactive -> managed handoff | Same engineering identity, explicit operational revision/mode mapping and admission; fresh protected paid approval required. |
| Two repositories in one initiative | Two per-repo work items grouped by explicit relation; no mutation of repository identity. |
| Failed/interrupted attempt | Retain partial evidence, unfinished/uncertain status and stop facts; no inferred success or automatic retry. |
| Concurrent edits/checkpoints | Distinct notes can coexist; conflicting scope revision update refuses/rebases via expected head. |
| Human corrects summary | New correction/superseding version visible with evidence links; original approved bytes unchanged. |
| PR merges, never deploys | Show merged with exact commit/evidence; deployment unknown/not-applicable as explicitly recorded, never inferred. |
| Sensitive artifact/withdrawal | Private payload absent from Jarvis/browser/search; sharing change produces explicit new view and cache/index invalidation. |
| Retrospective import | Source list, provenance and unknown original timestamps explicit; no observed approval implied. |
| Client/server/export outage | Bounded spool/outbox retains data; UI says pending/lagging; recovery deduplicates and never starts coding. |
| Malformed or spoofed event | Reject schema/size/reference/caller errors; user-controlled observed/human actor labels grant nothing. |
| Render/search rebuild | Rebuild derived views from records; approved document bytes/digest still retrievable unchanged. |
| Duplicate/ambiguous web action | One-use fence and original receipt preserved; do not repeat merge/deploy/launch to repair journaling. |
| Restore backup | Hash/reference consistency verified, action execution disabled, no replay of consumed approval. |

## Evidence and release gates

Source contract/renderer fixtures establish only their tested local semantics.
Storage/identity/network/hook/host changes need corresponding actual isolated
acceptance. A new model call is unnecessary for schema, rendering, hooks using fake
events, and read-only UI tests. Real managed acceptance only under a separately
scoped explicit paid approval. Do not use source merge to authorize new listeners,
service accounts, root broker permissions, production DB changes or ledger activation.

Success for Phase1 is an accepted design and reviewable backlog; success for the
product requires the later source/host/client/browser acceptance. Keep those separate.

## Initial implementation boundary

Use [the initial specification](initial-implementation-spec.md) to implement slices
1 and the non-deployed local library/CLI portion of slice2 first. Deliver contracts,
SQLite transactional fixtures, deterministic documents and explicit local commands
before creating service accounts or listeners. Root export integration, privileged
approval changes, hooks, browser controls and actual service installation follow
separately reviewed slices. This keeps the next PR testable without sudo/model calls.

The first [local foundation source slice](../engineering-history-local-foundation.md) now implements strict new envelopes, caller-owned transactional records/receipts/outbox and immutable draft rendering. It does not deploy the service or change protected approvals.

The [explicit interactive client source slice](../engineering-history-interactive-client.md) adds local durable context and spool-backed commands against that foundation. Actual authenticated service transport, hooks and shared narrative retrieval remain separate.

The [service access source slice](../engineering-history-service-access.md) defines
repository-scoped passive dispatch and distinct service-peer receipts. Peer UIDs are
supplied by tests until the following authenticated Unix transport is implemented;
no kernel authentication or host isolation is established by these policy tests.

The [Unix transport source slice](../engineering-history-unix-transport.md) implements
real kernel peer checks, protected local framing/policy/socket lifecycle and explicit
interactive service configuration. Disposable same-UID socket/subprocess tests do not
replace the next isolated cross-UID sudo acceptance or a separate deployment decision.

The [host acceptance source](../engineering-history-host-acceptance.md) prepares a
bounded pinned payload and real distinct-UID fixture without persistent accounts.
The corrected operator-run attempt02 passed real cross-UID acceptance with the
[recorded evidence](../engineering-history-host-acceptance.md#verified-attempt02-evidence).
Production account/service installation still requires a separate concrete decision.

The [production package source](../engineering-history-production-package.md) prepares
an inactive dedicated-account/unit/policy/runtime blueprint and exact per-UID local
ACLs. Earlier cross-UID acceptance does not establish this new hardened-unit/ACL
combination. Its host acceptance, encrypted backup/restore and explicit staged/live
installation decisions remain required before real production retention.

The [hardened-unit fixture](../engineering-history-hardened-unit-acceptance.md)
prepares the next actual systemd/per-UID-ACL gate with private client groups and
controlled revocation. Its offline packaging/unit syntax tests are not a privileged
success result; the pinned operator-run acceptance remains pending.
