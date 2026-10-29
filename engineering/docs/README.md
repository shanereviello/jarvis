# Engineering documentation

- [Current phase closeout](workflow-phase-closeout.md): installed release, first managed acceptance, criterion-level evidence and remaining gaps.
- [Reusable operator runbook](workflow-operator-runbook.md): proposal through explicit decisions/history using supported commands.

- [Architecture](architecture.md): ownership, current boundaries and unfinished work.
- [Publication policy](publication-policy.md): standing dedicated-branch pushes, human merge/deploy.
- [Operations](operations.md): supported entrypoints, runtime pins and review gates.
- [Cleanup](cleanup.md): source removed and dependencies deliberately retained.
- [Hermes intake review](rras-native-hermes-intake-review.md): source/actual-container transport acceptance and deployment gate.
- [Filesystem migration plan](rras-filesystem-migration-plan.md): previously approved migration plan; source cleanup supersedes its old source inventory. Do not execute its historical temporary review commands without a refreshed administrator procedure.

Historical bring-up reports, canary launchers and container experiments are retained in Git commit `ef9cfc09cb3ad7d1a0688adea44f2e0cb2445cfb`, not in the maintained product tree. Actual server task records and reviewed installed artifacts remain untouched.

- [Workflow roadmap](workflow-roadmap.md): accepted next-phase scope, acceptance criteria and deferred work.
- [Shared record contracts](workflow-record-contracts.md): passive repository/work/attempt/event contracts and consistency boundaries.

- [Repository admission preparation](repository-admission.md): reusable candidate preparation and baseline preflight; protected integration is installed; see current closeout.

- [Reusable operator control](operator-control.md): source capture/review/approve/launch/evidence interface and protected admission binding.

- [Workflow journal foundation](workflow-journal.md): transactional records/artifacts, explicit imports, structured summaries, sanitized Jarvis exports and pending index outbox.

- [Managed journal and reader](managed-journal-and-reader.md): durable control-event ordering, receipt reconciliation and projection-only history MCP.

- [Workflow acceptance](workflow-acceptance.md): actual Hermes MCP2, read-only fixture mount and root/UID996/systemd journal/permission acceptance; historical host acceptance; see current closeout for deployment.

- [Production workflow package](workflow-production-package.md): committed-source/offline candidate builder, atomic sanitized generation publication, inactive staging and separate activation/rollback gates.

- [Stopped-worker finish reports](workflow-finish.md): source capture, provenance-aware journal recording and replay; installed finish evidence and provenance limits.

- [Workflow publication receipts](workflow-publication.md): source local commit/handoff integration and imported branch/draft-PR reports; installed frontend draft-PR integration; deployment remains separate.

- [Native board observations](native-observation.md): source read-only snapshot checks and provenance limits; no native lifecycle or production change.

- [Draft-PR connector bridge](draft-pr-connector.md): named-operator one-use frontend contract and normalized receipts; no worker GitHub credentials; installed frontend status in closeout.

- [Independent post-validation contract and remaining host work](post-validation.md)

- [Complete runtime payload, operator frontend and upgrade plan](workflow-upgrade-package.md)

- [Engineering history Phase1 design proposal](engineering-history-phase1/README.md): architecture alternatives, shared records/documents, interactive integration, web access and implementation gates; no deployment or architecture acceptance implied.

- [Local engineering-history foundation](engineering-history-local-foundation.md): new passive engineering contract, caller-owned SQLite/CLI and deterministic private document drafts; no installed service or automatic capture.

- [Explicit interactive history client](engineering-history-interactive-client.md): start/attach/checkpoint/handoff/finish with private transactional spool, pending delivery and stable receipts; local transport only.

- [Engineering-history service access boundary](engineering-history-service-access.md): explicit repository grants, service peer receipt attribution and scoped passive dispatcher; no installed socket/service.

- [Authenticated Unix history transport](engineering-history-unix-transport.md): kernel peer checks, bounded private RPC and explicit interactive socket mode; no installed service or cross-UID host acceptance.

- [Isolated history host acceptance](engineering-history-host-acceptance.md): hash-pinned package and numeric-UID/network-isolated fixture; actual sudo result and production installation remain separate gates.

- [Production history installation blueprint](engineering-history-production-package.md): inactive pinned runtime/unit/policy, exact local ACLs and disable-only rollback; separate hardened-unit, backup and installation gates.

- [Actual history unit/ACL host acceptance](engineering-history-hardened-unit-acceptance.md): isolated production-profile unit, private client groups, revocation/replay and UID1000 ACL reachability; actual isolated host acceptance passed; production installation remains separate.

- [Backup deferral](engineering-history-backup-deferral.md): dated operator decision superseding the original pre-retention backup gate.
- [Inactive history installer](engineering-history-inactive-install.md): pinned stdlib-only installer, additive private custody, empty initialization and stopped/disabled verification.

- [First history activation](engineering-history-first-activation.md): exact inactive-state preflight, start/read-only acceptance/boot enablement and evidence-preserving failure handling; separate live decision required.

- [Managed engineering-history links](engineering-history-managed-links.md): allowlisted read-only operational export, exact work/revision binding and durable passive import checkpoints; source-only, no privileged deployment.

- [Managed-history host acceptance](engineering-history-managed-host-acceptance.md): pinned synthetic root exporter, distinct numeric UID handoff, lost-response/cursor recovery and restart/replay; actual sudo acceptance pending.

- [One-work production history export](engineering-history-production-export.md): exact reviewed target, frozen read-only source snapshot, protected original and private operator handoff; no import or lifecycle deployment.

- [Repeatable managed-history receiver](engineering-history-managed-sync.md): explicit private capture review, frozen delivery/resume and receipt-verified status; no automatic lifecycle trigger.

- [Standard managed review document](engineering-history-managed-review-document.md): deterministic private document and passive capture companion; protected custody and versioned approval enforcement remain separate.

- [Protected document approval](engineering-history-document-approval.md): private Markdown custody and opt-in v2 approval/launch verification; source-only, isolated host acceptance and installation remain separate.

- [Document approval host acceptance](engineering-history-document-host-acceptance.md): pinned model-free v2 custody/launch and real UID denial fixture; actual sudo result required.

- [Exact review-document intake](engineering-history-review-document-intake.md): passive packet and receipt/readback-verified private receiver; protected handoff and production intake remain separate.

- [Protected review-document handoff](engineering-history-review-document-handoff.md): historical root custody reader, private operator transfer and pinned isolated cross-UID rehearsal; actual sudo acceptance required.

- [Review-document intake commands](engineering-history-review-document-commands.md): explicit private packet inspection, frozen preparation, hash-bound intake and durable resume into an existing engineering work revision; source tooling, separate installation.
- [Review export commands and package](engineering-history-review-export-commands.md): exact historical root inspection/export and offline pinned passive tool assembly; separate staging and installation.
- [Inactive review tools staging](engineering-history-review-tools-staging.md): verified protected payload staging and isolated host command/permission checks; no wrappers or service changes.
- [Review tools first installation](engineering-history-review-tools-installation.md): explicit, exclusive publication of pinned export/intake wrappers over a host-verified release; separate production decision.
