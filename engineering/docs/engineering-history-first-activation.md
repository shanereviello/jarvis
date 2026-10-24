# First production history activation

Inactive installation completed with service UID/GID995. Host verification found
loaded/inactive/PID0/disabled and the expected account, protected release, config,
empty database and wrapper. This document describes the next separately approved
step; it does not authorize starting the service.

The generated `activation_package.emit_helper` tool includes the reviewed stdlib
runtime verifier and installation primitives plus bounded first-activation checks.
It imports no caller-writable runtime/vendor code as root. Installed source and
policy remain unchanged. The runtime payload is the one accepted in the actual
isolated hardened-unit test.

Read-only root preflight verifies the exact installed release/artifacts/custody,
matching private inactive-install receipt and service identity, empty/integral
schema-v1 database, stopped/disabled unit and absent runtime/activation journal.
It refuses a prior activation attempt. It creates nothing with `--check-only`.

After separate explicit live approval, the concrete scope is:

1. Create root-private `activation-01` evidence beneath the installation journal.
2. Start only `rras-engineering-history.service` once. Wait at most ten seconds
   for its socket; inspect PID identity, supplementary groups, zero capabilities,
   no-new-privileges and a network namespace different from the host.
3. Run read-only probes as UID1000 with no supplementary groups/capabilities and
   a private network namespace. Query empty history for jarvis/robot_ws; check
   refusal for an ungranted repository and unsupported action route. Verify
   direct private policy/database file access is denied.
4. Run UID996/997 worker probes proving private file and socket access denied.
5. Confirm database submissions/outbox remain empty. No synthetic task or note is
   written to production by activation acceptance.
6. Enable this history unit at boot only after checks pass; verify enabled/active
   and the same live PID. Return and retain the completion evidence.

Failure preserves the actual live state, private diagnostics and attempt fence.
There is no automatic restart/retry, rollback, stop, account deletion or database
restore. A failure after start can leave the history service running; inspect the
protected evidence and get an explicit recovery decision. Later activation,
upgrade or restart is not handled by this first-activation-only tool.

No provider calls, coding runs, root workflow changes, Hermes restarts, browser
listener, automatic transcript capture or engineering-history imports occur.
Backup verification is deferred by the operator's dated decision. Initial live
acceptance is read-only: real interactive recording remains explicit opt-in.
