# Native dispatcher checkpoint — 2026-10-05

Continues [host candidate](rras-native-host-candidate.md). Branch remains `phase5b/guarded-host-orchestration` at `f0d8a6eaf016153708c3e46a32e204a93bd11a97`. No installed service, gateway, credential, production task, timer or runtime fence was modified.

## Actual result

`tools/rras_native/probe_dispatcher.py` ran against the frozen Hermes source/venv. It used actual native project creation, task creation, claim/run bookkeeping, dispatch locking, worktree creation, profile environment resolution, default process spawning, per-task logging and completion transitions. Only the coding executable was replaced with a fixture process; native `_resolve_hermes_argv` was patched to invoke that process. Native lifecycle hooks on fake completion were explicitly suppressed. This is an integration fixture, not a model-backed task or a full Hermes CLI/session acceptance.

**11 checks passed:** one native spawn; second dispatch excluded by the one-worker cap; child survived the dispatcher process's exit; named profile selected; isolated CODEX_HOME propagated; child cwd was its native worktree; profile toolsets forwarded; board/scratch-workspace roots forwarded; child exited after completion; native task became done; RRAS exported the resulting patch with native task/run references. The dedicated UID and systemd cgroup were not tested. The fake edit and completion are test-only. Original private fixture repo, board, child log, patch index and receipt are retained at `/tmp/rras-native-dispatcher-id39auaz`; fixture child is stopped. [Repository evidence](rras-native-dispatcher-evidence.json) includes the receipt hash and scope notes.

After source cleanup hardening, **23 focused tests passed**, including PID-reuse refusal and zombie-versus-live-worker classification. The original successful integration fixture was not repeated after the restart; only source cleanup helper regressions and bundle verification were needed. Existing admission/export tests also passed.

## Deployment consequences

- Named profile must live at `<root>/profiles/rras-engineering/config.yaml`. Setting only `<root>/config.yaml` does not establish the assignee. Keep root and named-profile configurations explicit; preserve the board/root environment across profile selection.
- Actual worktree placement is `<admitted-repo>/.worktrees/<native-task-id>`. `HERMES_KANBAN_WORKSPACES_ROOT` governs other native workspace paths but does not relocate this worktree. Put the worker's admitted checkout outside the writable board directory, e.g. under `/var/lib/rras-engineering/repos`, and keep board state under `/var/lib/rras-engineering/kanban`. Native claims and single-worker policy provide the demonstrated exclusion; this is not an adversarial per-task UID guarantee.
- Detached-session child survival was demonstrated outside systemd. It does **not** imply escape from a systemd cgroup. A Type=oneshot dispatch unit with KillMode=control-group is not a reviewed task runner. Keep the candidate help-only service unchanged. Resolve a native foreground lifecycle or engineering-only native gateway arrangement in a disposable cgroup before selecting the production worker unit; no custom long-running dispatcher or deprecated forced daemon was added.
- Native dispatch produced `--toolsets bfl,kanban,skills` from the candidate profile. Source shows `bfl` is an auto-added recent-toolset migration; its requirements gate may leave zero callbacks without applicable credentials. No provider credentials or callbacks were loaded/tested. Effective tool inventory and fail-closed approval behavior still require session acceptance before a canary. Do not treat a configuration list as the proven runtime tool surface.
- CPython 3.13.16 linked SQLite 3.37.2. Native Hermes detected the WAL-reset issue and selected DELETE journaling. This probe passed with that fallback. Retain native fallback for the one-worker canary; do not enable WAL or mutate the host SQLite library. Observe lock/restart behavior under actual worker acceptance.

## Updated review bundle

`/tmp/rras-native-host-review-20261005-03`
Manifest SHA-256: `f960015c50d7f140ccf126ce8540fe76739ee544eec1346fd38d668f42b7fa90`.
Includes the hardened disposable dispatcher probe, exact source archive/lock, pinned Codex resources and existing help-only service. It is still uninstalled and contains no built venv or API credentials. The earlier 02 bundle and all failed/successful receipts remain intact.

## Dedicated-UID administrator preflight (read-only)

Run on server01; this does not provision, install or activate anything:

```bash
(
set -euo pipefail
REVIEW=/tmp/rras-native-host-review-20261005-03
ACCOUNT=jarvis-codex-engineering
python3 -B - "$REVIEW" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);m=r/'manifest.json'
assert hashlib.sha256(m.read_bytes()).hexdigest()=='f960015c50d7f140ccf126ce8540fe76739ee544eec1346fd38d668f42b7fa90'
files=json.loads(m.read_text())['files']
assert {str(p.relative_to(r)) for p in r.rglob('*') if p.is_file() and p!=m}==set(files)
for name,h in files.items():
 p=r/name
 assert not p.is_symlink() and p.resolve().is_relative_to(r)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,name
print('Review hashes verified')
PY
hostname
if getent passwd "$ACCOUNT"; then
  id "$ACCOUNT"
else
  printf 'Dedicated account is absent; provisioning remains pending.\n'
fi
for PATH_TO_CHECK in /opt /opt/rras-engineering /var/lib /var/lib/rras-engineering; do
  if test -e "$PATH_TO_CHECK" || test -L "$PATH_TO_CHECK"; then
    stat -c '%n owner=%U:%G mode=%a type=%F' "$PATH_TO_CHECK"
  else
    printf '%s is absent\n' "$PATH_TO_CHECK"
  fi
done
systemctl is-enabled jarvis-codex-reconcile.timer || true
systemctl is-active jarvis-codex-reconcile.service || true
)
```

This block intentionally does not inspect secrets or account environment. Presence is not acceptance: if the account already exists, review its UID/GID/groups and existing state before provisioning; never repurpose it automatically. Do not change `/srv` or existing applications. Approved future account has no login/sudo/Docker/LXD/NAS membership; mutable state is worker-owned 0700 and release/runtime is root-owned. A final-path frozen non-editable venv build is required; the temporary venv must not be copied as a relocatable release.

## Next source slice and activation gates

Prepare a dedicated-UID, disposable installed-host acceptance harness and an ordered administrator provisioning/release/rollback guide. It must run real Codex command/exec under the proposed UID with no key, validate admitted task and board writes plus sibling/network denial, verify powerful socket/private-file access is denied, and preserve exact cleanup/evidence. Native worker child lifetime must be tested inside the selected disposable cgroup before choosing a production runner. If no supported native foreground worker owner is established, report that interface gap; do not solve it by silently recreating Phase 5B orchestration.

Administrator installation and acceptance must preserve the production gateway and existing services/records. Actual profile selection, full session callback/tool inventory and approvals remain separate gates. Only after those pass: separately authorized dedicated-API canary, usage/patch/validation review and controlled activation. Budget enforcement remains operator-managed API portal policy. No administrator provisioning command is requested until the source harness and concrete installation procedure are reviewable.

Follow-up: [host acceptance preparation](rras-native-host-acceptance-preparation.md) adds the actual-UID payload, stronger five-case command boundaries and latest review bundle. Native foreground readiness remains unresolved; production runner/installation/activation stay pending.
