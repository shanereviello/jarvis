# Bounded sandbox investigation and host-worker proposal

2026-10-05. Supersedes the container-next-slice proposal in [step four](rras-native-step4-container-acceptance.md). Follow the approved [native-first architecture](rras-native-first-architecture-review.md). Container topology is optional.

## Investigation result and stopping point

One new disposable diagnostic used the exact existing Hermes image, no network or production mounts, read-only root, all capabilities dropped, no-new-privileges, 128 MiB memory, one CPU and 32 PIDs. Both `unshare(CLONE_NEWUSER)` and `unshare(CLONE_NEWUSER|CLONE_NEWNS)` returned EPERM. Active policy was `docker-default (enforce)` plus seccomp mode 2. The exact confirmed fixture container was removed. [Machine-readable receipt](rras-native-sandbox-investigation-evidence.json) retains identity and output; original journal remains under `/tmp/rras-sandbox-investigation-8b5491c8c0444253a61f521ed02797c3`.

A host `unshare --user --map-root-user /usr/bin/id` succeeded as the operator's real UID 1000; namespace UID 0 is not host root. Earlier actual host Codex command probes also succeeded, as recorded in [step three](rras-native-step3-runtime-preparation.md). Neither observation demonstrates operation under a new dedicated account.

[Docker documentation](https://docs.docker.com/engine/security/seccomp/) supports supplying a custom seccomp profile, but describes namespace and mount restrictions and advises against changing the default. No tested ready-made narrow policy was established here. Attribution between seccomp and AppArmor remains unresolved; no audit-log or syscall-policy claim is invented. Fixing the first namespace error would not establish that subsequent bubblewrap mount/namespace operations work. Pursuing that chain would require custom policy design, host loading where applicable, and ongoing regression testing. That cost exceeds this bounded investigation and offers no required RRAS product behavior.

**Stop pursuing this container lane.** This is an engineering-cost decision, not proof that containers inherently require broad privileges. No SYS_ADMIN, privileged/unconfined policy, daemon/sysctl change, sandbox bypass or host policy installation was attempted. [Official OpenAI documentation](https://learn.chatgpt.com/docs/sandboxing) supports Linux bubblewrap/user namespaces; retain the native sandbox on the host instead of nesting it. Docker gateway, installed Phase 5B services and old evidence remain unchanged.

## Smallest recommended architecture

Keep the existing Hermes gateway. Prepare a separate host-native Hermes engineering instance with its native Kanban board, worktree manager and worker lifecycle, using Codex App Server over local stdio. Avoid introducing another RRAS scheduler, Docker supervisor, budget broker or database dependency. How the gateway submits to this instance must use a verified native Hermes interface; do not invent a remote dispatcher API. Start with the operator invoking the engineering instance directly, then verify gateway integration separately.

Proposed account `jarvis-codex-engineering` is currently absent. Provision later as a dedicated non-login account with no sudo, Docker/LXD, administrator, NAS or existing supervisor groups. Allocate UID/GID only at administrator preflight. Do not reuse `nobody`, UID 1000 or `jarvis-codex-supervisor` (997). This worker account is distinct from the preserved old recovery service.

Proposed immutable code/venv/Codex package: root-owned `/opt/rras-engineering`. Proposed private home, board, workspaces and evidence: `/var/lib/rras-engineering`, worker-owned 0700 with protected ancestors. Board and workspace roots remain separate. Configure explicit HERMES_HOME, CODEX_HOME and HERMES_KANBAN_WORKSPACES_ROOT; no personal auth/config copy. Existing `/opt/jarvis-codex` and `/var/lib/jarvis-codex` ownership/state are outside this proposal and must not be changed.

Use Codex workspace-write, network-disabled coding tools, explicit admitted task/board roots, excluded broad temporary roots and manual approvals. The trusted model client eventually needs API networking; a systemd-wide network denial would also block inference and is not an appropriate default. No approval bypass. No grant for merge, push, deployment, Docker or production databases. RRAS admission and evidence utility supplies traceability and human review. Portal spending policy remains current; custom hard caps are deferred.

## Practical risk and cost

| Control | Practical risk reduced | Cost / limitation |
|---|---|---|
| Dedicated unprivileged UID, private state, no powerful groups | Removes operator's Docker/LXD/sudo and private-home authority from ordinary worker processes | One account and directory setup; publicly readable host files remain readable |
| Native Codex sandbox and manual approvals | Bounds normal coding writes/network to admitted work | Supported native policy; approval handling must be demonstrated in Hermes |
| Repo admission plus patch/log manifest | Prevents accidental wrong-repo work and makes review reproducible | Existing small utility; not a second lifecycle controller |
| Root-owned release and rollback target | Prevents worker modification of trusted code | One reviewed release procedure |
| Single worker initially | Reduces cross-task mistakes and sibling interference | Limits throughput; does not claim adversarial same-UID isolation |
| Custom Docker namespace/mount profiles | Would preserve an extra nested container boundary | Unquantified incremental benefit in trusted single-operator use; exceeds current maintenance budget, therefore omitted |

No incident-rate or monetary risk reduction can be quantified from available evidence. These are concrete authority reductions, not numerical security guarantees. Native sandbox is not a secret-isolation boundary for the trusted model-client process. Strong per-task UIDs, mediated credentials or separate hosts remain upgrades for untrusted repositories/multiple operators, not current prerequisites.

## Ordered next acceptance and deployment slices

1. **Credential-free host candidate:** obtain and pin a complete reviewed Hermes source/dependency release (the live container's revision label alone is insufficient), package the verified Codex software, provide a disabled launch/service candidate and reversible install guide. Keep only CLI engineering facilities; no second messaging gateway. Validate source inventory, dependencies, native profile settings and CLI creation flags without administrator operations. Do not extract live secrets or copy the personal Hermes home.
2. **Disposable dedicated-UID acceptance:** administrator provisions the reviewed account/release and runs model-free initialization and admitted-write/denied-sibling/network tests under that actual UID. Verify private operator/production credentials are inaccessible, Docker socket access denied, effective groups, task cgroup stop, no leftover worker descendants, exact fixture cleanup, and no shared gateway/service change. Avoid `PrivateUsers`, namespace-blocking RestrictNamespaces or hardening settings that silently prevent bubblewrap; test any systemd policy under the real identity. Passing tests on UID 1000 is insufficient.
3. **Full native workflow:** verify Kanban project admission, native worktree creation, worker profile/env, actual tool callbacks and approval handoff, failure/restart evidence and patch export. Begin with one admitted repository and one worker; no concurrency guarantee beyond demonstrated native behavior. Keep service disabled until these gates pass.
4. **Separately authorized canary:** provision the dedicated API identity with operator portal controls; one small coding task, retained usage/patch/validation evidence, human review. No personal login reuse. Activation and credential provisioning are pending, not performed by this investigation.

The next implementation slice is item 1: a credential-free host-native candidate and complete Hermes dependency provenance. It resolves the concrete installation gap while removing nested-container policy work. No immediate operator installation command is requested; first produce a reviewable candidate. GUI, remote interactive handoff and stronger per-task containment can follow the first successful canary.
