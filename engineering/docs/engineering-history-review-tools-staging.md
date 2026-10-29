# Inactive review tools staging and host checks

`review_tools_package.emit_stage_helper(destination)` emits a standard-library
bootstrap containing the reviewed fixed package verifier and
`stage_review_tools.py`. The operator must verify its reviewed digest before sudo.
The bootstrap verifies candidate bytes as data before staging or evaluating code;
it never imports modules from the unprotected candidate.

Preflight requires root and checks protected release/journal parents, the native
interpreter directory and resolved interpreter, and the unshare/setpriv binaries.
It verifies the manifest and every bounded member and refuses any existing target
release or journal. `--check-only` performs no writes. The staging operation creates
only these fixed destinations:

- `/opt/rras-engineering/releases/history-review-tools-<manifest-prefix>`: root-owned,
  directories 0755, files 0444, original manifest retained.
- `/var/lib/rras-history-tools-staging/<full-manifest-digest>`: root-private 0700
  journal with 0600 plan, probe diagnostics and final completion or stopped record.

All payload writes are exclusive and fsynced; directories are fsynced. The final
protected payload is verified again before launching any staged entrypoint. A
failure preserves the journal and partial release, refuses later adoption/retry,
and does not remove evidence or invoke recovery against production.

Host validation invokes bounded subprocesses under separate private network
namespaces, with no supplementary groups, no capabilities, no provider environment
and no-new-privileges. It checks:

1. Both packaged command dispatch paths as root and UID1000.
2. UID1000 and UID996 cannot write the release, manifest or entrypoint.
3. Actual child identities, private networks and privilege restrictions.
4. UID1000 and UID996 are refused by the root-only export command before source access.
5. A wrong manifest pin is refused before dispatch.

These checks create no accounts, sockets or services and never select a production
capture, journal or history database. They do not repeat the prior distinct-UID
full document export/import rehearsal or claim a fresh production export passed.
The root source access guard uses a nonexistent source selection only in the
unprivileged refusal probes; it must refuse before any source read.

A successful result means an inactive protected payload and real host command/
permission checks passed. No wrappers are installed, no existing command pointer
changes, no Hermes/history service restart, no history import or worker/provider
execution occurs. Separate source merge and production installation decisions
remain required. The actual host validation must pass before treating source as
ready for this staging procedure's final review.
