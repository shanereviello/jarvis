# Interactive Codex integration design and verified coverage

No hook, skill, plugin, client configuration or model pin was changed in Phase1.
Local read-only inspection found Codex CLI0.159.0 and `hooks` listed stable/enabled.
This does not prove desktop session event delivery in the attached client or that
any engineering-history hook is configured/trusted. No private config or transcript
was read to infer that coverage.

## Supported opportunity versus actual acceptance

Official documentation describes lifecycle command/MCP hooks, trust review, and
SessionStart, Stop, Interrupt, compaction and SessionEnd events. It warns that the
transcript file format is unstable and that background hooks may be cancelled at
session end. Plugin hook scripts must exist in the execution environment and enabling
a plugin does not automatically trust its hooks. Thus a reviewed local integration
is plausible; its actual desktop/server delivery still needs fixture acceptance.
Sources: [Hooks](https://learn.chatgpt.com/docs/hooks),
[plugin packaging](https://developers.openai.com/plugins/build/plugins).

## Capture coverage table

| Trigger | Proposed integration | What is not inferred |
| --- | --- | --- |
| Start / attach | Explicit start/attach command; optional trusted SessionStart helper can offer active context. | A directory match or new session alone does not choose an engineering objective or approve work. |
| Intent / scope | Explicit reviewed form or agent-assisted template submission. | Hooks cannot reliably infer purpose, acceptance criteria or a human approval. |
| Meaningful checkpoint | Explicit client tool after a decision/result; optional Stop/compaction hook sends bounded metadata or reminds client. | Turn stop is not task completion; compaction is not a source change or approval. |
| Git change evidence | Read-only collector resolves selected repo/worktree HEAD, allowed diff stats/digests and dirty-state attribution. | Shared checkout changes may belong to another session; filesystem proximity is not authorship. |
| Validation | Wrap supported explicit checks with exact argv/context/exit/time/tree binding, or import output as a claim. | A tool result copied from chat is not automatically a protected validation observation. |
| Interrupt / crash | Best-effort lifecycle hint plus retained private spool and explicit later handoff. | No clean SessionEnd is guaranteed on crash; missing final record means unfinished/unknown. |
| Close | Explicit completion/handoff action with user review; SessionEnd is a hint only. | No automatic success/merge/deploy from a session ending. |
| Historical session | Explicit source selection, curated import and retrospective label. | No recursive transcript harvesting or fabricated exact source time/session identity. |

## First implementation path

Deliver explicit start/attach/checkpoint/finish/handoff CLI or authenticated MCP
commands before hooks. They submit structured summaries to the selected store; they
never supply shell snippets to a privileged service. Return durable receipt IDs and
recorded/pending state. A later focused skill can guide when to use them; a skill is
not authenticated observation or guaranteed universal capture.

A reviewed hook then records only bounded event metadata (session/turn IDs if supplied,
repository association hint, event name, capture time) to a private spool. Parse only
versioned documented fields, reject unknown oversized payloads, allow event duplicates,
and never use raw tool arguments/prompts/transcript bytes as routine telemetry.
No model turn inside a hook; no recursive hook-triggering action loop. If a summary
needs a model, obtain it in the existing interactive turn and label its provenance.
No new background model spending is authorized by the capture feature.

Require actual attached-client fixture checks for startup/resume/fork, interruption,
compaction, duplicate Stop, server/network outage and crash/no final event. Do not
bypass hook trust or use a permission hook's allow output as a workflow approval.
A hook cannot mint an authenticated human decision. Until accepted, the UI shows
'explicit capture only' rather than promising automatic coverage.

## Ordinary interactive collaboration

Recording does not route interactive Codex through UID996 or the managed launch gate.
A persistent user-selected work context survives session changes, with explicit
revision mapping on resume. Work continues under the client's normal permissions;
merge/deployment rules still apply. Unrecorded intervals are displayed, not silently
reconstructed. If intake is down, preserve a bounded private spool and show pending.
No unavailable history service should trigger coding retries or reread private logs.
