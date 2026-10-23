# Isolated cross-UID engineering-history acceptance

This source prepares an operator-run fixture for the
[Unix history transport](engineering-history-unix-transport.md). It is not a
production installer. The reviewed attempt02 returned
`isolated_history_cross_uid_verified`; production installation remains a separate
explicit decision.

## Scope and custody

The packager snapshots the explicit history source/schema/template allowlist plus
vendored contract-validation dependencies into a bounded candidate (at most256 files,
8MiB total). Each file and the canonical manifest have SHA256 bindings. Verification
refuses changed bytes, duplicate manifest keys, traversal, symlinks, hard links,
bytecode and executable path-injection files. It never downloads dependencies.

An emitted stdlib-only bootstrap verifies the exact manifest pin and copies the
verified bytes into a new root-owned read-only acceptance release before executing
privileged fixture orchestration. Root imports no history library or third-party
validation dependency. Those imports occur only in the dropped-privilege children.
The existing protected Python3.13 interpreter is reused without modifying it.

The preserved first attempt used `/var/lib/rras-history-acceptance-20261022` and
`/opt/rras-engineering/releases/history-acceptance-<manifest-prefix>`. A new reviewed attempt uses `/var/lib/rras-history-acceptance-attempt02-20261022`
and its new manifest-derived release. Both destinations had to be absent before
execution. Any existing path causes refusal, including an earlier failed attempt; no
automatic retry, overwrite or deletion. Retain synthetic fixture evidence and the
protected payload for inspection after either success or failure.

## Distinct identities without account changes

The fixture uses numeric identities only; it creates no passwd/group entries:

| Identity | UID | Role |
| --- | --- | --- |
| History fixture service | 61081 | Own private fixture database |
| Client A | 61082 | Private read/write for `example` |
| Client B | 61083 | Private read/write for `other` |
| Unknown client | 61084 | Connection opportunity, no policy grant |
| Private reader | 61085 | Private read for `example`, no writes |
| Existing worker/control roles | 996/997 | Explicit refusal tests only |
| Existing operator account | 1000 | Fixture database/policy denial only |

GID61080 supplies fixture socket traversal/connect access. The service uses primary
GID61081 and supplementary GID61080; other children have only the shared fixture
GID. The root-owned policy is0640:GID61081, so socket clients cannot read or edit it.
The store is0700:UID61081; client spools are separate0700 directories. The runtime
folder is setgid2750:61081:61080 so the service-created0660 socket inherits the
admitted connection group. Repository authorization is still checked per call.

The administrator preflight refuses if proposed numeric UIDs/GIDs are allocated or
active in `/proc`. This is an isolated acceptance reservation, not approval to use
these identities for the later production service. UID996/997 probes run only the
fixed protected fixture code, never the production task unit or coding launcher.

## Actual child boundaries and cases

Each child is launched by `unshare --net` then `setpriv` with explicit UID/GID/groups,
no new privileges and empty capability sets. Its environment contains only a fixed
PATH, nonexistent HOME and locale. Each child verifies its actual kernel identity,
capabilities, no-new-privileges flag, loopback-only network namespace and empty
route table. No real credential is opened. A parent-death signal and bounded root
orchestration cleanup keep the fixture service tied to the acceptance invocation.

The acceptance checks:

- Offline client work/session requests persist, then flush through the real service.
- Real service writer UID differs from the authenticated client peer UID.
- Restart and replay return the original receipt without duplicate records.
- Two repository grants isolate read/write access; a private reader cannot submit.
- Unknown, UID996 and UID997 callers are refused despite fixture socket access.
- Actual OS denial protects the fixture database, root-only synthetic sentinel,
  policy and immutable source from clients, workers and UID1000.
- Synthetic rendered review bytes match the stored manifest digest; the other
  repository cannot retrieve them; no execution route exists.
- Oversized/incomplete frames refuse or hit the wire deadline, and the service
  recovers for the next legitimate read.
- The service exits normally and removes its own socket at completion. Store,
  spools, logs and protected release remain as synthetic evidence.

A success record is `isolated_history_cross_uid_verified`. Failures preserve private
root diagnostics and bounded child stdout/stderr, stop the fixture service and emit
a generic refusal. Forced stop or uncertain cleanup cannot report success. The
bootstrap grants cleanup time on orchestration timeout; service children also arm
parent-death termination. A crash may retain evidence, including a stale endpoint;
never erase it merely to make a retry pass.

## Validation and subsequent gate

Unprivileged tests cover deterministic packaging, exact file/manifest hashes,
malformed/corrupted paths/files, self-contained helper refusal without sudo, isolated
fixture path checks and privilege-drop command construction. They do not establish
cross-UID runtime behavior. The full existing history suite independently verifies
contracts, storage, client queues, policy and actual same-UID Unix transport.

The actual sudo fixture succeeded with the evidence below. Merge the acceptance
source separately. Then prepare the concrete production account, protected
release/store/policy, hardened service unit and rollback plan for an explicit
installation decision. Production Hermes, coding tasks, operational journal,
credentials, containers and existing service units are untouched by this fixture.
No GUI, hook, curated Jarvis narrative publication, root operational exporter or
paid coding run is authorized by source merge or acceptance.


## First host attempt diagnostic and corrected route check

The first privileged fixture stopped in its initial child, before database creation
or service startup. A separate read-only diagnostic observed the intended UID/GID,
no-new-privileges, zero capabilities, loopback-only interface and zero IPv4 route
lines. Imports and file metadata checks passed. The failure was the probe's
assumption that an empty `/proc/net/route` always retains a header line.

The corrected check accepts an empty/blank file or exactly the recognized Linux
header, and rejects every route row, duplicate header and unrecognized content.
Regression cases cover both empty formats and real route-row refusal. The network
isolation requirement is unchanged. Attempt02 uses a fresh pinned payload and state
directory; the original fixture/release and diagnostic remain preserved. The
corrected attempt succeeded as recorded below.


## Verified attempt02 evidence

The operator-run pinned procedure returned `isolated_history_cross_uid_verified`:

- Tested source: `b43d7c55c32a9c49cd46634b7859f28de7bfb013`.
- Payload manifest: `27f6fb9c42c62a093f07082b493ff53c2f2322c105a7570ecf30e8eff3628189`.
- Protected acceptance release:
  `/opt/rras-engineering/releases/history-acceptance-27f6fb9c42c6`.
- Synthetic state/evidence:
  `/var/lib/rras-history-acceptance-attempt02-20261022`.
- Service UID61081 and client UIDs61082/61083 exercised distinct kernel principals.
- All nine reported case groups passed: offline queue recovery, distinct identities,
  isolated network/capabilities/environment, restart/replay, repository isolation,
  unknown/worker/control and read-only grants, actual OS file denial, immutable
  private documents/no action route, and frame/deadline recovery.
- Fixture service stopped normally and its socket was removed. The report records
  zero API calls, no real credentials, no permanent account creation and no production
  configuration/journal/service changes. No automatic retry occurred.

These observations establish the isolated tested boundary. They do not establish
an installed production account/service, production policy, automatic interactive
capture, root export, curated narrative access or browser controls. Documentation
updates after the tested source commit do not change the pinned acceptance payload.
The preceding32 unprivileged packaging/route regression cases also passed.
