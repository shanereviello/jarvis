# Automatic runtime reporting

The private Codex runtime can install `runtime_reporting.Reporter` against an
explicit work/architecture configuration and an existing private intake spool.
It freezes a start attempt and checkpoint **before** native generation, records
native thread/Linear session relationships, and records observed running,
uncertain, interrupted, failed and completed states. Native completion does not
close the work item or establish independent acceptance. A history outage or
queue-capacity failure never starts another coding run. Staging failures leave a
sanitized gap in the separate runtime journal.

`session.describe` retains actual source identity and available lineage,
configured model, workspace/host and source version. Unknown parent/fork IDs,
token counts and cost stay null. A thread model is configuration metadata, not
per-turn execution telemetry. A native thread Git SHA is labeled as thread
metadata rather than a fresh checkout audit. Optional attempt and validation
fields can retain managed task/run, worktree, command, criterion, environment,
code commit and output digest without rewriting earlier records.

`runtime_checkpoint_mcp.py` exposes only `engineering_checkpoint`. The trusted
parent supplies the actual Linear session; the tool reads that integration's
runtime journal and accepts a stable key, observations, reasons, changes,
validation, questions, references and next step. It injects the installed work,
architecture and active attempt. Callers cannot choose work or grant approval.
Text is redacted before staging. Exact replay is safe; changed text under an
existing key is refused. A terminal or unknown session cannot append an active
checkpoint. No private history, execution or Linear credential is exposed.

The runtime applies the recorder's MCP configuration and checkpoint guidance on
both thread start and resume. Before generation, it inspects the actual thread's
MCP inventory and refuses unexpected MCP identities/tools. A missing recorder is
a visible reporting gap. The HTTP entry point requires a separate private
`STATE/codex-home`; it never inherits the operator's personal Codex home. Native
authentication is provisioned separately by the operator. The initialization
operation creates only the journal and empty native home, then exits; it starts
no listener, native process or model.

Actual native source paths returned for a configured thread are registered as
immutable, private selected-file jobs under the installed source root. This
registration does not open/export the file or scan other sessions.
`runtime_capture_jobs.py` validates registrations against the installed work,
exporter, authorization and Unix transport policy. It visits up to 32 sources
per pass, rotates fairly through at most 4,096 retained registrations and flushes
the shared queue even before a native source becomes available. Invalid entries,
changed policy, lock contention and capacity stop the pass with retained sources
and pending data. No native source, history item or registration is automatically
deleted. An incomplete cursor temporary file is a stop/report condition for an
operator to inspect. Collection and delivery run independently of coding.

Source fixtures cover start-before-generation, terminal states, outage replay,
capacity gaps, exact attribution, redaction, MCP SDK stdio discovery/call/refusal,
unexpected MCP identity refusal, selected-file confinement and fair rotation.
These are model-free fixtures. Production activation, native authenticated
runtime behavior, background timer installation and paid interaction acceptance
remain separate. Existing interactive desktop chats still use explicit recording
until a selected-source integration is installed for that surface.

The configuration uses supported [App Server thread and MCP APIs](https://learn.chatgpt.com/docs/app-server)
and [stdio MCP settings](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
Compatibility is pinned to the reviewed local release; current documentation
alone does not establish the installed binary's behavior.
