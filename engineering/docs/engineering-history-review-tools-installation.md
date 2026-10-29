# First installation of review command wrappers

`review_tools_package.emit_install_helper(destination)` emits a reviewed stdlib
verifier/bootstrap for two new commands over an existing protected release:

- `/usr/local/sbin/rras-history-review-export`: root-only historical inspection/export.
- `/usr/local/bin/rras-history-review-document`: operator private document intake.

The installer takes only the exact release manifest digest. It derives the fixed
release directory and reads its root-private staging completion evidence. The
release must match every manifest hash, retain 0444 payload/manifest modes and
protected root ownership/ancestors. The completion evidence must match that
release, source, member count and all five actual host checks, with no production
mutations. The native interpreter and wrapper parents are protected separately.

`--check-only` checks these conditions and target absence without writing anything.
Installation additionally requires `--approve-wrapper-installation`. It refuses
existing wrapper targets, pending files or installation evidence; it is a first
installation procedure, not an upgrade or overwrite tool.

Each wrapper contains an absolute native interpreter, isolated `-I -B` options,
absolute staged entrypoint, exact manifest pin and fixed export/intake mode. It
clears inherited environment through `/usr/bin/env -i`, uses a minimal PATH/HOME/
locale and forwards caller arguments without interpreting them. The entrypoint
continues to verify manifest/payload before loading bundled dependencies. Actual
root access and repository permissions remain enforced by the existing commands
and authenticated local history service.

Publication writes/fsyncs a new 0755 root-owned pending file in the destination
directory, then creates the final name with an exclusive hard link and removes the
pending name. Existing target races fail without replacement. A successful wrapper
has exactly one link. The private 0700 installation journal at
`/var/lib/rras-history-tools-installations/<manifest-digest>` records the plan,
individual wrapper hashes and final completion. Both commands cannot be published
as a single filesystem transaction: failure after the first leaves that wrapper
installed, preserves pending files/evidence, and records the completed subset.
There is no automatic retry, deletion or rollback. Diagnose partial state before a
separate reviewed recovery decision.

Source merge does not authorize this production installation. Review the emitted
helper digest and concrete target release, obtain the installation decision, then
run preflight and the explicit install command using sudo. Verify installed bytes
and both help paths afterward. This operation creates no service, account, socket,
scheduler, provider call or history record. Existing history and workflow services
are not restarted and the existing `rras-history-client` is untouched.
