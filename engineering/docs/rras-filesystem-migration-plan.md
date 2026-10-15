# RRAS filesystem consolidation — review before execution

Prepared 2026-10-12 for server01. **This is a plan, not authorization to move files, commit/merge, recreate containers, migrate databases or delete directories.** Only this document was created in this pass. PostgreSQL consolidation and centralized backups are explicitly deferred.

## End state

One human-controlled source repository for Jarvis tooling, one for robot software; reviewed installed software under /opt; credentials under /etc; worker copies/evidence under /var/lib. No coding worker writes the canonical repository, live installed code or Docker configuration. Human review controls merges and deployment.

```text
/srv/git/jarvis/                         Canonical Jarvis tooling source
  app/, scripts/, tests/                 Existing MCP application; preserve imports
  activity-ledger/                        Ledger code, schema and deployment sources
  engineering/                           Native RRAS runner/tools/tests/docs
  deploy/                                Host/container deployment definitions
  config/examples/                       Secret-free configuration templates
  docs/                                  Architecture, migration and operator guides
/srv/git/robot_ws/                       Canonical robot software; unchanged

/opt/jarvis/releases/<reviewed-release>/  Root-owned MCP and ledger installed assets
/opt/jarvis/current                      Operator-selected release pointer
/opt/hermes/                             Existing assistant installation; tracked Compose source
/opt/rras-engineering/releases/native-10/ Existing pinned Hermes/Codex runtime; retain initially
/opt/rras-engineering/rras-releases/<id>/ Reviewed RRAS runner code; separate from vendor runtime

/etc/jarvis/mcp/runtime.env              Protected MCP runtime configuration
/etc/jarvis/hermes/runtime.env           Protected assistant configuration if required
/etc/jarvis/activity/secrets/            Ledger passwords and API tokens
/etc/rras-engineering/credentials/       Dedicated engineering API credential

/var/lib/rras-engineering/repos/jarvis/   Worker-owned execution clone
/var/lib/rras-engineering/repos/robot_ws/ Worker-owned execution clone
                                        Native .worktrees reside in these copies
/var/lib/rras-engineering/runs/<run-id>/  Private task context, board, logs and evidence
/var/lib/jarvis/activity/legacy-state/   Temporary compatibility state only if still required
```

Keep unchanged: `/srv/hermes/data`, `/srv/jarvis/audit`, notes/shared/n8n application data, PostgreSQL volumes, `/srv/postgres/data`, current backup locations until their consumers are known. Existing acceptance directories under `/var/lib/rras-engineering` need not be renamed to achieve this layout. Their immutable references remain valid.

New /etc service directories and secret files: root-owned 0700/0600; runtime access via reviewed container secret mounts or systemd LoadCredential, not worker-readable parent directories. New /opt release directories: root-owned, no group/other write; no blanket recursive ownership changes to existing /opt or /srv. Canonical Git repositories remain human-controlled. Worker repo/run directories: dedicated UID/GID996, private ancestors/0700. Retain existing dedicated account/no supplementary groups/no sudo or Docker access.

## Verified starting facts

| Item | Verified condition / consequence |
|---|---|
| `/srv/git/jarvis` | Clean main at `ec591178ed5c2813da4f1a3252a0ecf290f19b36` |
| `/srv/git/robot_ws` | Clean master at `67b150469921c1c08317a71fe56f33ad9eb17cbd` |
| `/opt/jarvis` | Same committed Jarvis revision **but five modified and two new entries** not in the canonical checkout; preserve deployed custom work before any rebuild |
| Current development repository | `/srv/hermes-dev/jarvis/tasks/TASK-20260916-001-central-codex-activity-prototype/repo`, phase5b/guarded-host-orchestration, HEAD `f0d8a6eaf016153708c3e46a32e204a93bd11a97`; independent Git root history, no remote, substantial uncommitted work. Import selected source; do not merge unrelated histories or copy its .git into Jarvis |
| Old Hermes baselines | Published file snapshots, not Git repos; approval markers match canonical commits above, contents not independently byte-compared here |
| Old Hermes task repos | Independent clones; robot create-task script explicitly avoids worktrees |
| Running Hermes | Compose `/opt/hermes/compose.yaml`; mounts both old baselines/task roots and canonical repos read-only |
| Running MCP services | `jarvis-mcp` **and** `linear-action-mcp`, Compose `/opt/jarvis/compose.yml`; audit/notes and Linear bridge secret are active dependencies |
| Ledger | Running dedicated `jarvis-activity-jarvis-activity-postgres-1` and adapter; Compose paths, DB init and migrations still reference the development repo |
| Ledger data | Docker volume `jarvis-activity_jarvis_activity_pgdata`; separate from engineering-postgres and Honcho PostgreSQL. Never rename/recreate/delete it as part of path cleanup |
| Legacy reconciliation | jarvis-codex-reconcile.service inactive/dead; timer disabled. Keep that condition until separately reviewed retirement |
| New workflow | Paid canary `bd70070307cb45dd8ccc9890c888afef` passed; generic runner host acceptance `592ceb6681574b8cabf3411559831273` passed six model-free cases. Preserve their evidence at existing paths |

Deployed /opt/jarvis changes needing import: `app/core/config.py`, `app/servers/mcp/registry.py`, `app/servers/mcp/server.py`, `app/tools/__init__.py`, `compose.yml`, new `app/services/linear_gateway.py` and `app/tools/linear_actions.py`.

## Exact source and operational mapping

| From | To | Treatment |
|---|---|---|
| `/opt/jarvis` application changes listed above | Same relative paths in a review branch of `/srv/git/jarvis` | Review diff/import; preserve existing Python layout initially |
| `/opt/jarvis/compose.yml` | `/srv/git/jarvis/deploy/mcp/compose.yml` | Track sanitized definition; adapt build context explicitly, preserve both services |
| `/opt/hermes/compose.yaml` | `/srv/git/jarvis/deploy/hermes/compose.yaml` | Track sanitized definition; installed copy stays under /opt/hermes |
| Development repo `adapter/`, `src/`, `db/`, relevant ledger dependencies/tests | `/srv/git/jarvis/activity-ledger/` preserving relative paths | Import closure required by the running adapter; shared ledger code is not disposable merely because it lives beside old executors |
| Development repo `deploy/jarvis-activity/` | `/srv/git/jarvis/activity-ledger/deploy/jarvis-activity/` | Preserve relative build/migration paths initially; then reviewed operational Compose without old executor services |
| Development repo `tools/rras_native/` | `/srv/git/jarvis/engineering/tools/rras_native/` | Select manual_runner, native_task_cli, activity, wait_worker, credential loader dependency, relevant install/preparation/probes; exclude caches. Review dependency closure before dropping helpers |
| Native tests / current RRAS docs | `/srv/git/jarvis/engineering/tests/` and `engineering/docs/` | Preserve working relative tool links and test roots; fix any absolute historical execution references only in new procedures |
| `/opt/jarvis/.env` | `/etc/jarvis/mcp/runtime.env` | Protected copy, byte-equivalence verification without printing contents; never Git. Do not copy .aws/.codex/.agents into source or installed releases |
| `/srv/jarvis-activity/secrets/*` | `/etc/jarvis/activity/secrets/<same filename>` | Copy existing required credentials, no rotation or role expansion; update mounts only after verification |
| Engineering key in `/etc/rras-canary-credentials-20261012-01/openai_api_key` | `/etc/rras-engineering/credentials/openai_api_key` | Protected copy and equality check; retain old source until launchers use new path. Original /srv/jarvis-codex key then becomes removable after dependency clearance |
| `/srv/jarvis-activity/runner-state` | No permanent new-workflow home | Retire old controller/executor mounts only after route/consumer audit. If adapter still needs them temporarily, copy to `/var/lib/jarvis/activity/legacy-state` and preserve container-side paths; this is explicitly transitional |
| `/srv/jarvis-activity/backups` | Remains at current path in this pass | Backup consolidation deferred. Therefore the top directory may remain solely for backups after execution-state cleanup |
| `/srv/hermes-dev`, `/srv/jarvis-codex` | Retire after gates below | Current implementation extracted first; private verified rollback snapshot before deletion. No permanent duplicate legacy workflow |

Third-party runtimes are reproducible through version/checksum pins and installer instructions, not by committing virtualenvs, caches or downloaded binaries. Include custom operator/install/deployment code in Git. Other stack definitions under /opt/cloudflared, /opt/n8n, /opt/hindsight, /opt/honcho and /opt/postgres can be imported as sanitized deployment sources in a later source-only batch; do not relocate/recreate those stacks in this migration.

## Ordered execution slices and stop gates

### 1 — Freeze inventory and capture rollback material; no outages

Produce an administrator-only migration journal with a unique ID and protected off-host backup destination. Record Git HEAD/branches/status, preserve committed histories and working/untracked content separately, and verify restoration into an isolated temporary directory. A Git bundle alone does **not** capture uncommitted work. Do not commit secret/runtime snapshots to Git. Keep source/editing stable during snapshot creation; record and stop if hashes change.

Record every targeted container's name, Compose project/service/source files, exact installed image configuration ID, mounts, network membership, aliases, ports and existing health/read-only checks. Render configurations privately and emit only sanitized structural comparisons/hashes, never environment/secret values. Record local systemd units/drop-ins, backup/cron references and metadata without credential contents. Root crontabs/protected runner homes remain an inventory gap until administrator inspection; no claim they are unused.

**Pass:** independent restore of source snapshots; required secrets/data backups exist privately; all affected consumers listed; canonical clean HEADs unchanged. **Stop:** unreadable required state, missing backup destination, unexplained consumer or changing source. Nothing else moves before this passes.

### 2 — Consolidate source in an isolated review checkout; no deployment

Use branch `codex/filesystem-consolidation-20261012` in a new human-owned review checkout, not the live /opt checkout or current dirty development clone. Base it on canonical Jarvis main. Import deployed MCP modifications first, then selected ledger/native components by the mapping above. Treat the development repository as a donor of reviewed files, not mergeable Jarvis ancestry. Keep old Phase5B history in the rollback capture; user does not require maintaining its tooling long-term.

Explicitly enumerate source files and dependencies; exclude secrets, .env, auth directories, live DB files, task state, caches, virtualenvs and binaries. Sanitize Compose configurations and provide templates/placeholders for credentials. Adjust Docker build contexts and Python/test imports based on the new package location. No opportunistic code/provider/database upgrades or schema migrations.

**Pass:** MCP/Linear focused tests, ledger/adapter focused tests, native runner regressions and isolated model-free fixtures; no secret-bearing staged candidate; deployment definitions structurally equivalent except reviewed paths/legacy removals. Review exact diff and installed-drift import. **Approval:** human approves source merge/commit and any remote push separately; this plan does not authorize them. **Rollback:** discard only the new review candidate if rejected; live files never changed.

### 3 — Publish new root-owned release candidates and protected config copies; no cutover

After source review, create an absent-only `/opt/jarvis/releases/<release-id>` and `/opt/rras-engineering/rras-releases/<release-id>`, with file manifests linking reviewed source revision and artifact hashes. Retain current native-10 vendor runtime, including the exact Python path native_task_cli currently admits; changing it requires a separate compatibility update/test. Do not overwrite /opt/jarvis's existing live Git checkout.

Copy—not move—required config/credentials into the /etc paths above. Preserve bytes and verify private ownership/modes without printing them. Do not make worker repos or the worker UID members of Docker/sudo groups. Do not rotate credentials or expand database grants.

**Pass:** root-owned release/ancestor checks, manifest verification, offline configuration validation, credential-free installed runner fixture, exact credential-copy checks, no activation. **Rollback:** old code/config remains authoritative; quarantine new candidate if partial publication fails rather than overwriting it on retry. A fresh review ID resolves collisions.

### 4 — Establish worker copies and prove the human merge boundary; no paid task

Create private execution clones from approved `/srv/git/jarvis` and `/srv/git/robot_ws` commits under `/var/lib/rras-engineering/repos`. Use independent Git objects (`--no-hardlinks`) and remove publication remotes; do not copy personal Git/Codex auth. Native worktrees must derive from these execution copies, not canonical /srv/git metadata. Registered repo IDs map to these worker paths. Synchronizing new approved baselines is an operator-controlled step; record the canonical source path/SHA in admission.

**Pass:** engineering UID can read admitted source and write only its own copy/worktrees; cannot write canonical files or .git, installed releases, secret sources or Docker socket. Model-free dispatch/context/completion/validation/export works after source relocation; dirty baselines, wrong repo/run and forbidden paths are rejected. No global write arbitration is claimed: operator serializes tasks until shared intake is installed.

**Rollback:** stop the exact disposable unit before abandoning new copies; keep evidence and branches. Canonical repos remain untouched. A real model task still requires a concrete reviewed request and separate paid authorization.

### 5 — Relocate active deployment references, one service group at a time

Use unchanged Compose project identities: `jarvis`, `hermes`, `jarvis-activity`. Inventory shows jarvis-mcp and linear-action-mcp currently use **different image IDs** despite shared source definition; preserve each service's actual image initially. Hermes uses a latest tag; do not pull it. Pin relocation candidates to recorded locally installed configuration IDs, with pull/build disabled; these IDs are not newly approved registry-distribution digests. Version upgrades/rebuilds are a separate reviewed deployment.

**5A MCP/Linear:** retain current service names, ports, networks, notes mounts, audit path and Linear bridge secret mount initially. Adapt deployed source/Compose locations and runtime.env reference. Controlled recreate only the affected application services during an agreed interruption window. Check startup plus existing harmless MCP/Linear health/read behavior; no issue creation, message sending or other irreversible smoke-test actions. Preserve both previous images and old environment source for rollback.

**5B Hermes:** remove `/srv/hermes-dev/*` mounts only once its configured tools/prompts no longer reference those paths. Keep `/srv/hermes/data`, notes/shared paths and canonical repository mounts read-only. Do not mount the private engineering worker area wholesale into Hermes. Shared Jarvis intake is unfinished; until its narrow interface exists, Hermes cannot silently resume engineering via old task scripts. Ordinary assistant functionality stays available; engineering jobs use the manual runner. Check assistant startup/profile/tool availability and a credential-free engineering path separately, no model-backed smoke test inferred.

**5C ledger adapter:** relocate secrets/source definitions, audit legacy endpoint consumers and remove old controller/executor capability only after confirming no active client depends on it. Until then use the transitional state mapping. Check adapter readiness and existing permitted read-only ledger operations without schema/grant changes. Preserve adapter image identity and current API behavior unless separately reviewed.

**5D ledger PostgreSQL source mounts:** DB init/migration bind sources must eventually point into the installed ledger release. Changing an existing container's mount definitions requires controlled recreation of that database container. This is **not** a data migration, but is a brief database outage: require the current backup/restore procedure and an operator maintenance window first. Reuse exact existing image, project/service/network aliases and `jarvis-activity_jarvis_activity_pgdata`; declare that volume external with its exact name. Never run init/migrate services, down -v, volume prune or change ports. Do not touch engineering-postgres or Honcho database containers. If a DB interruption is not approved, stop this substep and retain the old read-only mount-source directories; legacy deletion must wait.

**Pass each substep:** all expected container identities/mounts/health and functional read checks match; unrelated stacks unchanged; no missing ledger records; old paths absent from that service's active references. **Rollback each substep:** recreate only the changed service with its previously recorded Compose, image ID, mounts, network/ports and old config source. Existing data volume remains attached. Do not rely on a symlink switch alone: running containers retain their prior mounts and Compose labels until recreated. No database rollback through schema reversal is needed because schemas never change.

### 6 — Remove legacy execution machinery after verified disuse

Require zero live processes/mounts, installed launchers, scheduled jobs, assistant tool references or deployment definitions depending on targeted legacy paths. Separately account for stopped containers: obsolete migration/runner containers may retain old references even when they are not running. Removing a stopped container needs review; it is never permission to remove its volumes.

Retire disabled jarvis-codex-reconcile units and old custom supervisor/runtime only after confirming no new worker dependency. No Phase5B fence is cleared or treated as success. Keep protected rollback material off-host long enough to meet the operator's chosen rollback policy; this is a recoverability snapshot, not a maintained legacy workflow. Then delete approved obsolete /srv/hermes-dev and /srv/jarvis-codex contents. This active development session must relocate before its own directory can be removed.

For /srv/jarvis-activity, obsolete execution state/runner-home can go after the adapter audit. Secrets go after all consumers use /etc. **Backups stay where they are** because backup relocation is deferred; consequently /srv/jarvis-activity may remain as a backups-only directory. Removing the final directory requires a later explicit backup move; do not silently delete backups to satisfy a tidy tree.

**Pass:** new workflow and existing application checks pass, required current source is in reviewed Git/off-host backup, no dependencies point at deleted paths, canonical repositories unchanged by worker activity. **Approval:** review exact deletion inventory and rollback snapshot before destructive cleanup. **Rollback:** restore needed legacy source/config from the verified snapshot and restore affected prior service definitions; no automatic revival of old orchestration/timer.

## Inputs and decisions before dependent actions

1. Approve the destination map and source grouping. Recommended: existing Jarvis Python application layout retained; ledger and engineering are subprojects in the same canonical repository.
2. Select the protected **off-host rollback backup destination and retention period**. None was invented or tested here; slice1 cannot finish without it.
3. Approve source diff/merge only after the candidate is prepared. No remote writes are implied.
4. Select maintenance windows when the exact MCP/Hermes/adapter and eventual ledger DB cutover candidates are ready. The DB source-mount recreation is an actual brief outage and must not be hidden inside file cleanup.
5. Decide obsolete adapter-route retirement based on the consumer audit. If consumers exist, keep compatibility state temporarily instead of deleting it.
6. Defer PostgreSQL unification, centralized backups, GUI, hard RRAS budget enforcement and paid tasks. These are not prerequisites for source capture or offline preparation.

## Delivery and next action

Each slice will have an administrator script with all variables defined, exact hashes/manifests, absent-only publication checks, safe failure reporting and specific rollback commands **prepared and tested before execution**. Release IDs, backup targets, build dependency closure and service functional checks that are not yet verified are gates, not invented command arguments. This plan deliberately does not present a speculative all-in-one sudo migration script.

**Next:** perform slice1 inventory completion and prepare slice2 source consolidation in an isolated review checkout after the destination map is accepted. No data/code migration or service change occurs merely by accepting this planning document. Source changes/install/cutover/deletion remain separately reviewable checkpoints.

## Execution checkpoint — plan approved, slice1 in progress

Operator approved execution on2026-10-12. No host moves/install/cutovers/deletions performed. Canonical source and original development branch preserved. Slice1 off-host destination and retention remain required inputs; /srv/backups exists but is local storage, not established as an off-host recovery copy. No off-host mounted filesystem was identified in the accessible mount inventory; scheduled backup transport remains to be checked.

Noninteractive sudo was checked outside the managed filesystem sandbox and requires an operator password. No password was requested or captured. A read-only administrator collector was prepared to close protected cron/user-unit/runner reference gaps and record sanitized container identity/mount metadata. It excludes credential/auth files and emits source path/count metadata only; raw environment, commands and source lines are not output. Five focused tests passed, including secret-file exclusion and Docker environment/command redaction. Inventory gaps remain visible and do not authorize deletion.

Collector `/tmp/rras-filesystem-inventory-20261012-01.py` is a review copy of tools/migration/inspect_filesystem.py. Exact hash is supplied in the operator handoff. It performs no host writes, container starts, SQL operations or model calls. Once its result and the backup destination/retention are supplied, finish the verified rollback capture before importing/deploying source under subsequent slices.

## USB rollback preparation

Operator supplied the read-only administrator inventory:86 files examined, no unreadable paths in its bounded scan, container identities/mounts recorded. USB UUID `C0DE-2913` was identified as removable USB/vfat and mounted at `/mnt/rras-migration-usb` by the operator with root-only access/noexec,nodev,nosuid. Operator reported113GiB free, 1.8GiB pre-existing drive contents; listed source/config/state footprint approximately1.8GiB. Existing USB contents must not be overwritten. This removable copy meets the off-host objective only after successful verification, safe unmount and physical disconnection. It is not a mounted network/off-host filesystem while attached.

Prepared collector `tools/migration/usb_backup.py` and review copy `/tmp/rras-usb-migration-backup-20261012-01.py`. It requires root/server01/exact mounted UUID, creates unique absent-only stage and USB subdirectory, prompts for a new passphrase locally, captures source/config/Git working content and credentials, encrypts AES256 via GPG, splits into1GiB files, synchronizes/readbacks USB, decrypts and restores into a private local stage. It checks restored bytes/modes/UIDs/GIDs/link targets/xattrs, source stability and ciphertext hashes. Archive traversal/symlink-parent/hardlink escapes are refused. Four focused tests include a real harmless GPG roundtrip; local GPG agent sockets require the unsandboxed test environment. No production credential or USB backup has been executed by the agent.

Live PostgreSQL files/volumes are excluded; existing ledger backup files under /srv/jarvis-activity are captured, but this does not establish a current database restore point for slice5D. Metadata preservation uses tar; FAT32 is not used to store loose Linux files. Root-private local plaintext stage/test restore remains until explicit cleanup; no original files, legacy directories or pre-existing USB contents are deleted. There is no automatic expiry: retain the encrypted USB rollback until operator-authorized cleanup. Keep its passphrase separately/off-server. Any capture/verification failure preserves the unique failed stage; source migration stays blocked, and the operator returns only the safe error/result.
