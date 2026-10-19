# Server01 migration status — 2026-10-18

Source consolidation and service/path relocation have been performed separately.
This records the resulting installation, not authorization to repeat maintenance,
start stopped services, run migrations, execute paid tasks or delete old paths.
Private configuration, transaction journals and task records remain outside Git.

| Component | Result | Acceptance and limits |
|---|---|---|
| Jarvis MCP / Linear action MCP | Reviewed source release under `/opt/jarvis/releases/mcp-9e8749d65063`; protected environment/bridge binds under `/etc/jarvis`. Both replacements running on accepted exact image IDs. | Post-cutover protocol discovery passed. Notes/audit roles preserved; no real Linear mutation used for acceptance. Original containers retained stopped. |
| Hermes | Reviewed Compose under `/opt/hermes/releases/hermes-0c8b6be07ce8`; same image and private state; four legacy workspace mounts removed. | Actual five retained mounts, gateway liveness, six configured MCP entries, two preparation tools and reduced write roots verified. No claim that every remote integration was exercised. Original container retained stopped. |
| Ledger PostgreSQL / adapter | Reviewed deployment under `/opt/jarvis-activity/releases/ledger-c677172ac8d7`, protected configuration under `/etc/jarvis/activity-ledger`; replacements created and stopped. | Same external volume/networks and existing images; unchanged evidence mount roles. Current cold backup and isolated recovery passed; logical dump retained root-private. Actual schema versions1–8, zero active writer/controller leases at recovery. No production start or migration occurred, so live adapter/database readiness is not certified. |
| Engineering runtime | Trusted native-10 interpreter path retained; base Python copied to `/opt/rras-engineering/releases/cpython-3.13.16-ae7041461525`. | Existing3.13.16 executable/runtime bytes preserved. Isolated UID996 import/access checks and ten native fake-worker cases passed after the pointer switch with zero model calls. Old runtime retained. |
| Engineering credential | Protected copy at `/etc/rras-engineering/credentials/openai_api_key`. | Equality checked privately; direct worker access refused. Existing launch arguments/approvals were not rewritten. New reviewed launches select the source explicitly for systemd delivery; no paid execution is implied. |
| Automation | Legacy reconciler disabled/inactive; engineering Git-sync timer enabled. | Git-sync fetches/status-checks refs without modifying canonical branch contents. Existing fences and historical lifecycle records remain intact. |

## Compatibility boundaries

Ledger path relocation deliberately reused the installed adapter image. Newer
canonical source and migration files are not proof that production runs them.
Canonical migrations extend through11, while the recovered database has applied
only1–8. Review image/application/schema compatibility before any future upgrade;
never run migrations simply to relocate deployment files. Preserve the migration
history, grants and data volume. The release Compose contains no migration service
and refuses implicit image pulls/builds or missing external-volume creation.

Ledger restart policy remains `no`. Its earlier stop sequence coincided with a
Docker/containerd package upgrade; the adapter exceeded its stop timeout and was
not reported as OOM-killed. Keeping both replacement definitions stopped preserves
the observed state. Decide future availability and restart behavior explicitly
before activation, then test authenticated reads without submitting tasks.

The three source merges for MCP/Linear, Hermes and ledger deployment were reviewed
independently. A source merge does not authorize subsequent installation or an
application/schema upgrade. Production-bound execution, publication and merge
contracts retain their own approval requirements.

## Retained material and final retirement gates

Original containers and the historical migration job remain stopped for exact-ID
rollback or evidence. They retain old Compose labels/bind provenance. Avoid broad
Compose up/down/recreate commands while originals and replacements share service
labels. Never start both database containers against their shared data volume.

Do not delete old roots as a cosmetic follow-up:

- `/srv/hermes-dev` still contains dirty/untracked development work; older Codex
  sessions were observed with that worktree as cwd. Close or relocate those
  sessions and verify a frozen, private snapshot/restore before retirement.
- `/opt/jarvis-codex` and `/srv/jarvis-codex` retain old runtime/credential or disabled
  legacy-unit dependencies and rollback evidence. Audit each remaining consumer
  before proposing an exact deletion list; do not activate the reconciler.
- `/srv/jarvis-activity` retains evidence mounts, backup material and original
  configuration for rollback. Relocation did not supersede those records.
- `/var/lib/jarvis-codex/runtime-state` and newer task/control roots contain
  lifecycle evidence and writer fences. These are not cleanup targets and are
  not cleared or declared successful by migration.

Final retirement requires an explicit disposition for each consumer, a verified
recovery snapshot (including uncommitted/untracked work), and approval of exact
paths/units/containers. Retaining rollback material does not create authority to
run the abandoned workflow. Robot feature work, model upgrades and PostgreSQL
consolidation remain outside this migration.
