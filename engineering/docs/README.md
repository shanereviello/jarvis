# Engineering documentation

- [Architecture](architecture.md): ownership, current boundaries and unfinished work.
- [Publication policy](publication-policy.md): standing dedicated-branch pushes, human merge/deploy.
- [Operations](operations.md): supported entrypoints, runtime pins and review gates.
- [Cleanup](cleanup.md): source removed and dependencies deliberately retained.
- [Hermes intake review](rras-native-hermes-intake-review.md): source/actual-container transport acceptance and deployment gate.
- [Filesystem migration plan](rras-filesystem-migration-plan.md): previously approved migration plan; source cleanup supersedes its old source inventory. Do not execute its historical temporary review commands without a refreshed administrator procedure.

Historical bring-up reports, canary launchers and container experiments are retained in Git commit `ef9cfc09cb3ad7d1a0688adea44f2e0cb2445cfb`, not in the maintained product tree. Actual server task records and reviewed installed artifacts remain untouched.

- [Workflow roadmap](workflow-roadmap.md): accepted next-phase scope, acceptance criteria and deferred work.
- [Shared record contracts](workflow-record-contracts.md): passive repository/work/attempt/event contracts and consistency boundaries.

- [Repository admission preparation](repository-admission.md): reusable candidate preparation and baseline preflight; privileged integration pending.

- [Reusable operator control](operator-control.md): source capture/review/approve/launch/evidence interface and protected admission binding.

- [Workflow journal foundation](workflow-journal.md): transactional records/artifacts, explicit imports, structured summaries, sanitized Jarvis exports and pending index outbox.

- [Managed journal and reader](managed-journal-and-reader.md): durable control-event ordering, receipt reconciliation and projection-only history MCP.
