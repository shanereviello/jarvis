# Standardized History Reporting Format and Rules

Architecture document — **draft v0.3, for human review**  
Date: November 7, 2026, America/New_York  
Proposed repository: `jarvis`  
Purpose: durable engineering reference and debugging, with Jarvis/Hermes as the overall assistant and Codex as the coder/engineer, independently reachable in Linear.

**Proposed direction:** give **Jarvis (Hermes)** and **Codex** separate, named Linear agent identities. The operator can communicate with either directly; the agents can hand off work through Linear while retaining the same project/work identity. Jarvis is the overall assistant; Codex is the coder/engineer and can work directly with the operator on architecture and approvals without Jarvis as an intermediary. Evaluate SpecStory and Entire for capture and retain the Jarvis-owned history database and web UI. Human oversight remains focused on architecture and material deviations.

The operator largely agreed with [reporting-rules draft v0.2](STANDARDIZED-HISTORY-REPORTING-FORMAT-AND-RULES-ARCHITECTURE-DRAFT-v0.2-20261107.md) and requested this explicit revision. Both v0.2 and [draft v0.1](STANDARDIZED-HISTORY-REPORTING-FORMAT-AND-RULES-ARCHITECTURE-DRAFT-v0.1-20261106.md) remain unchanged. This is separate from the already completed **Engineering History Workspace v0.2** effort. This file is the new review candidate; it does not designate itself as governing or authorize implementation.

Only research and this document were produced for this revision. No collectors were installed, Linear objects changed, history records created, production services inspected or modified, credentials read, or paid agent runs started. Product behavior below is documented behavior or source inspection, not an end-to-end compatibility test on the installed system.

## 1. Purpose and success criteria

The system should let the operator and Jarvis reconstruct engineering work after the original conversation has ended. It should preserve intent, alternatives, failed attempts, changes, validation, and operational outcomes, with enough source evidence to distinguish a reported conclusion from a verified result.

The two original problems remain central: recording did not start automatically when interactive work began, and several independently assessable deliverables were represented by one conversation-sized work item. Session capture addresses the first problem; explicit architecture work items and consistent Linear/Jarvis identity address the second.

Success means answering these questions with dated records and source references:

1. What problem was being solved, and what architecture did the human agree to?
2. What distinct work items were planned, and which actually happened?
3. Was work requested directly from Codex or handed off by Jarvis? Which agent performed each action?
4. What was tried, what failed, and why was the final approach selected?
5. Which code, tests, review, merge, deployment, and runtime checks support the result?
6. What is unknown, missing from capture, deferred, or inconsistent with the plan?
7. Can the operator discuss work and architecture decisions directly with either named Linear agent, including Codex when Jarvis is unavailable?

The main deliverable is reliable engineering knowledge. A board status or a saved transcript alone is insufficient to establish completion.

## 2. Decisions carried into this proposal

| Area | Direction |
| --- | --- |
| Project architecture | Every project has a versioned architecture document, without exceptions. A human agrees to the governing version before implementation. The document contains the corresponding work breakdown. |
| Organization | Linear is the shared working project/issue and agent-conversation interface. Reuse compatible parts of the existing Hermes connection, with two distinct registered agent identities. |
| Agent roles and alignment | Jarvis/Hermes is the overall assistant; Codex is the coder/engineer. Each is separately mentionable and delegatable in Linear, with its own actor identity, sessions, and responses. Shared project/work identity does not merge the agents. |
| Direct Codex path | The operator may start and continue with Codex directly in Linear or the existing interactive coding surface, including architecture review and deviations. Jarvis participation is optional. |
| Agent handoff | Jarvis and Codex exchange explicit context and responsibility through the mapped Linear issue. A handoff does not create a second execution work item or imply human approval. |
| Capture | Evaluate SpecStory and Entire. Prefer an existing capture mechanism over building another general recorder. |
| Human oversight | Review the initial architecture and material architecture deviations. Do not require approval for every work item, checkpoint, command, test, or handoff. |
| History ownership | Keep the private Jarvis history service, database, retained documents, and developing read-only web UI. |
| Existing grouping | One repository/category per project; one primary project per assigned work item. `jarvis-non-git` remains the sole non-Git category. Baselines remain Git commits. |
| Exclusions | No n8n/Activepieces or other formal workflow engine, new autonomous scheduler, custom approval dashboard, or replacement coding runner. |

Existing execution, spending, repository, merge, and deployment permissions remain in force. Architecture agreement defines intended work; it does not grant new machine privileges or silently remove existing operational controls.

## 3. Research findings and capture recommendation

### 3.1 SpecStory and Entire

| Question | SpecStory | Entire CLI |
| --- | --- | --- |
| Documented approach | Exports native agent conversations to local Markdown. | Hooks connect agent sessions with Git checkpoints and commits. |
| Codex | Documented CLI integration reads existing session history and supports background watching. Actual desktop/remote layouts still require testing. | Codex is listed as supported. Actual desktop and managed-worker behavior still require testing. |
| Existing conversations | Explicit export of previously created Codex sessions is documented. | Do not assume arbitrary old-chat backfill; test the supported checkpoint/session recovery paths. |
| Storage | Markdown exports; custom output location is available. | Local metadata plus checkpoint Git storage and commit references. |
| Main fit | Capturing conversations, including research that produces no commit. | Tracing committed code back to agent evidence. |
| Main concern here | Export completeness and mapping across sessions/projects. | Hook compatibility and preventing unintended transcript publication to Git remotes. |
| Hermes | Native support was not established by the documentation reviewed. | Native support was not established by the documentation reviewed. |
| Cost boundary | Free, open-source CLI; hosted services are a separate choice. | MIT-licensed CLI; hosted forge/memory features are a separate choice. |

Sources: [SpecStory overview](https://docs.specstory.com/), [Codex integration](https://docs.specstory.com/integrations/codex-cli), [CLI reference](https://docs.specstory.com/integrations/terminal-coding-agents/usage), [Entire CLI](https://github.com/entireio/cli), and [Entire session/checkpoint architecture](https://github.com/entireio/cli/blob/main/docs/architecture/sessions-and-checkpoints.md).

**Provisional recommendation: evaluate SpecStory first as the primary Codex capture source, with Entire as the comparison candidate for stronger commit correlation.** Do not enable both by default. Select one after demonstrating the required coverage, or record that neither meets it.

This is an architectural preference, not a completed benchmark. Entire's support for commit-less snapshots means it must not be dismissed simply as commit-only; the test must establish what is retained automatically for research and interrupted sessions. Documentation and implementation evolve, so evaluation records must pin exact versions and settings.

### 3.2 Capture privacy and compatibility

SpecStory documents optional cloud synchronization and configurable analytics/telemetry. Entire documents checkpoint uploads to Git remotes and best-effort redaction. A separate Git ref is still publication of transcript content. [SpecStory privacy](https://docs.specstory.com/privacy), [SpecStory configuration](https://docs.specstory.com/integrations/terminal-coding-agents/usage), [Entire security](https://docs.entire.com/security).

The proposed evaluation therefore uses disposable repositories, synthetic transcripts, local output, no cloud account, disabled optional telemetry, and no transcript pushes. Verify those settings and actual behavior for the selected release before any real-history pilot. Never install hooks into the production checkout as part of research.

Native session files stay under their existing agent owner. Export only the selected engineering sessions. Collectors do not need provider credentials, another agent's authentication files, or privileged workflow journals. Redaction reduces exposure but does not prove that arbitrary transcript content is safe to publish.

### 3.3 Hermes evidence

Current Hermes documentation describes native session persistence, search, and stored tool interactions. These are useful existing sources; their current upstream layout is not proof of what this installation runs. [Hermes sessions](https://hermes-agent.nousresearch.com/docs/user-guide/sessions), [session storage](https://hermes-agent.nousresearch.com/docs/developer-guide/session-storage).

Inspect the installed version and supported read/export surface during implementation. Prefer an existing supported export or a small read-only normalizer over changing Hermes internals. For Hermes-coordinated Codex work, capture the coordinator session and the worker evidence separately. Existing managed journal/export records remain the source of protected execution facts.

If complete Hermes session capture requires a substantial new recorder, do not expand this project silently. Deliver the agreed structured reporting and existing managed evidence, display the capture gap, and bring that additional scope back for architectural review. Enabling unattended Hermes execution remains outside this project.

### 3.4 Capture selection test

Run both candidates against the same model-free fixtures and expected results. Use a separately authorized real-session pilot only after fixture success.

| Required case | Evidence to retain |
| --- | --- |
| Existing and newly created Codex session | Expected exchanges, identities, timestamps, and export contents; no manual request to record each turn. |
| Desktop/CLI and remote-workspace layouts actually used | Exact supported paths/formats and an explicit pass, failure, or unsupported result for each surface. |
| Research without edits or commit; interruption before finish | Recoverable source evidence and honest partial/final status. |
| Resume, compaction, compression, or source rotation | Preserved lineage, missing ranges if any, and repeatable restart behavior. |
| Two projects sharing one repository; a work switch in one chat | Explicit work associations; no assignment based solely on repository or time proximity. |
| Managed worker leaves changes uncommitted | Evidence survives worker cleanup and links to later publisher/validation records. |
| Handoff from Hermes to Codex | Distinct coordinator/worker identities connected to one work item. |
| Repeated export or lost intake response | No duplicate sessions, work items, or history events. |
| Privacy and hook coexistence | No unexpected upload, source change, damaged existing hook, or credential capture. |
| Export portability and resource use | Independent local readback, practical storage/CPU behavior, pinned configuration, and uninstall/recovery notes. |

Mandatory selection conditions are coverage of the actual work surfaces, private export, recoverability, and compatibility with current development controls. Prefer the least additional machinery among candidates that meet those conditions. A failure of both is a decision point, not authorization to build a replacement capture platform.

## 4. Components and ownership

```mermaid
flowchart LR
    Human[Operator] --> Linear[Linear projects, work and architecture review]
    Linear <--> JA[Jarvis Linear agent adapter]
    Linear <--> CA[Codex Linear agent adapter]
    JA <--> Hermes[Jarvis / Hermes overall assistant]
    CA <--> Codex[Codex coder / engineer]
    Human <--> Direct[Existing direct Codex interaction]
    Direct <--> Codex
    Hermes --> HS[Existing Hermes session evidence]
    Codex --> Capture[Selected capture tool]
    HS --> Normalize[Scoped intake and normalization]
    Capture --> Normalize
    Linear --> Observe[Scoped Linear observation]
    Observe --> Normalize
    Journal[Existing protected journal exports] --> Normalize
    Normalize --> History[Jarvis private history service]
    History --> DB[(Owned database and private evidence storage)]
    History --> Web[Existing read-only web UI]
    History --> Curate[Existing curated publication boundary]
    Curate --> Reader[Jarvis or Hermes history retrieval]
```

The two Linear adapters represent independently routed agent identities; they may share transport code but cannot depend on Jarvis to deliver Codex messages. Linear is the shared conversation/handoff surface. The direct Codex path also remains available. These arrows describe proposed integration, not new permissions: Hermes does not acquire the private database/socket, and the browser does not become a writer.

| Information | Authoritative location / responsibility |
| --- | --- |
| Current planned work, issue ownership, discussion, and board status | Linear. |
| Named agent participation and incoming message routing | Separate Jarvis and Codex Linear app identities and adapters; each response is attributed to its actual agent. |
| Exact retained governing architecture, designation history, Git baselines, historical project membership | Existing Jarvis project/history service. |
| Architecture drafting/review presentation | Markdown files and/or Linear document/resources; publication copies reference the retained version. |
| Native conversation | The original agent store; an export is evidence derived from it. |
| Retained engineering evidence and historical observations | Jarvis-owned storage, with immutable manifests and provenance. |
| Code and PR contents | Git/GitHub. |
| Protected execution, validation, and publication facts | Existing trusted records and their explicit exports. |
| What an agent may retrieve | Existing curated-history boundary and explicitly authorized scopes. |

Linear is the working coordination interface; Jarvis preserves historical observations and evidence. Neither side silently overwrites the other's historical records. Linear deletion, renaming, or an outage does not delete the owned engineering archive.

## 5. One work model across Hermes and Codex

### 5.1 Identity and decomposition

A project has one stable Jarvis project ID and one mapped Linear project UUID. A distinct engineering deliverable has one architecture plan ID, one Linear execution issue UUID, and one Jarvis work ID. Human-readable Linear identifiers and URLs are display references, not durable identity keys.

The mapping includes the Linear workspace/team scope, repository/category, architecture document/version/digest, and history work revision. Do not create a second project or work item when the agent changes.

An independently testable capability, investigation result, or corrective deliverable deserves a work item. Commands, retries, commits, checkpoints, and individual chat turns normally do not. An attempt is activity within a work item; a session is a conversation that can span several work items.

Architecture-review/deviation issues are **decision records**, distinguished from execution issues. They do not inflate delivered-work counts. Parent grouping issues need not become duplicate Jarvis work items. The explicit execution-issue mapping determines counting.

Plan refinements inside already agreed scope may split an oversized deliverable without another human approval: retain the parent plan entry, add traceable child IDs, and preserve the old mapping. New outcomes or changed architectural commitments use the deviation process. Never retire a plan ID and reuse it for unrelated work.

### 5.2 Two named agents and direct communication

**Separate Linear agents are required in this version, not optional future integration.**

| Agent | Primary role | Operator interaction |
| --- | --- | --- |
| **Jarvis** (Hermes) | Overall assistant: understand broader intent, organize and research efforts, maintain continuity, coordinate work, and use its existing assistant tools within their permissions. | Address Jarvis directly for assistant work, context, planning, or coordination. Jarvis can prepare a bounded engineering handoff to Codex. |
| **Codex** | Coder/engineer: investigate technical problems, develop the architecture, implement agreed work, validate results, explain deviations, and report engineering evidence. | Address Codex directly for engineering work or architecture decisions. Codex asks the operator directly for needed agreement; it does not require Jarvis to relay or endorse the exchange. |

These are distinct app actors, not labels on an operator account, two issue queues, or an alias that forwards every request through Hermes. The operator remains the human decision maker. Jarvis is not an additional approver above Codex, and Codex cannot approve its own architecture or material deviations.

| Scenario | Required behavior |
| --- | --- |
| Operator → Codex in Linear | Codex receives the addressed message, replies as Codex, and works against the mapped issue/architecture. Jarvis need not run, receive the message, or participate. |
| Operator → Codex in the current interactive coding style | Continue directly. Associate relevant context, reports, and decisions with the same Linear/Jarvis records; adopting Linear does not force the conversation through Jarvis. |
| Operator → Jarvis | Jarvis answers as the overall assistant. Engineering execution is normally handed to Codex when it needs the coder/engineer role. |
| Jarvis → Codex | Jarvis records the bounded request and handoff on the existing issue, directs it to Codex, and transfers the active engineering responsibility. Codex acknowledges as Codex. |
| Codex → Jarvis | Codex reports an engineering result or requests assistant context using the same issue or an explicitly linked context issue. Jarvis responds as Jarvis; this does not automatically return engineering ownership to Jarvis. |
| Codex needs architectural agreement | Codex presents the exact change to the operator in its own Linear conversation or direct interaction and waits only on affected work. No Jarvis mediation or second signoff is required. |
| Jarvis unavailable | Direct operator/Codex conversation, decisions, and authorized engineering work remain usable. |

A shared issue can contain exchanges with both agents. Human ownership, the current delegated agent, and historical contributors are different concepts. Use the platform's supported delegation model and an explicit current executor; do not assume one issue can have two simultaneous active delegates. The human may talk to either agent without transferring execution responsibility on every message.

### 5.3 Handoff contract

A handoff preserves the project/work/plan IDs, issue UUID, governing architecture version/digest, current work revision, current code/branch/worktree, useful evidence, remaining work, and the requested recipient/action. Record sender and recipient agent IDs plus the source message/session reference. On receipt, the target acknowledges the handoff and records its own session/attempt binding. Retransmission must not start a second attempt or create duplicate issues.

A handoff is the transfer of context or agreed work, not a new approval gate. Routine in-scope handoffs need no extra human approval. A new outcome or material design change still goes to the operator. Stop the prior executor's overlapping edits before the recipient starts; a request for advice does not transfer ownership. Preserve the distinction between requested, accepted, and completed handoffs.

Only directed mentions, delegated work, or messages addressed to an existing agent session activate the matching agent. Do not make both agents react to every comment. Ignore self-authored echoes and replayed events; correlate handoffs and bound automatic replies so the agents cannot create an endless conversation loop. Native agent-to-agent mention/delegation behavior must be tested. If Linear does not emit the required event for an agent-authored handoff, use the same thin adapter to deliver a correlated request through a supported API path and retain its Linear reference; do not require the operator to manually repeat every handoff or claim that an ordinary comment guarantees delivery.

### 5.4 Linear agent integration and attribution

Linear documents mentionable/delegatable app actors using app authentication and agent-session event delivery. Its developer guidance separates the human assignee from the agent delegate. This supports the proposed identity model; actual installed capability is untested. [Agent setup and authentication](https://linear.app/developers/agents), [assignment/delegation](https://linear.app/docs/assigning-issues).

Use two separately registered Linear app/agent identities with distinct names, actor IDs, and credentials. Keep scopes limited to the selected workspaces/teams and required actions. Reuse an existing integration where it provides the required identity and behavior. The current Hermes MCP connection alone is not evidence that Jarvis is already a registered Linear app actor. The inspected repository gateway supports issue operations, comments, relations, and links; it does not establish either agent registration or incoming message delivery.

A minimal message/session adapter connects each Linear identity to its corresponding runtime. It receives and validates agent events, acknowledges intake, binds issue and agent-session context, delivers messages to the addressed runtime, and publishes progress, questions, and results under that agent's identity. It may use shared infrastructure, but Codex routing cannot require Hermes orchestration. Existing outbound MCP/API access can still support work organization; it is not by itself an incoming communication channel. [Linear agent interaction](https://linear.app/developers/agent-interaction), [Linear MCP](https://linear.app/docs/mcp).

The adapter must identify the configured Codex backend and its supported session-resume/message surface. Do not assume a Linear mention can inject a message into this exact running desktop conversation. If the runtime requires a separate Codex session, create an explicitly linked continuation with the same work identity and a retained handoff. The operator must be able to reply and give architecture decisions directly to that Codex session through Linear. A link that merely opens an issue or a silent export is insufficient to satisfy the communication requirement.

A sandboxed managed Codex worker receives admitted issue/architecture context and leaves evidence for its scoped adapter; it does not receive either agent app's credentials or an operator credential. The Codex adapter publishes the worker's engineering updates as Codex. Jarvis-owned coordination remains attributed to Jarvis. Direct interactive Codex reports can be associated with the same Codex identity through its authorized adapter; do not silently present user-token MCP writes as authenticated app-originated actions.

Agent-session events require an authenticated, signed webhook route or a supported integration that provides equivalent delivery. This is a narrow addition to the earlier polling-only direction for incoming agent communication; passive history observation can remain polling-based. Pin the runtime, transport, and session-continuity choices during implementation and demonstrate them before real use. Receipt of an event admits a message; it does not grant new paid-run, host, merge, or deployment authority. This is not a new generic workflow engine or unattended scheduler.

Put the common reporting convention in repository guidance read by both agents, with role-specific instructions and the agreed architecture/work context delivered to each runtime. Do not rely on arbitrary MCP issue reads automatically including Linear's agent guidance. [Linear guidance](https://linear.app/docs/agents-in-linear), [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Hermes context files](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files).

Record Linear app/actor IDs, Linear agent-session/activity IDs, native runtime session IDs, coordinator/executor, and submitting service principal separately. An agent's own message cannot establish human agreement. Existing actions performed through an operator credential retain their attribution limits; missing identity remains unknown. The owned archive keeps the provenance of direct operator decisions as well as agent handoffs.

## 6. Lightweight architecture oversight in Linear

### 6.1 What Linear provides

Linear has project documents with version history, issue templates, comments, and configurable issue/project statuses. These can present a review request without another application. Its GitHub reviews concern pull requests; they are not proof of approval of a separately identified architecture. [Documents](https://linear.app/docs/documents), [templates](https://linear.app/docs/issue-templates), [issue statuses](https://linear.app/docs/issue-property), [project statuses](https://linear.app/docs/project-status), [PR reviews](https://linear.app/docs/diffs).

**Proposed convention:** one `architecture-decision` issue for each version or bundled deviation requiring human agreement, using the existing team workflow where practical. Its contents identify the project, exact proposed architecture version/digest, readable content, change summary, affected plan IDs, and the decision requested. A single decision may approve several related architectural changes.

Statuses such as `Awaiting architecture review` and `Resolved`, plus labels, make these requests easy to find. They are coordination aids, not a new execution-enforcement service. No per-test, per-command, or per-checkpoint review issues are created.

### 6.2 Agreement and version handling

1. Retain the candidate Markdown version in Jarvis and link it from the Linear review issue. Linear may hold a convenient draft copy, but the decision identifies the exact retained bytes.
2. The operator gives an explicit decision, preferably a comment identifying the version and digest. This can be a direct reply to Codex in Linear, a direct operator/Codex conversation such as the current interaction, or an operator/Jarvis exchange. Retain the source reference; Jarvis forwarding or countersigning is never required for a direct Codex decision.
3. Record that decision and explicitly designate the agreed version through the existing operator/history interface. This remains a lightweight recording operation, not a new approval engine.
4. Link the decision and governing version from the Linear project and execution issues. Work proceeds under that agreement without repeated approvals. Codex can receive and record the operator's decision through the authorized path without waiting for Jarvis to relay it.

If a connector acts as the operator, an imported comment has the connector's attribution limits. Where human authorship cannot be independently established, retain an operator attestation through the existing operator interface; do not elevate an agent-written comment into human agreement. No autonomous status-to-approval conversion is proposed.

A later edit, a resolved comment, a reaction, or moving an issue to Done does not change the agreed version. New drafts remain drafts. Documentation-only corrections may be saved with their change classification while the preceding agreed design continues to govern. Material changes require human agreement before the affected implementation proceeds. Closeout retains an as-built reconciliation and any decisions that explain differences.

### 6.3 What needs the human's attention

| Situation | Behavior |
| --- | --- |
| Initial architecture | Obtain agreement once before implementation. |
| Change to outcomes, exclusions, data ownership, external publication, significant dependencies, trust boundaries, public interfaces, or important storage/retention behavior | Present a material deviation with options and consequences. Pause only affected implementation; continue independent in-scope work. |
| Refactoring, routine tests, retrying a failed test, implementation detail within agreed boundaries | Proceed and record useful engineering evidence. |
| Breaking one large item into equivalent child deliverables within the same accepted scope | Update the work mapping with a reason; no new approval solely for decomposition. |
| Bug discovered during implementation | Fix within the agreed acceptance scope; use a separate corrective item when independently assessable. Escalate if the solution changes architecture materially. |
| Merge, deployment, paid execution, or privileged action | Follow the existing authority for that action. Linear status does not replace it. |

Every project, including non-Git and historical projects, still needs an architecture document. Retrospective documentation must label what is reconstructed and what was not agreed at the time. Do not manufacture past approvals. Existing projects with missing documents remain visible as incomplete documentation; remediation is explicit and does not erase their history.

## 7. The engineering record to preserve

### 7.1 Data and relationships

The following is a logical target, not a claim that these fields already exist in the current contracts.

| Record | Minimum useful content |
| --- | --- |
| Project / work mapping | Stable IDs, scope, Linear UUIDs/URLs, plan ID, work revision, architecture pin, mapping change reason. |
| Session association | Named agent and Linear app/actor ID, Linear agent-session/activity IDs, native runtime session ID, parent/resume lineage when available, host/workspace identity, capture source/version, and association to work/attempt. |
| Attempt / handoff | Coordinator if present, executor, sender/recipient agent IDs, directed request and source reference, requested/accepted/completed state, attempt ID, managed task/run IDs where applicable, start/end or interruption, previous attempt, branch/worktree and Git baseline. |
| Engineering checkpoint | Problem/context, observation, approach or decision and rationale, meaningful change, validation, failures, unresolved questions, evidence references, next useful step. |
| Validation evidence | Criterion, command/test identity, code revision, actual result, relevant output/artifact digest, environment and provenance limits. |
| External observation | Linear object/version or content digest, source/observed times, observed actor, relevant issue state or discussion, import identity. |
| Architecture decision | Exact version/digest, material delta, affected work, decision/source, human-attribution basis, designation reference, and the direct agent/conversation receiving the decision. Jarvis involvement is optional. |
| Capture artifact | Source identity/range, immutable exported bytes or chunk references, SHA-256, format, size, capture time, redaction profile, coverage and limitations. |
| Outcome | Delivered/failed/deferred/cancelled state for the exact work revision, acceptance evidence and open limitations. Merge/deploy/runtime facts remain separate linked evidence. |

One project contains many work items; one work item can have many attempts and sessions. A session can contribute to several work items, using explicit message/turn ranges where the source supports them. Otherwise label the link as session-level context, not proof that every exchange belongs to every linked work item.

Preserve source occurrence time separately from capture/import time. Unknown tokens, cost, timing, model, or identity stay unknown. Do not sum coordinator and worker counters without checking whether one already includes the other. Missing tool output is a coverage limitation, not an invented successful result.

### 7.2 Reporting cadence

At work start, establish the issue/work/architecture context and record a starting checkpoint automatically through the integration. Capture conversation evidence in the background. Agents contribute concise structured checkpoints after a meaningful finding, failed approach, design decision, validation result, handoff, or interruption—not after every shell command.

At finish or pause, record what changed, what was validated, remaining uncertainty, and the next step. A crash can leave the last captured exchange and an interrupted attempt without a fabricated completion report. Normal reporting does not require the user to ask to create history.

| Reporting field | Purpose |
| --- | --- |
| Context and work references | Identify the exact deliverable and agreed design. |
| Observation / result | State what actually happened. |
| Reasoning / alternatives | Explain why this approach was chosen and what was rejected. |
| Change | Describe the code, configuration, document, or operational effect. |
| Validation and evidence | Link the relevant proof and its limits. |
| Open questions / next step | Preserve continuity for another session or agent. |

Session transcripts are evidence of visible exchanges, not access to private internal model reasoning. Structured explanations are attributed engineering reports, not automatically verified facts.

## 8. Intake, storage, synchronization, and recovery

### 8.1 Reuse and additive extension

Keep the existing service-owned SQLite database, scoped Unix API, immutable work/project/scope events, exact document versions, receipts, and read-only dashboard. The inspected source is `705f69c057a1e2b6e134d61a69519c409928425d`; the operator previously reported production merge `354a893999b5006bdf3c31175f4e52d8d0306478` and schema version 3. These are source/report baselines, not a fresh production audit or this project's selected Git baseline.

Existing contracts have strict fields and bounded request sizes. Implement new mappings, attempts, capture manifests, and decision observations through explicitly versioned additive contracts/tables where needed. Do not hide structured relationships in narrative strings or bypass the service to insert database rows. Preserve previous bytes, receipts, document versions, and signed snapshot behavior.

New historical views must pin the new record streams and exact artifact revisions as well as the existing work/project/scope boundaries. Older signed views must remain reproducible and represent the new streams as unavailable at that boundary; never join an old closeout to today's mappings or captures. Read projections and indexes remain rebuildable from retained records.

Large exports belong in service-owned private evidence storage with immutable manifests referenced from the database. Final path, size/chunk limits, quotas, migration version, and backup integration are implementation details to specify in the intake contract. Existing small work/document requests must not be silently overloaded with entire growing transcripts.

Retain source-native files under their original owner, normalized/redacted engineering exports in owned evidence storage, and structured history in the database. Linear receives concise context, decisions, and links rather than full transcripts or raw logs. Repository commits contain source and appropriate documentation, not private session exports.

### 8.2 Delivery and association

Use a durable local spool and stable source-event keys. A repeated identical export returns its existing receipt; a changed export creates a new immutable artifact revision. Appending to a growing session must not rewrite previously retained evidence. Capture cursor, parsed range, artifact digest, and intake receipt make replay auditable.

Explicit issue/work context determines association. Repository identity alone is insufficient because several projects may share a repository. Unknown associations stay in a visible pending/unmapped view. Correcting an association appends a correction; it does not rewrite the original import.

### 8.3 Linear synchronization

Start with an outbound, scoped polling adapter using a supported authenticated read path for the selected workspace/team/projects. Reuse the existing gateway when its actual operations and pagination are sufficient; otherwise use a narrow, separately configured API reader. Do not automate a desktop agent session as the synchronization daemon.

Import relevant object snapshots/discussion with stable IDs and content digests. Follow pagination, preserve source and observation times, tolerate overlap, and reconcile by object identity. Polling cannot promise every intermediate edit or capture a comment deleted between polls; label this limit. Passive history observation does not itself require a public webhook endpoint. Separately, the two interactive agent identities require the native agent-event delivery path described in Section 5.4, with signature/identity checks, durable delivery IDs, replay protection, and a clear mapping to the target app/session. Capture those exchanges into history without making the history poller a worker launcher. [Linear webhooks](https://linear.app/developers/webhooks).

Current issue state remains Linear-owned. The history observer appends observations; it does not push status changes back or launch work. Jarvis and Codex make ordinary coordination updates through their separately attributed adapters/tools. Keep incoming agent-event delivery separate from passive history observation. Bookmark/attachment creation and mapping bootstrap use repeatable lookup-before-create behavior, with reconciliation of uncertain writes rather than creating duplicate issues or delivering a handoff twice.

### 8.4 Failure behavior and protection

If history delivery is unavailable, queue evidence durably, show pending/failed delivery, and continue already authorized in-scope work where the context remains known. If Linear is unavailable, use the last exact saved context for current work and queue coordination updates; direct operator/Codex work remains possible. Do not guess a new assignment or architecture decision. If Jarvis or its adapter is unavailable, Codex's separate path remains usable; if Codex is unavailable, Jarvis may report the outage but must not impersonate a Codex response. Missing governing agreement prevents affected implementation, while research and draft preparation can continue.

Do not silently discard data when storage is full. Stop capture cleanly, report the lost/uncaptured interval, and preserve existing evidence. Initial policy retains ingested engineering evidence without automatic deletion; monitor usage and bring retention changes back as an architectural decision. Backups must include both database and referenced artifacts; this document does not claim the earlier deferred backup/restore work has been completed.

Imported text is untrusted evidence, not new agent instructions. Keep credentials out of exports, restrict paths and scopes, render transcript content as text, and refuse arbitrary artifact-path/URL access. Preserve current authentication and browser failure-clearing behavior. No general private-history mount or new privilege is given to Hermes.

## 9. Web UI and agent retrieval

Retain scope → project → work and the existing five project tabs. Add focused reference features instead of another task board or approval editor.

| Existing area | Proposed addition |
| --- | --- |
| Project Overview | Linear project link, governing architecture and human-agreement source, planned/mapped work counts, and capture/sync freshness. |
| Project Work | Architecture plan ID, Linear issue link, named active agent/delegate, optional coordinator, current work revision and latest meaningful result. Distinguish decision/grouping issues from execution work. |
| Architecture | Existing exact versions/diffs plus decision/deviation links and coverage of the architecture work breakdown. |
| Baselines | Preserve Git-only versions; connect relevant attempts and deployment evidence without inferring that every commit was deployed. |
| Project History | Mapping changes, Jarvis/Codex handoff requests and acknowledgments, direct operator/Codex architecture decisions, imports, closeout, and outstanding capture gaps with source attribution. |
| Work Timeline / Evidence | Attempts, session lineage, failure/decision/validation checkpoints, immutable export references, and capture completeness. |

The browser remains read-only. Open Linear for coordination and human discussion. Never label an issue status as verified deployment or an agent-authored decision as authenticated human approval.

Jarvis retrieval should return concise engineering answers with exact project/work/architecture/evidence references. Reuse the curated publication boundary: the operator's private archive is not automatically made available to Hermes. Establish a reusable publication profile for approved structured fields within selected projects, so normal safe summaries can be published without reviewing every checkpoint individually. It must preserve withdrawal, scope checks, generation semantics, and exclude full transcripts by default. That profile is part of the reviewed implementation, not permission granted by collection alone.

Acceptance must demonstrate retrieval through the actual allowed MCP surface, rather than only browsing the operator UI. Broader transcript access or semantic/vector infrastructure is deferred.

## 10. Work breakdown for this project

These are the proposed execution deliverables to appear in this architecture, Linear, and Jarvis history. `SHRR-xx` values are stable **plan IDs**, not existing Linear issue identifiers. Linear UUIDs and Jarvis IDs are assigned and recorded during authorized setup. This drafting session has not created those objects.

| Plan ID | Deliverable | Acceptance result | Dependency |
| --- | --- | --- | --- |
| SHRR-01 | Capture comparison and selection | Pinned SpecStory/Entire fixture results, real-surface coverage matrix, private-output proof, selection rationale, and Hermes gap disposition. Research in this draft is an input, not completed acceptance. | Reviewed architecture |
| SHRR-02 | Linear organization and architecture-review convention | Project/issue templates, plan mapping, decision/deviation examples, and usable human review with no routine implementation approval queue. | Reviewed architecture |
| SHRR-03 | Two Linear agent identities, direct communication, and handoff | Separate registered Jarvis and Codex actors; scoped message/session adapters; direct conversations and Codex architecture decisions; both handoff directions; correlated runtime sessions, replay/loop prevention, and continued Codex operation when Jarvis is unavailable. | SHRR-02 |
| SHRR-04 | Owned history relationships and evidence intake | Versioned additive contracts, immutable mappings/attempts/artifacts, privacy, receipt/replay behavior, and compatibility with existing records/snapshots. | SHRR-01; SHRR-02 |
| SHRR-05 | Capture and Linear observation integration | Automatic selected-source capture/intake, scoped Linear observations, durable delivery, restart recovery, freshness/gap reporting, and no work launching. | SHRR-03; SHRR-04 |
| SHRR-06 | Reference UI and curated retrieval | Focused UI additions and actual MCP retrieval of approved engineering summaries with citations and maintained access boundaries. | SHRR-04; SHRR-05 |
| SHRR-07 | Existing-project architecture reconciliation | Every existing project accounted for with a retained architecture document, truthful retrospective provenance, and explicit unapproved/unknown history where applicable. No fabricated original agreement or new automatic reassignment. | SHRR-02; SHRR-04 |
| SHRR-08 | Acceptance, operating documentation, and staged rollout | Cross-agent synthetic acceptance, approved pilot evidence, recovery/backup limitations, operator runbook, separately authorized deployment, and project closeout with an as-built architecture. | SHRR-01–07 |

Each row gets its own execution work item. Attempts, tests, and deployment steps attach to the relevant item. Scope-changing defects become explicitly mapped corrective work; they are not concealed by repeatedly enlarging one conversation-sized work item.

## 11. Project acceptance scenarios

| Scenario | Required outcome |
| --- | --- |
| New project | Retained architecture, explicit human agreement, and work breakdown map to Linear/Jarvis before implementation. |
| Ordinary work start | Correct project/work/architecture context and capture begin without the operator asking to record history. |
| Several deliverables in one chat | Distinct execution work items, explicit switches, no duplicate project or indiscriminate transcript attribution. |
| Two named Linear agents | Jarvis and Codex are separately discoverable, mentionable, delegatable, and visibly attributed; they are not aliases on a shared operator identity. |
| Direct operator → Codex in Linear | Codex receives a message and its follow-up, replies as Codex, and binds the actual runtime session to the issue. No Jarvis relay is used. |
| Direct architecture decision with Codex | Codex presents a version/deviation; the operator replies directly; exact decision/source and designation are retained without a Jarvis signoff. |
| Jarvis unavailable | Operator/Codex communication, agreed work, and decision recording still function through the independent Codex path. |
| Jarvis → Codex → Jarvis through Linear | Correlated request, recipient acknowledgment, and result appear under the correct actors; one work identity persists and every transfer has truthful state. |
| Linear → existing interactive continuation | Supported runtime/session binding or explicit linked continuation is demonstrated; no claim of injecting into a desktop chat merely from MCP setup. |
| Hermes → Codex → later interactive continuation | One work identity, separate coordinator/executor sessions and attempts, source evidence and failure context preserved. |
| Repeated handoff event or agent reply echo | One accepted request/attempt; no duplicate launch or infinite agent conversation. |
| Worker never commits | Capture survives; later source publication is linked without pretending the worker made that commit. |
| Architecture changes | One review request for the material delta; only affected work waits. Routine work creates no new approval requests. |
| Agent edits a Linear document or sets Done | Governing bytes and human agreement do not silently change. |
| Legacy user-token write or impersonation attempt | Attribution limits remain visible; neither agent can be confused with the other or with the human, and no agent message becomes human approval. |
| Outage, lost response, repeated export, or restart | Durable pending evidence, repeatable receipts, no duplicated work/imports, and visible freshness. |
| Old/missing source, compaction, or deleted Linear comment | Coverage limit preserved; no claim of complete history without evidence. |
| Cross-project or unauthorized access | No evidence, metadata, counts, or curated content leaks beyond the admitted scope. |
| Later debugging question | Operator and allowed Jarvis reader can explain a failed approach and final decision with versioned architecture/work/test/deployment references. |
| Existing project lacks architecture | Retrospective document retained with honest provenance; original events and decisions preserved. |
| Closeout | Exact as-built architecture, work dispositions, final baseline and rollout evidence linked; source completion distinguished from deployment and browser/MCP acceptance. |

## 12. Delivery sequence and review points

1. Human reviews this architecture. Any agreed version is retained and designated explicitly.
2. Establish the Linear project/work mappings and lightweight decision convention. Inventory the existing Hermes connection and preserve its current behavior while designing the two registered app identities and required adapter routes.
3. Compare collectors on synthetic fixtures, select the minimal compatible capture path, and report significant coverage gaps before designing around them.
4. Implement the two named agents' message/session paths and additive history contracts/intake. Demonstrate direct Codex communication and architecture decisions independently of Jarvis, then connect automatic capture and scoped observations.
5. Add reference UI/curated retrieval, reconcile older project architecture documents, and run the cross-agent acceptance scenarios.
6. Present the concrete tested release for the existing merge/deployment decision, conduct the approved pilot/production checks, and retain closeout evidence.

This sequence does not add a human gate between every implementation step. The decisions needing attention are the governing architecture, a material deviation, and operational actions already requiring separate authority. Model-free testing is preferred; new paid runs and production activation are not implied by preparing this document.

### Recommendations to assess during this review

- Start with SpecStory as the capture favorite; retain a fair Entire comparison before selection.
- Use existing Linear issue/document features and explicit decision records. Register Jarvis and Codex as separate native agents with the minimal message/session event delivery needed for direct conversation and handoff; no general workflow engine.
- Keep one active engineering executor per issue by convention, with explicit handoff and role attribution. Jarvis is the overall assistant; Codex is the coder/engineer. The operator can work with Codex directly throughout.
- Preserve complete selected engineering exports privately, keep Linear updates concise, and publish only approved structured fields to the existing Jarvis reader.
- Treat installed Hermes/session compatibility and the operator's Linear plan/capabilities as facts to establish, not assumptions to conceal.

Linear's published Free plan currently includes two teams, 250 issues, and MCP/API access. The operator's actual plan was not inspected; this proposal does not require buying Linear AI, Loops, or premium workflow automation. Confirm capacity before creating the project work set. [Linear pricing](https://linear.app/pricing).

## 13. Baseline, references, and version history

Local source reviewed read-only:

- Repository: `/home/shanereviello/Documents/Codex/2026-10-17/files-mentioned-by-the-user-rras/work/jarvis-migration-source`, commit `705f69c057a1e2b6e134d61a69519c409928425d`.
- `engineering/docs/engineering-project-workspace/PROJECT-WORKSPACE-AS-BUILT-ARCHITECTURE-20261107.md`: schema, ownership, exact architecture versions, membership, snapshots, and read-only UI.
- `engineering/tools/rras_history/{store,projects,scopes,interactive,curated_mcp}.py`: immutable event storage, scoped organization, explicit recording client, and curated-only reader.
- `app/tools/linear_actions.py` and `app/services/linear_gateway.py`: existing Linear action surface and gateway boundary.
- `engineering/docs/hermes-preparation-install.md`, `engineering/docs/rras-native-hermes-intake-review.md`, and `AGENTS.md`: existing preparation/runtime/publication boundaries. Historical checkpoint language is not treated as proof of current live capability.

External sources are linked beside the findings they support. All were consulted for this research on November 7, 2026. Versions, account entitlements, and live integration behavior must be pinned in the eventual evaluation report. Product documentation is evidence about the product; it is not an instruction to install it or expand the project's scope.

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | November 6, 2026 | Earlier proposal emphasizing shared reporting policy, lifecycle enforcement, and approval bindings; retained unchanged. |
| 0.2 | November 7, 2026 | Refocuses on durable engineering reference; evaluates SpecStory/Entire, selects Linear for coordination, distinguishes Hermes/Codex roles and identity, narrows human oversight to architecture/deviations, and retains owned history/UI with eight explicit execution deliverables; retained unchanged. |
| 0.3 | November 7, 2026 | Makes separate registered Jarvis/Hermes and Codex Linear agents mandatory; sets overall-assistant versus coder/engineer roles; adds direct operator/Codex conversations and architecture decisions without Jarvis mediation; defines bidirectional Linear handoffs, scoped message/session adapters, actor attribution, failure isolation, and corresponding work/acceptance updates. |

**Status: draft for review. No implementation, architecture designation, installation, Linear mutation, or deployment is established by this file.**
