# Native session policy checkpoint

2026-10-05. Continues the [dedicated-UID procedure](rras-native-dedicated-uid-operator-guide.md) and [native-first architecture](rras-native-first-architecture-review.md). No installed release, unit, credentials, timer, runtime record or writer fence changed.

## Demonstrated boundary

Operator output records successful native-10 installation with dedicated UID/GID 996, no supplemental groups or sudo, and actual transient-systemd sandbox acceptance. Run `b795b3ec80a2491eafbcb4cc9f90659e` retained under `/var/lib/rras-engineering/acceptance-b795b3ec80a2491eafbcb4cc9f90659e`. All five native sandbox cases passed; zero inference. This is operator-reported host evidence, not a rerun in this pass.

[probe_session_policy.py](../tools/rras_native/probe_session_policy.py) imports the actual pinned Hermes session module in the reviewed disposable dependency environment. **17 checks passed**: native thread-start arguments inject no dynamic tools; missing UI declines command/file approvals; permission changes decline; foreign MCP elicitation declines; unknown requests receive protocol errors; deny/timeout/unknown choices and callback exceptions decline; explicit once accepts. Expected synthetic exception logs are intentional test inputs. [Machine-readable evidence](rras-native-session-policy-evidence.json). Existing focused suite: **33 tests passed**. No server/model process is started by this handler probe; its transport is a recorder. It does not demonstrate a complete live session or approval round trip.

Read-only inspection of root-owned installed `codex/config.toml` confirmed workspace-write, on-request approval, network false, and no MCP server entries. Native session thread/start passes cwd only: Hermes CLI toolsets are not automatically exported as Codex dynamic tools. Effective server-discovered tools/configuration still require a live model-free inventory check under the dedicated identity. Do not equate the five command/exec sandbox checks with full session tool acceptance.

## Concrete approval exception and minimal response

Pinned Hermes automatically accepts `mcpServer/elicitation/request` from `hermes-tools`. Its standard migration helper registers an external Python MCP process providing Hermes tools, including tools beyond coding. These callbacks execute outside the Codex coding sandbox; enabling that bridge adds a separate authority surface. The CLI `kanban, skills` selection alone is not proof of the callback inventory or containment.

Keep that bridge absent for the manual first canary. Native Hermes owns board/worktrees/dispatch outside the model session; Codex provides coding tools inside its sandbox. No custom broker or fork is needed for this lane. Do not run automatic runtime migration or copy personal Codex configuration. Later Hermes callbacks require explicit list-tools evidence, narrow admitted toolsets and separately tested approval behavior before enablement.

The [official App Server documentation](https://developers.openai.com/codex/app-server) describes client-handled server requests and experimental dynamic tools. Current documentation is not proof of pinned 0.159.0 behavior. Check actual session initialization, thread policy and server configuration with isolated homes and no turn/start; do not invoke login or inference to make a fixture pass.

## Next bounded slice

Prepare dedicated-UID live model-free native session initialization/configuration inventory using native environment helpers (no transplant stubs), separate disposable homes and exact evidence paths. Require private Codex home propagation, admitted cwd, workspace-write/network-off policy and zero configured MCP/apps before advancing. Auth-required initialization is a reported pending gate, not authorization to supply credentials or make calls. Keep approvals manual and bypass/yolo settings absent. Then prepare a disposable admitted Git repository, native project/worktree binding, one-pass dispatch command and evidence export. Credential provisioning and the first paid canary remain separately authorized; persistent dispatcher/cgroup worker termination remains the later unattended milestone.
