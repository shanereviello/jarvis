# Isolated managed-history export/handoff acceptance

PR51 provides the passive bridge source. This separate fixture tests actual root
source custody and distinct-UID receipt delivery before any production export or
import is proposed. It does not install an exporter, timer or history runtime.

One fresh scope is frozen in `managed_host_package.py`:

- Evidence `/var/lib/rras-history-managed-link-acceptance-20261024`.
- Numeric service UID/GID61101, importer61102, unknown61103; actual worker996
  denial is checked too. No NSS accounts or shared groups are created or adopted.
- Root-owned hash-pinned release under
  `/opt/rras-engineering/releases/history-managed-host-<manifest-prefix>`.
- Synthetic operational journal and artifact only, seeded from committed examples.

The stdlib bootstrap verifies every byte before copying a root-owned read-only
release. The root stdlib driver controls only this fixture. Seed/export subprocesses
retain UID0 to read their root-private synthetic journal, but execute with no
capabilities, no supplementary groups, no-new-privileges, a private network namespace
and an explicit credential-free environment. Schema/dependency imports in those
subprocesses come only from the pinned protected release/vendor. No user-owned code
is imported as root. The synthetic seed does write its own journal; the actual
exporter opens it read-only. The final check compares source DB bytes after seed
against the bytes after all exports/delivery/restarts.

Root-private exports are handed off as exact bytes into an importer-owned0700
input directory with600 files, while their root originals remain private. Importer
UID61102 cannot read the journal, history database or policy. Unknown61103/worker996
cannot read the packet or connect to the fixture history socket. The history service
runs as61101 with exact per-UID ACLs through the production entry point. All client
processes use private network namespaces, no supplementary groups and no caps.
This process fixture does not retest the already accepted production systemd unit.

Acceptance exercises two source pages, deliberate loss of a response after commit,
no cursor advance on that loss, service restart/recovery, second-page cursor
chaining, another restart and exact-receipt replay without duplicate records. Source
observed provenance must remain imported/no-authority in the destination receipt.
No synthetic fixture content is imported into production history.

Success stops the fixture service and removes its own socket, while retaining
private evidence/databases and the pinned release. Failure preserves evidence and
stops only the fixture service; no automatic retry or production recovery occurs.
Existing scope/release/identity collisions refuse before proceeding. A stage timeout
terminates the driver; child parent-death signals and scoped cleanup bound leftovers.
No systemctl/useradd/groupadd/Docker/provider command is used.

Offline checks establish payload guards, role/identity mapping, shared state paths
and synthetic SQLite role logic only. The actual sudo result is still required for
root/DAC/network/cross-UID acceptance. No production journal, history rows, accounts,
configuration or services are touched by this procedure. The later production
export/handoff and explicit task mapping/import need their own concrete review.
