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
parent supplies the actual Linear session; its broker reads the integration's
runtime journal and accepts a stable key, observations, reasons, changes,
validation, questions, references and next step. It injects the installed work,
architecture and active attempt. Callers cannot choose work or grant approval.
Text is redacted before staging. Exact replay is safe; changed text under an
existing key is refused. A terminal or unknown session cannot append an active
checkpoint. No private history, execution or Linear credential is exposed.

The runtime applies the recorder's MCP configuration and checkpoint guidance on
both thread start and resume. Before generation, it inspects the actual thread's
MCP inventory and refuses unexpected MCP identities/tools. A missing recorder is
a visible reporting gap. Production uses a protected Unix stream connected to a
separate native coding account. The private HTTP adapter keeps the n8n bridge
credential, runtime journal and intake spool; the coder has its own native home
and provider authentication, without those adapter files or a general history
grant. A systemd accepted service can connect native App Server stdin/stdout to
the Unix stream. The adapter verifies the protected socket's owner and exact
listener UID before sending context. Native authentication is provisioned
separately by the operator. Initialization creates only the adapter journal and
exits; it starts no listener, native process or model.

The coder's MCP process is a thin client of a separate, write-only Unix broker.
Kernel credentials restrict it to the configured native UID. A frozen session
and dispatch binding must match an active retained attempt on every call; stale
clients cannot report into a subsequent turn. The broker supplies work and
architecture context and exposes no private-history read, arbitrary work
selection or execution operation. Existing named-UID ACL helpers grant only
endpoint traversal/connection, with no added group membership. Direct journal
mode and the stdio launcher remain isolated fixture helpers. The production HTTP
entry uses the separate socket transport and broker. Visible result text is also
redacted before transport publication; private native/runtime evidence remains
retained separately.

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

The opt-in `probe_native_checkpoint.py --isolated-containers --binary PATH`
also passes with installed Codex **0.159.0**, executable SHA-256
`d2752c52353401f7f6efbfcea68796f4f7a3d3e4769f5d1da53fa49d4856b72f`.
It creates a synthetic ephemeral native thread and discovers the actual scoped
MCP recorder in a disposable nonroot container with only loopback, no credentials
and no production mounts. It calls **no** `turn/start`. This checks native MCP
configuration/initialization rather than model behavior or paid execution.

`probe_native_isolation.py` additionally passes actual native stdio-over-Unix RPC
and a real MCP tool callback across numeric UIDs **61180/61181** in a disposable
offline container. The native account cannot read the adapter's bridge marker,
journal or spool. Wrong UID, history-method and stale-dispatch calls are refused;
the valid callback stages the exact bound work. No permanent accounts, provider
credentials, production mounts or coding turns are involved. That fixture uses
an ordinary primary group for traversal; actual host named-UID ACLs, systemd
activation and provider authentication remain host acceptance work.
