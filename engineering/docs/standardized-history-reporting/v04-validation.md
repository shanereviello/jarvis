# v0.4 source validation — November 7, 2026

The exact human-approved architecture is retained as owned version 4, with all
8 existing work IDs preserved and REV-46–53 updated. REV-54 retains the direct
operator decision as an attributed transcription, not a native app message.
No new architecture agreement is inferred from source tests or Linear state.

This source slice adds inactive n8n workflows, app-scoped transport SQL, a dedicated
Codex signature-verification Worker, and a private Codex App Server adapter. Jarvis
configuration remains unchanged. Old standalone OAuth source is superseded for
installation. Neither source publication nor these results establish deployment.

## Evidence

- Combined history/reporting regression: **865 passed, 1 skipped**. The skipped
  case is the existing opt-in browser acceptance; this slice changes no web UI.
  A legacy Starlette/httpx deprecation warning remains.
- Final focused runtime/registration/n8n tests: **29 passed**, covering actual
  local HTTP, private journal restart, frozen dispatch replay, closed/competing
  adapters, wrong app/issue/design/authority refusal, cancellation, and fixed
  workspace ownership across distinct issues. No real models are called.
- The isolated transport probe executes JavaScript in an existing n8n 2.28.3
  image and SQL in a fresh PostgreSQL 18 container. Both have no network or
  production mounts. Actual admission/follow-up/stop cases, 9 refusal cases,
  generated Code compilation, OAuth actor refusal, Worker HMAC/unchanged body
  forwarding, SQL receipt replay/conflict and prepared workflow queries pass.
  A real database uniqueness check prevents simultaneous runtime dispatches.
  Fixture data/container are discarded; installed images are never pulled.
- The installed Codex 0.159.0 binary generated public protocol schemas without
  starting a model. Initialization, start/resume, turn/start and turn/interrupt
  parameter shapes validate against them. See the companion compatibility JSON.
  Native runtime behavior still needs separately authorized acceptance.
- Exact approved Markdown digest is preserved. Four intentional two-space
  Markdown line breaks are retained; whitespace checks exclude only that
  end-of-line convention and pass for the remaining source.

The broad run preceded final isolated ownership/HTTP safeguards; focused tests
and the transport probe were rerun for those changes. Counts overlap and are not
summed. No new runtime, workflow, credential, migration, tunnel or production
service was installed or activated by this validation.

## Remaining

The admin must create the distinct Codex app and keep secrets private. Its actual
client/actor/credential IDs are not fabricated. Actual isolated n8n import and
workflow execution, credential renewal, runtime recovery/permissions, native
bidirectional handoffs, release packaging and separately authorized deployment/
real interaction checks remain. Artifact byte intake, automatic capture and
observation, reporting UI/curated retrieval and historical architecture closeout
remain unfinished SHRR work. Do not mark the project or SHRR-03 complete.
