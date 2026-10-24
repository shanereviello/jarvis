# Operator decision: defer backup gate (2026-10-23)

The operator explicitly requested skipping encryption/backup setup for now and
agreed to continue with inactive production installation preparation. This
supersedes the earlier pre-retention encrypted-backup/restore requirement for the
current rollout. It does not imply that backups or recovery have been verified.
Engineering records may be lost if the server or database fails.

The earlier snapshot prototype is retained on branch
`codex/history-encrypted-backup-20261023`; it is not merged or installed. No key
creation, private-key transfer, encryption dependency, automatic backup schedule,
off-host destination or retention guarantee is part of this deployment.

Keep the approved dedicated service identity, private SQLite store, per-UID socket
ACLs, repository grants and existing root-journal separation. Source merge,
inactive installation and live activation retain separate human decisions.
A later backup project must revisit key custody, destination, retention and tested
restore explicitly. Historical architecture documents describe the original gate;
this dated decision controls the current rollout.
