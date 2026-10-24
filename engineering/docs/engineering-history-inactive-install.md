# Inactive history installation

The operator deferred encrypted backup/restore on 2026-10-23. The generated
installation plan records that decision and makes no verified-recovery claim.
The hardened production service runtime already passed actual isolated host
acceptance, including separate UIDs, exact ACLs, restart and revocation. This
installer leaves production history stopped and disabled.

`install_package.emit_helper` combines the reviewed stdlib-only manifest checks
and installer into one hash-pinned script. Root verifies every candidate byte and
independently regenerates installation artifacts. It never imports runtime or
vendor Python from the user-owned candidate. Runtime initialization runs only as
the new unprivileged history identity, in a private network namespace with no
capabilities, supplementary groups or provider environment.

Preflight checks protected executable/destination ancestors, absent target paths,
absent account/group and no existing systemd unit. Refuse collisions; do not adopt
or overwrite prior records. A read-only `--check-only` invocation performs the
same preflight and no writes. Root verification is separate from source merge.

After separate inactive installation approval, the helper:

1. Creates a root-private installation journal and records the exact candidate.
2. Allocates `rras-history` system group/account with locked password, nologin
   shell, no home creation and no login-log initialization. Existing user groups
   are unchanged; existing history identities cause refusal.
3. Copies the root-owned release (directories0755/files0444), verifies its bytes,
   creates root:history policy directory0750/file0640 and service-owned store0700.
4. Initializes only an empty schema-v1 SQLite database as the service identity;
   verifies integrity, database0600 custody and empty submissions/outbox.
5. Adds the exact unit0644 and client wrapper0755; reloads systemd definitions.
6. Verifies the unit remains inactive, PID0, disabled, and runtime/socket absent.

It never starts/enables/disables services, accesses provider credentials, modifies
Hermes/coding services/root workflow records, changes repository admission or
imports synthetic acceptance data. Systemd daemon-reload loads unit definitions
without restarting services. Installation commands and bounded diagnostics stay in
the root-private journal. On failure, stop and preserve all partial state; do not
retry, delete the account, recreate the database or perform automatic rollback.

Expected paths: `/opt/rras-engineering/releases/history-<payload-prefix>`,
`/var/lib/rras-history-installations/history-<payload-prefix>`,
`/var/lib/rras-engineering-history`, `/etc/rras-engineering-history`,
`/etc/systemd/system/rras-engineering-history.service`,
`/usr/local/bin/rras-history-client`. No browser/TCP listener or automatic session
capture is added. A stopped service means client submissions can remain locally
queued; installation alone does not deliver narrative records.

Source merge and inactive installation need separate decisions. Live activation,
boot enablement and real-client acceptance form a later separately approved step.
