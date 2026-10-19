# Server01 migration status — 2026-10-18

Source consolidation and service/path relocation have been performed separately.
This records the resulting installation, not authorization to repeat maintenance,
start stopped services, run migrations, execute paid tasks or delete old paths.
Private configuration, transaction journals and task records remain outside Git.

| Component | Result | Acceptance and limits |
|---|---|---|
| Jarvis MCP / Linear action MCP | Reviewed source release under `/opt/jarvis/releases/mcp-9e8749d65063`; protected environment/bridge binds under `/etc/jarvis`. Both replacements running on accepted exact image IDs. | Post-cutover protocol discovery passed. Notes/audit roles preserved; no real Linear mutation used for acceptance. The operator subsequently retired the stopped originals after verified preservation. |
| Hermes | Reviewed Compose under `/opt/hermes/releases/hermes-0c8b6be07ce8`; same image and private state; four legacy workspace mounts removed. | Actual five retained mounts, gateway liveness, six configured MCP entries, two preparation tools and reduced write roots verified. No claim that every remote integration was exercised. The stopped original was subsequently retired after verified preservation. |
| Ledger PostgreSQL / adapter | Reviewed deployment under `/opt/jarvis-activity/releases/ledger-c677172ac8d7`, protected configuration under `/etc/jarvis/activity-ledger`; replacements created and stopped. | Same external volume/networks and existing images; unchanged evidence mount roles. Current cold backup and isolated recovery passed; logical dump retained root-private. Actual schema versions1–8, zero active writer/controller leases at recovery. No production start or migration occurred, so live adapter/database readiness is not certified. |
| Engineering runtime | Trusted native-10 interpreter path retained; base Python copied to `/opt/rras-engineering/releases/cpython-3.13.16-ae7041461525`. | Existing3.13.16 executable/runtime bytes preserved. Isolated UID996 import/access checks and ten native fake-worker cases passed after the pointer switch with zero model calls. The duplicate old runtime was subsequently removed after acceptance. |
| Engineering credential | Protected copy at `/etc/rras-engineering/credentials/openai_api_key`. | Equality checked privately; direct worker access refused. Existing launch arguments/approvals were not rewritten. New reviewed launches select the source explicitly for systemd delivery; no paid execution is implied. |
| Automation | Obsolete reconciler units removed/not-found; engineering Git-sync timer enabled. | Git-sync fetches/status-checks refs without modifying canonical branch contents. Existing fences and historical lifecycle records remain intact. |

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

## Completed retirement and retained data

After accepting the new installations, the operator approved simplifying retirement
rather than maintaining an executable legacy stack. Unique dirty/untracked source,
Git history, protected runner/configuration records and old unit definitions were
privately archived and independently restored/compared before removal. These are
local root-private preservation copies; no off-host recovery claim is made.

Completed and independently checked:

- Removed the five stopped original containers and historical completed migration
  container by exact ID, without force/volume flags. Existing named and anonymous
  volumes remain. The former original-container rollback option is retired.
- Removed the inactive/disabled reconciler service and timer; both are now
  not-found/inactive. Existing lifecycle records and writer fences remain.
- Removed `/opt/jarvis-codex` and `/srv/jarvis-codex` after clearing consumers.
- Gracefully stopped the exact connected-backend process identities from an
  independent terminal, then removed `/srv/hermes-dev` only after checking zero
  process/bind consumers and an unchanged verified source manifest. The three
  earlier cwd references belonged to related backend processes, not three
  independent coding jobs.
- Preserved/restored and removed the obsolete checkout/configuration children of
  `/opt/jarvis`, leaving only its active `releases` directory. Removed the original
  `/opt/hermes/compose.yaml`; the active Hermes release remains. Home-account
  authentication and configuration were not cleanup targets.

Current MCP/Linear/Hermes services remain running; ledger replacements remain
created/stopped. The native-10 Python base is the accepted engineering release,
with no dependency on the removed interpreter tree. Current release roots,
`/srv/hermes/data`, ledger data volume, `/srv/jarvis-activity` evidence/backups and
all historical/current `/var/lib` task/control/fence roots remain intact.

Root-private preservation/maintenance evidence is under `/var/lib/jarvis-migration`.
Do not rerun completed scripts: some preserve absent-only allocations and some
refer to intentionally retired original containers. Restore files deliberately
from the verified archive if unique historical work is needed; do not restart an
abandoned workflow to recover source.

## Work explicitly left outside this migration

Ledger activation/restart policy and any application/schema upgrade remain future
reviewed work. The original protected canary credential source remains because
historical launch arguments were not rewritten; newly reviewed launches select
`/etc/rras-engineering/credentials/openai_api_key` explicitly. No credential was
rotated and no task was launched to test cleanup.

The reusable Hermes/Codex workflow can now resume as its own development scope.
Migration acceptance did not establish its full model-backed end-to-end behavior.
Robot feature work, model upgrades and PostgreSQL consolidation remain separate.
