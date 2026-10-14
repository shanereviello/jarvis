# Native step 2: minimal engineering records and profile preparation

Date: 2026-10-05. Status: **source utility implemented; credential-free profile candidate prepared; native deployment pending**.

## Current cost policy

Operator instruction supersedes the earlier custom hard-budget activation gate: build the functional core first and defer RRAS budget enforcement. Spending controls remain operator-managed in the API portal; no portal settings were inspected or changed here. Keep $5/task, $20/day and $100/month as intended configurable future controls, without claiming the utility enforces them.

Current [official spend-limit documentation](https://developers.openai.com/api/docs/guides/spend-limits) supports monthly organization/project hard limits when **Enforce a hard limit** is enabled; alerts alone do not stop calls. Enforcement may slightly overshoot during propagation. The documented monthly controls do not establish per-RRAS-task or daily enforcement. This corrects the earlier blanket assumption that native portal controls are only soft alerts. The specific operator account settings remain unverified.

No budget proxy is implemented or required to continue core source/configuration work. No paid execution or credential use occurred in this pass.

## Implemented small utility

[activity.py](../tools/rras_native/activity.py) is a standard-library, local CLI with five operations:

| Operation | Behavior |
|---|---|
| `admit` | Resolve enabled canonical repository allowlist entry; capture real Git baseline; persist stable task objective and native project reference; repeated same admission retains the original baseline; conflicting identity is refused |
| `preview` | Return native `hermes kanban create` argv using a preserved worktree, registered native project, idempotency key and triage; **does not submit or execute** |
| `bind` | Record operator-attested board/task/run/session references absent-only; cannot replace an old run silently |
| `export` | Verify native worktree belongs to registered Git common repository and baseline is an ancestor; capture baseline-to-working-tree binary patch, staged patch, status and explicit log files; content-addressed manifest and local index |
| `review` | Verify manifest/artifact hashes and current worktree; record local operator acceptance/rejection for exact export/HEAD; acceptance requires committed clean work; no remote action authority |

This is a local admission registry and evidence index, not a new lifecycle controller. Native project-to-repository mapping must be verified before executing the preview. Binding is attested rather than independently authenticated. No claim tokens, writer leases, daemon, scheduler, Docker calls, model calls or database migrations are introduced.

The reviewed repository registry has this shape (paths and project slug must be actual values in the execution environment):

```json
{
  "schema_version": 1,
  "repositories": [
    {"repository_id": "demo", "path": "/absolute/registered/repository", "enabled": true, "hermes_project": "verified-native-project"}
  ]
}
```

Host/container paths can differ; do not use host paths blindly inside Hermes. State must be caller-owned 0700 and separate from old `/var/lib/jarvis-codex/runtime-state`. Export logs explicitly; do not provide secret-containing logs. Untracked file names are retained, not their content; commit intended files before acceptance. Git inspection disables external diff/textconv, hooks and fsmonitor. It invokes no validation automatically.

Snapshots are from a mutable worktree, not a transactional filesystem or tamper-resistant store. Stop editing before export/review. Essential test command/exit-code provenance can be included in explicit reported logs; this phase does not reproduce or certify tests. Artifacts remain local and `database_indexed=false`; PostgreSQL indexing is a later adapter, not silently claimed complete. Native restarts producing another run need a separate RRAS record initially; no automatic multi-attempt lifecycle is implemented.

## Profile candidate

[prepare_profile.py](../tools/rras_native/prepare_profile.py) creates an absent-only directory containing an isolated engineering config, Codex config, activation-plan metadata, CLI source and SHA-256 manifest. No installed files are modified. `gpt-5.4` is a review candidate, not an automatic final model choice or entitlement claim; [official model reference](https://developers.openai.com/api/docs/models/gpt-5.4). CLI candidate is 0.159.0, matching the observed host executable.

Installed-source inspection found that session creation does not pass an explicit per-profile Codex home. The launch environment must supply `CODEX_HOME` separately, and native dispatcher propagation still needs acceptance. The running deployment's Compose location is `/opt/hermes/compose.yaml`; no host image-build recipe was found in that directory. The candidate therefore does not pretend to include a complete executable/image installation or rollback procedure.

## Repeatable source checks and candidate preparation

Run these as the ordinary repository user. They do not install, launch Hermes or use credentials:

```bash
(
set -euo pipefail
REPO=/srv/hermes-dev/jarvis/tasks/TASK-20260916-001-central-codex-activity-prototype/repo
cd "$REPO"
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest tests.test_rras_native_activity -v
git diff --check
)
```

```bash
(
set -euo pipefail
REPO=/srv/hermes-dev/jarvis/tasks/TASK-20260916-001-central-codex-activity-prototype/repo
REVIEW_PARENT=$(mktemp -d /tmp/rras-native-profile-review-XXXXXXXX)
CANDIDATE="$REVIEW_PARENT/candidate"
MODEL_CANDIDATE=gpt-5.4
PYTHONDONTWRITEBYTECODE=1 python3 -B "$REPO/tools/rras_native/prepare_profile.py" \
  --destination "$CANDIDATE" --model "$MODEL_CANDIDATE"
printf 'Review candidate: %s\n' "$CANDIDATE"
)
```

Do not copy the candidate into `/opt/data`, apply it to the existing default profile, or execute the preview yet. Actual project registration, persistent CLI packaging, effective callback controls and model-free native acceptance are the next deployment work. No custom budget gate is needed for that work under the revised policy.

## Tests and next slice

Focused tests use disposable local Git repositories and native Git worktrees. They cover stable admission/conflict, disabled/unknown repo refusal, triage/idempotency preview, attempt-binding conflict, committed/staged/unstaged evidence, foreign-repository refusal, native worktrees, tampering, stale/dirty review refusal, unsafe inputs, external-diff bypass denial and absent-only credential-free packaging. These are source tests, not installed Hermes/Codex acceptance.

Executed source result: **12 tests passed**, zero failures/errors; three Python files parsed successfully; `git diff --check` passed. No full repository suite rerun. Prepared candidate: `/tmp/rras-native-profile-review-9hgqxhxg/candidate`; manifest SHA-256 `e01752059cab83a7c7f9407c33d8dacdb6d072818f00be2ac27b55ecc51b3339`. All manifest file hashes were checked. This candidate contains review configuration and utility source, not the Codex executable or an installed profile.

Next: prepare the persistent Codex executable/image plan and validate engineering home/tool configuration through a model-free native integration fixture. Then wire actual triage submission/native IDs and the dedicated activity-ledger index. Paid canary remains a separately authorized step; installed services, old runtime records, secrets and disabled timer remain preserved.
