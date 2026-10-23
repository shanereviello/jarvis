# Actual hardened-unit and per-UID ACL acceptance

This source prepares an isolated operator-run test of the
[production blueprint](engineering-history-production-package.md). Its actual sudo
result is pending. Earlier shared-group and same-UID tests do not establish this
new systemd/ACL boundary. No production service/account is installed here.

## Exact fixture resources

- Fresh state: `/var/lib/rras-history-unit-acceptance-20261022`.
- Protected code: `/opt/rras-engineering/releases/history-unit-acceptance-<pin>`.
- Runtime: `/run/rras-history-unit-acceptance-20261022`.
- Only controlled unit: `rras-history-unit-acceptance-20261022.service`.
- Temporary runtime unit file: `/run/systemd/system/rras-history-unit-acceptance-20261022.service`.
- Numeric service UID/GID61081; client61082/61083, reader61085 and unknown61084;
  existing operatorUID1000 and worker/control996/997 participate in fixed probes.

There are no account/group database writes. Each caller uses its own primary GID
with cleared supplementary groups. The service may retain only its private primary
group in its group list. No caller shares the service group. Root preflight checks
reserved identity collisions, protected tools/paths, existing unit and all fresh
fixture destinations. Existing evidence or units refuse; no automatic retry.

The manifest pins a nested runtime package and all additional stdlib orchestration
and unprivileged probe bytes. The root bootstrap validates and snapshots every file
before copying into root-owned read-only custody. Third-party history dependencies
load only in unprivileged processes. The privileged orchestrator independently
revalidates the nested runtime manifest and generated deployment artifacts.

## Production profile and scoped substitutions

The fixture derives its unit from the actual generated production unit. It changes
only the numeric identity, protected fixture release, store/policy/runtime paths,
conditions and runtime directory name. It supplies explicit fixture CLI arguments
to the unchanged production entry. Every production hardening/resource directive
remains. It adds a fixed `ExecStartPost` probe, a25-second startup bound and180-second
maximum active lifetime, and removes the install-target section so it cannot be
enabled as a persistent deployment through this fixture.

The lifetime cap bounds a test service even if its root controller is killed. The
controller's start/stop calls always name the fixed fixture unit; it never controls
the production history unit, coding unit, Hermes or containers. It loads the one
fresh runtime unit with daemon-reload. Success stops the fixture, removes only its
matching hashed runtime unit file and reloads manager configuration; no production
unit is restarted or enabled. The original fixture unit bytes, logs, store, spools
and preserved runtime directory remain evidence. Failure stops the fixture when
possible and retains its runtime unit/evidence for inspection.

## Cases and actual observations required

The production initializer first creates an empty synthetic store under the service
UID. A caller queues work while no socket exists. The actual hardened service then
starts, applies exact ACLs before listen, and recovers the queued work/session.
UID1000 must read through the socket despite having no shared group or session
membership change. Receipt writer and peer IDs must be the real distinct UIDs.

Inside the actual unit, the fixed post-start probe checks no new privileges and
zero capabilities, a writable private store, an EROFS refusal for a synthetic file
that ordinary DAC permissions would allow writing, INET socket refusal, hidden
non-process procfs entries and protected PID1 metadata. Root independently verifies
the main process's identity/capabilities and distinct network namespace. The probe
creates only a private synthetic scratch file; it never sends network traffic.

Further cases require:

- Distinct repository grants; unknown/worker/control and private-reader write refusal.
- Actual direct database/policy/root-sentinel/source denial, including UID1000.
  Missing fixture files cannot count as access-denial proof.
- Actual-unit immutable review rendering and exact Markdown hash retrieval; no
  cross-repository document access or execution route.
- Clean unit stop/restart with the original durable replay receipt and no duplicate.
- A controlled fixture-only policy revocation, then restart. The revoked client's
  old named ACL entries must disappear from both runtime directory and socket;
  replay must refuse while UID1000 can still read the retained records.
- Final process stop, socket removal and removal of the exact fixture runtime unit.

Readiness uses bounded read-only history requests; writes are never retried to make
startup appear ready. Planned successful restart/revocation cases are distinct from
a failure retry: any unexpected error stops acceptance and preserves evidence.

## Diagnostics and source validation

Private root logs contain bounded child stdout/stderr and the fixture unit journal.
Failure output releases only exception types and code frame metadata. Structured
probe-error metadata can be selected from that private journal; raw journal messages,
policy content and narrative payloads are not emitted as diagnostic output. New
attempts require a separately pinned fresh fixture after evidence review.

Offline tests cover nested manifest/runtime bindings, immutable source/artifacts,
unsafe paths and hard links/symlinks, unchanged production hardening, scoped unit
commands, private group construction, refusal without sudo and file-denial semantics.
Generated fixture syntax passed installed systemd249 verification with returncode0;
existing unrelated netplan/snapd warnings were observed. These checks are not an
actual privileged unit result.

The success contract is `isolated_history_hardened_unit_verified`. Only that reviewed
operator-run result can satisfy this unit/ACL gate. Encrypted consistent backup and
isolated restore remain next, followed by explicit inactive installation and live
activation decisions. No real credentials, paid API call, automatic interactive
capture, root operational export or public listener is part of this test.
