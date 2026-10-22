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
