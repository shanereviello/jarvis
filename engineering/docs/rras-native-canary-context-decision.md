# Canary task context and native lifecycle decision

2026-10-12. Dedicated CLI/systemd sentinel acceptance is operator-reported passed: run 59324c06a5754bcd908504e752fd94a8, UID996, nine checks, zero model/API calls. Preserve its WORK and SOURCE_ROOT. No source/runtime installation or paid execution occurred in this reconciliation.

## Concrete gap

Pinned native source under `/opt/rras-engineering/releases/native-10/hermes` shows:

- `hermes_cli/kanban_db.py`, worker spawn around line10735, constructs query `work kanban task <id>`.
- `agent/codex_runtime.py`, around line755, calls session.run_turn(user_input=user_message), without forwarding the assembled Hermes system prompt or task context.
- `agent/transports/codex_app_server_session.py`, ensure_started around line343 and run_turn around line521, sends cwd at thread/start and the supplied user text at turn/start. No task body or dynamic lifecycle tools are injected there.
- Hermes's ordinary KANBAN_GUIDANCE expects kanban_show and kanban_complete tools. In the deliberately MCP-free App Server profile those Hermes tools are not exported. CLI processing of task-body images does not forward the text body as instructions.
- Native lifecycle expects explicit completion/blocking; successful process exit alone is not task completion. Earlier repository fixtures substituted a child that explicitly called complete_task. Their success is not evidence of model-side context/lifecycle wiring.

This is a demonstrated integration gap, not a reason to restore Phase5B orchestration or enable arbitrary callbacks. Coding sandbox, identity and delivery acceptance remain valid within their recorded scopes.

## Recommended minimum adaptation

Keep the no-MCP lane. Add reviewed **repository instruction metadata** for the disposable canary: AGENTS.md points to the exact admitted task specification and validation command. It explains native board inspection/completion through the installed Hermes CLI from the assigned worktree. Native CLI show/complete is already supported; complete routes the assigned HERMES_KANBAN_RUN_ID through expected_run_id. No new completion controller, lifecycle database or custom state machine is needed. The board is the admitted native writable root already supported by the transport.

Prepare one fresh isolated board/repo, baseline instruction files, one admitted task, and one bounded native-dispatch invocation that stays alive until native worker exit. Acceptance before inference must exercise these native CLI commands through the actual coding sandbox, verify matching task/run completion, reject a stale run, retain the worktree/patch/logs, and preserve timeout evidence. This does not prove the model follows instructions; the separately approved paid canary supplies that final evidence. Explicitly restrict the canary to fixture paths and no remotes/hooks/publication.

Practical cost: a small reviewed task-spec/instruction template and fixture checks; no additional privileged component or long-lived scheduler. Risk addressed: task not understood or worker exits without native terminal status. Limitation: instructions and board write access remain cooperative single-operator controls, not adversarial per-task isolation. This preserves the accepted architecture's scope.

## Alternative and decision

Enable a narrow Hermes MCP lifecycle bridge instead. Before choosing this, verify actual exported tools and approvals: the pinned bridge has a fixed EXPOSED_TOOLS surface and auto-accepts hermes-tools elicitation. A CLI toolset list alone does not establish a narrow MCP inventory. This path requires additional callback authority testing and may need a reviewed upstream configuration/change. Do not enable it merely to make the canary proceed.

**Operator decision:** approve the recommended repository instruction/native-CLI adaptation for the first canary, or select the narrow MCP bridge investigation. Both alter how task context and lifecycle operations reach the coding session. Dependent paid-invocation preparation is stopped until this choice is made. No real-key provisioning or new administrator command is needed for this decision.

## Approved and implemented model-free fixture

Operator approved repository instructions/native CLI. The fixture now exercises actual show/completion through the Codex coding sandbox, retains AGENTS/task metadata in the native worktree, and verifies stale-run refusal. [Dedicated acceptance procedure](rras-native-cli-context-acceptance.md) is the current next step. The decision above is resolved; no MCP bridge or upstream fork is required for this fixture. Model instruction compliance remains for the separately authorized canary.
