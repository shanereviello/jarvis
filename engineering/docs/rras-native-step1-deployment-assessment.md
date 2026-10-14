# Native deployment step 1: installed capability assessment

Date: 2026-10-05. Status: **read-only assessment complete; configuration and installation not performed**.

Subsequent operator decision: custom budget enforcement is deferred until the core architecture is functional, with API portal spending controls used meanwhile. Historical budget blockers below are superseded by the [step-two checkpoint](rras-native-step2-implementation.md); installed capability observations remain unchanged.

Implements step 1 of the approved [native-first review](rras-native-first-architecture-review.md). Machine-readable observations are in [the assessment evidence](rras-native-step1-evidence.json). This is a deployment proposal, not an administrator installation procedure.

## Verified deployment

| Item | Observation | Consequence |
|---|---|---|
| Repository | `phase5b/guarded-host-orchestration`, HEAD `f0d8a6eaf016153708c3e46a32e204a93bd11a97` | Existing tracked/untracked work preserved |
| Hermes image | `sha256:b99f4564d5e17ec0183314c0d2f6f633657cff4916fad0f05f6e7667722da432` | Assess existing image before considering an upgrade |
| Hermes version | Installed `pyproject.toml` declares `0.20.4` | Source declaration, not a runtime invocation |
| Source provenance | OCI revision label `76952ba54f5dd83f4f5bd0246059171b4b9d1c4a`; no `/opt/hermes/.git` | Recorded build assertion, not independently verified correspondence to an upstream commit |
| Native features | Kanban CLI/DB/tools, profiles, Codex runtime switch and App Server transport source present | No custom runner needed merely because the old controller exists |
| Container execution | PID 1 and inspection subprocess UID/GID 0; `privileged=false`, network `jarvis-net` | Container root is not evidence of host root. Evaluate actual native sandbox/callback authority with focused checks |
| Codex in container | Absent on a clean standard PATH and four checked common installation paths | No executable presently available to the proposed runtime there; unusual paths/live PATH were not inspected |
| Codex on host | `/home/shanereviello/.local/bin/codex`, `codex-cli 0.159.0` | Personal executable/version observation only; no login/config/auth inspected or reused |
| Engineering profile | `/opt/data/profiles/rras-engineering` does not exist | Prepare a new profile; do not enable the runtime globally on current Hermes |
| Existing reconcile service | Timer disabled; service inactive | Preserve this state and retained records |

Read-only repository/baseline mounts and writable task/shared/artifact/data mounts were inspected. No Docker socket was listed among mounts. Multiple task roots are writable in the container; native per-session policy must determine allowed writes. This observation does not justify replacing native sandboxing with custom containers.

## Installed source versus moving documentation

Installed `agent/transports/codex_app_server.py` defines minimum CLI `(0,125,0)`, launches `codex app-server` over stdio, and strips non-provider secrets through the native subprocess helper. Actual helper behavior and callback authority remain deployment checks; comments are not a secret-leak acceptance result.

For Kanban workers, the installed transport adds the board database directory as an extra writable root, retains workspace-write sandboxing and disables sandbox tool network access. It does not contain the newer documented multiple-root forwarding in that source section. Use a native preserved worktree with the ordinary workspace layout first. Only patch/upgrade if the chosen layout fails a concrete write/handoff requirement; do not upgrade automatically to match a documentation page.

Installed profiles source supports independent Hermes homes, with profiles beneath the custom Hermes home. Runtime-provider source supports the opt-in setting and named custom-provider resolution. Native dispatch passes the workspaces-root environment marker. No global concurrency setting was established by the bounded source searches; serialize ready coding tasks operationally initially.

References checked with official documentation: [Hermes native Codex runtime](https://hermes-agent.nousresearch.com/docs/user-guide/features/codex-app-server-runtime), [Codex App Server](https://learn.chatgpt.com/docs/app-server). Their documented capabilities do not prove the current deployment's effective configuration.

## Smallest deployment proposal

1. Keep the existing Hermes gateway and image unchanged. Prepare a distinct `rras-engineering` profile rather than converting the default profile. Do not clone credential-bearing configuration, auth stores, plugins or personal Codex home.
2. Make a pinned Codex executable available in the Hermes execution environment through a reviewed persistent build/install mechanism. Candidate CLI is **0.159.0**, matching the observed host version and exceeding the installed source minimum. Artifact checksum and model-free protocol/sandbox validation are required before calling it accepted. Do not mount the personal CLI directory or auth home as the solution, and do not install into a live container's disposable layer.
3. Configure the profile for `model.openai_runtime: codex_app_server` and a named API provider such as `custom:rras-api`, with matching Codex provider configuration in a separate profile-owned Codex home. These are proposed names; no endpoint or key source is applied. Verify how this exact Hermes version selects that home before writing config.
4. Keep native local tools, worktrees and lifecycle. Permit local commits; withhold publication, deployment, production database and Docker authority from coding tools/callbacks. Start with network-disabled tool sandbox and one ready coding task. Preserve the worker's necessary Kanban handoff access.
5. Use a small RRAS task-record/export CLI next: task ID, registered repository, baseline commit, Hermes task/run references, evidence manifest and operator review. Do not install the custom recovery-service candidate or its writer-lease migration for this new path.

No model pin is selected in this source/configuration assessment. Select one supported API model with reviewed pricing when budget feasibility is assessed. A source minimum version does not establish model entitlement or protocol compatibility.

## Gates before applying settings or running a task

| Gate | Small concrete check | Current result |
|---|---|---|
| Executable/protocol | Pinned CLI available to native profile; model-free initialization succeeds | Pending; CLI absent in inspected container locations |
| Profile isolation | Separate home/provider and explicit callback list; personal/gateway auth is not copied | Pending; profile absent, live config intentionally not read |
| Worktree/handoff | Native task creates preserved branch/worktree; handoff can update board; sibling write denied | Pending; no task/container acceptance was run |
| Irreversible authority | Coding tool/callback profile lacks production/push/deploy authority | Pending; source/mount inspection alone cannot establish it |
| Recovery | Native interrupted task can be understood and resolved before a conflicting retry | Pending; preserve all old Phase 5B fences separately |
| Hard budgets | $5/task, $20/day, $100/month, including auxiliary calls, enforced or live execution denied | Unresolved; no verified native hard-dollar control |

API credential provisioning remains pending; existing secret location is not read or changed. The configured provider must use the dedicated API Platform identity. The CLI candidate is not permission to reuse personal auth. A native/provider spending feature should be checked first; if insufficient, propose only the narrow budget gateway. Do not put a direct production key into the new profile before deciding how the hard ceiling can be enforced.

## Next action

Prepare the minimal admission/export utility and a credential-free native-profile installation candidate. First inspect the existing image-build/deployment mechanism and exact profile/Codex-home selection code; then produce absent-only profile settings and a pinned executable plan. Test configuration and protocol without inference. Applying profile/install changes and the first paid task are distinct later operations, not done in this assessment.

Validation performed: branch/HEAD, filtered container/image metadata, installed source presence and selected source sections, file hashes, profile/executable path existence, host CLI version and systemd disabled/inactive state. The Git revision command failed because the image contains no Git metadata; the revision above comes from the allowlisted OCI label. Live provider configuration, environment values, secrets, auth, database, model availability and runtime sandbox enforcement were not inspected or exercised.
