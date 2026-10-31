# Inactive curated production package

The production topology is approved; this package makes its first installation
reviewable without starting the reader or publishing any history. Source merge,
installation, service activation, Hermes integration and real content publication
retain separate operator decisions.

The package pins committed source and offline schema dependency bytes. It derives
a protected `curated-history-<digest>` release identity from the core file map and
source commit, then renders the reviewed reader unit and fixed publication wrapper.
The stdlib bootstrap verifies the exact manifest, safe paths, single-link regular
files, byte digests and size bounds before any installation. Root never executes
or imports the caller-writable candidate as code.

A sudo `--check-only` preflight performs no mutations. It requires the existing
history account/group to remain UID/GID 995 with no extra groups, the proposed
`rras-curated-reader` identity and UID/GID 994 to be unused, protected destination
parents and all first-install paths to be absent. It also requires the protected
nine-case host acceptance record and byte-for-byte agreement of every runtime
source/dependency with that tested protected release. New packaging and deployment
artifacts are reviewed separately; changed runtime requires new acceptance.

Explicit inactive installation creates:

- A root-owned read-only release under `/opt/rras-engineering/releases`.
- A locked, no-home, no-login reader account/group at UID/GID 994, with no private
  history policy grant or supplementary groups.
- `/var/lib/rras-curated-history/catalog`, private to UID/GID 995, with only a
  fixed Jarvis repository configuration and empty generations directory. There is
  no current pointer or selected content.
- Root-private publication request and attempt directories under
  `/var/lib/rras-curated-publications`.
- Root-protected `/etc/rras-curated-history/read-policy.json`, readable by the
  history owner, granting the dedicated reader only the Jarvis repository.
- The disabled, inactive `rras-curated-history-read.service` unit and a root-owned
  `/usr/local/sbin/rras-curated-publication` wrapper fixed to this release. The
  wrapper accepts only the exact reviewed-request-digest argument; callers cannot
  override the release through extra arguments.

An exclusive root-private installation journal precedes mutations. Every account
command has an intent and private output record. Existing state is never adopted
or overwritten; partial installation stops without automatic retry or rollback.
The installer reloads systemd definitions but does not start/enable a unit. It
verifies the reader remains inactive and disabled, the runtime socket directory
is absent and the catalog has no current generation. It does not open the private
engineering database, change Hermes configuration, use provider credentials or
add history records. Backup verification remains explicitly deferred by the
operator's existing decision.

After inactive installation, the protected production launcher and UID-995 CLI
still need a separately approved empty-catalog acceptance before activation.
Real curated summaries require their own exact preview/request review and explicit
publication decision. Hermes mounting/configuration and service activation follow
separate preflight and acceptance steps; an empty catalog is not task success or
release/deployment evidence.
