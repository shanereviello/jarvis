# Engineering-history production installation blueprint

This source builds and verifies an **inactive package**, not an installed service.
The [cross-UID fixture](engineering-history-host-acceptance.md#verified-attempt02-evidence)
passed. This package adds a production entry, exact socket ACL setup and a hardened
unit that still need their own isolated unit/ACL host acceptance. Nothing here
creates accounts, modifies systemd, initializes production history or authorizes
activation. Backup/restore verification remains a pre-activation gate.

## Concrete resource plan

| Resource | Proposed custody and behavior |
| --- | --- |
| Account/group | New `rras-history` system identity, unused UID distinct from root,996,997,1000; private primary group, nologin shell, nonexistent home, no supplementary client/Docker/sudo groups. Allocate only after approved install preflight. |
| Runtime | `/opt/rras-engineering/releases/history-<payload-digest-prefix>`; root-owned directories0755/files0444, vendored pinned dependencies, templates and schema. |
| Store | `/var/lib/rras-engineering-history`; service-owned0700, SQLite0600. Initially empty; no acceptance records or existing operational database copied. |
| Policy | `/etc/rras-engineering-history/access-policy.json`; root:service0640 in root:service0750 directory. Service reads, never edits policy. |
| Socket | `/run/rras-engineering-history/service.sock`; service-owned directory, exact per-UID access described below. No TCP/browser port. |
| Unit | `/etc/systemd/system/rras-engineering-history.service`; root0644, inactive/disabled after a separately approved stage. |
| Client | `/usr/local/bin/rras-history-client`; root0755 wrapper pinned to the exact release and protected interpreter. Caller spool remains private and explicit. |
| Install evidence | `/var/lib/rras-history-installations/history-<payload-id>`; root-private inventory, hashes, preflight/stage results and subsequent decisions, to be implemented by reviewed install tooling. |

Read-only host inspection found the account/group and proposed service paths absent.
It found `/usr/bin/setfacl` and systemd249 available. The install preflight must repeat
collision/custody checks immediately before any mutation. Existing paths/accounts
must not be silently adopted or overwritten. No existing user's groups change.

The initial private policy grants UID1000 read/write for engineering repository IDs
`jarvis` and `robot_ws`. Those grants concern passive narrative records, not managed
execution admission or filesystem/Git access. The service never opens either Git
checkout. Future attached repositories need explicit reviewed policy grants; their
IDs use the existing generic contract. No Jarvis/Hermes identity receives private
narrative access here. Curated sharing remains a separate implementation.

## Exact local access without session group changes

The production entry runs under the dedicated service identity and reduces its
environment to PATH, nonexistent HOME and locale before loading the history runtime.
It refuses root,996,997 and interactive UID1000 as the service owner. An explicit
numeric account option exists for later protected acceptance fixtures; the production
unit selects the named dedicated account.

At startup it validates protected policy and opens the existing store. The server
binds its new socket, then applies filesystem ACLs **before listen**:

- Runtime directory: service-owner `rwx`; each private-read principal receives
  traverse-only `--x`; group/others have no access; stale default ACLs are removed.
- Socket: service-owner `rw`; each admitted principal receives `rw`; group/others
  have no access. Replace the full ACL rather than adding entries to an old policy.

The fixed `/usr/bin/setfacl` command runs without a shell as the unprivileged file
owner. It has bounded arguments/time and uses only validated numeric policy UIDs.
The target must be a canonical service-owned directory/socket with unchanged inode.
No user-selected executable or path comes through requests. A failed ACL setup
refuses startup and removes only that instance's new socket. All repository grants
are independently rechecked after kernel peer authentication; filesystem ACLs do
not authorize a repository or human decision.

This gives the existing UID1000 desktop/shell session access without login refresh
or adding the service to the user's groups. Revocation requires a reviewed policy
change and stop/restart; exact ACL replacement removes old named/default entries.
An existing/stale socket still prevents startup. Never delete it automatically to
make a restart pass.

## Hardened service and client bootstrap

The unit pins its exact release and existing protected Python3.13 interpreter. It
uses a private network namespace, AF_UNIX-only sockets, empty capabilities, no new
privileges, a read-only system/home boundary, limited writable store/runtime paths,
private tmp/devices, kernel/control-group protections, syscall/resource limits and
explicitly inaccessible root workflow/control/task/credential/Docker paths. No
credential directive or paid-coding launcher is present. The production entry also
clears inherited manager environment values; the unit's explicit unsets alone are
not treated as a complete credential filter.

`Restart=no` leaves failures visible. `RuntimeDirectoryPreserve=yes` retains crash
or stale-endpoint evidence; normal server cleanup removes its own socket. Stop kills
the unit's control group with a15-second bound. Initialization is a separate explicit
`initialize-empty` command under the dedicated UID; normal unit startup requires an
existing database and never creates one automatically.

The client wrapper adds this release's vendored dependencies before entering the
existing interactive CLI. `init` still requires an explicit socket, expected service
UID and caller-owned0700 state. Existing spools retain their fixed transport and
receipts. No transcript scraping, hook or automatic session selection is installed.
A source merge or inactive stage does not mean current Codex work is being recorded.

## Package identity and verification

`production_package.py` snapshots a minimal runtime allowlist plus offline vendored
dependencies. Acceptance orchestrators/probes are omitted. Payload file hashes form
a digest that selects the release path. Generated unit/policy/plan/client wrapper/
rollback artifacts then bind that path. The final external manifest digest binds
all bytes, avoiding a self-referential hash. Unknown/traversal/symlink/hardlink paths,
changed bytes, noncanonical manifests, missing files or oversized packages refuse.

Verification independently recomputes payload identity and expected deployment
artifacts. Rehashing an edited unit/policy/plan/wrapper into a changed manifest cannot
silently change this blueprint. Both staging and activation authorization remain
false. No package command writes outside its fresh output directory.

The generated unit passed installed `systemd-analyze verify` with returncode0; the
host also emitted unrelated existing netplan/snapd unit warnings. This establishes
unit syntax/directive compatibility, not successful runtime hardening or ACL access.
Disposable tests exercised real ACL replacement before listen, stale/default grant
removal, refusal cleanup, exact artifact/identity guards and environment filtering.
Actual separate-UID hardened-unit behavior remains the following host gate.

## Installation, retention and rollback sequence

1. Separate source merge, then prepare a protected isolated acceptance using the
   actual hardened unit, ACLs, distinct UIDs and restart/refusal checks. Do not infer
   this new boundary from the earlier shared-group fixture.
2. Implement consistent encrypted backup and isolated restore checks for history
   bytes/receipts/grants/schema/templates before retaining real engineering content.
   Select encryption custody and any off-host destination/retention/RPO/RTO with the
   operator; none is silently promised by this package.
3. Present exact inactive staging tooling and inventory for explicit installation
   approval: allocate the dedicated identity, copy protected release/config/unit/
   wrapper, initialize only an empty store as service UID, leave unit disabled/stopped.
   Keep a protected mutation journal; refuse collisions and preserve partial failures.
4. Present live preflight/acceptance and backup readiness for a separate activation
   decision. Start only the additive history unit, verify actual UID1000 client
   access and worker denial, then enable at boot only under that same explicit plan.
5. Connect an explicit interactive client and approved current/retrospective work.
   No synthetic acceptance fixture is imported into production history.

The included rollback is disable-only: stop/disable this history unit, verify it
exited, retain account/store/policy/release/runtime evidence and spools. Do not restore
an older database over later records, delete pending delivery, reuse service UIDs or
modify the existing managed workflow. A future downgrade/upgrade needs its own
compatibility and exact-state plan. GUI, web authentication, root export and curated
Jarvis narrative publication remain later roadmap items.
