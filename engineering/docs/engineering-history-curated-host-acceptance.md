# Isolated curated-reader cross-UID host acceptance

The fixed fixture uses only synthetic data under
`/var/lib/rras-curated-read-acceptance-20261029`. Numeric service61121, reader61122
and denied61123 must be unused in NSS/process state; no accounts/groups are created.
UID996 is included only in denial probes. No production policy, catalog, history,
operational journal, container, systemd unit or provider credential is selected.

`curated_host_package.py` builds a committed-source/offline-vendor package. Its
emitted stdlib bootstrap verifies exact manifest/member hashes before protected
staging and evaluation, checks the resolved native interpreter, creates a new
root-owned immutable release, and runs the bounded controller. Existing release
or fixture scope refuses. Do not repeat a failed run or delete evidence blindly.

The root controller creates a root-private source sentinel, service-owned private
synthetic SQLite history/catalog and runtime, reader-owned context directory and
root-protected fixture policy. Existing bounded child/start/stop machinery is
reused with an explicitly replaced scope and role map. Each child has a private
network namespace, no supplementary groups/capabilities, no-new-privileges and a
minimal provider-free environment. No source from an unprotected handoff is run.

The service loads exact read-only UID/repository policy and uses the existing
per-UID ACL implementation on its runtime directory/socket before listen. A service
self-reader grant is used only for internal readiness across reader revocation.
The external reader receives only example_library. Synthetic other_repo content
exists to exercise authorization; private source prose is never copied into the
selected curated entries.

Required case groups:

1. Actual distinct-UID search and exact current-generation entry read.
2. Other repository and all private/history/document/writer/action routes denied.
3. Reader, unknown identity and worker denied direct private files; unknown/worker
   denied socket access.
4. Service denied root-private source material.
5. Synthetic private source prose excluded from curated retrieval.
6. Actual identity/network/group/capability/provider-environment boundaries.
7. Withdrawal removes current matches and refuses old cursors/entry reads.
8. Service restart retains withdrawal.
9. Restart with revised fixture policy replaces ACLs and removes old reader access.

The controller verifies root source and private-history DB hashes unchanged and
requires tracked service shutdown plus socket removal. It retains root-private
child diagnostics and completion/failure evidence. Failure never invokes production
recovery, automatic retry, coding or publication. The final success result is emitted
only after actual host execution; source tests are adapters/packaging evidence.

This fixture does not choose a production service identity, install a reader or
publish real content to Jarvis. Those remain separately reviewed concrete steps.
Browser authentication D2 remains open and independent.
