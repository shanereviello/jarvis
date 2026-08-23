# Jarvis Agent Memory Architecture

## Purpose

This document defines the planned addition of durable agent memory to Jarvis using a self-hosted Mem0 deployment.

The goal is to let Jarvis remember useful information across conversations—such as user preferences, project context, prior decisions, and verified diagnostic outcomes—without replacing or weakening the existing engineering sources of truth.

Jarvis will use two complementary information systems:

1. The engineering database and engineering note vault will remain authoritative for facts about the engineered system.
2. Mem0 will provide contextual memory about the user, conversations, decisions, and the agent's prior experiences.

The memory system must supplement engineering retrieval, not become a second uncontrolled engineering database.

## Target outcomes

When this work is complete, Jarvis should be able to:

- remember explicit user instructions across separate n8n conversations;
- recall stable preferences, aliases, and project context;
- recall what was previously discussed or decided;
- reuse verified lessons from earlier diagnostic work;
- distinguish historical context from the current engineered configuration;
- explain where a recalled memory came from;
- allow memories to be inspected, corrected, exported, and deleted;
- continue answering engineering questions when the memory service is unavailable;
- prevent memory from overriding current engineering database records or approved notes;
- preserve a provider boundary that would allow a narrow Hindsight integration later without redesigning the agent.

## Non-goals

The initial implementation will not:

- copy the engineering database into Mem0;
- treat Mem0 as authoritative for wiring, components, part numbers, pinouts, interfaces, or configuration;
- write every chat message permanently without filtering;
- store passwords, tokens, private keys, or other credentials;
- allow the model to rewrite its own system procedures autonomously;
- introduce a graph database;
- deploy Hindsight alongside Mem0;
- require memory for ordinary engineering tool calls;
- move the agent runtime out of n8n;
- replace the existing Jarvis MCP engineering tools.

Hindsight may be evaluated later for a small, explicitly isolated episodic-learning use case. Mem0 will be the exclusive durable memory provider for the initial system.

## Information and trust model

Jarvis will operate with three distinct context layers.

| Layer | Purpose | Examples | Authority |
|---|---|---|---|
| Engineering sources | Current facts about the physical and software system | components, wiring, cable terminations, GPIO assignments, part numbers, approved notes | Authoritative for engineering facts |
| Mem0 | Durable user and agent context across conversations | preferences, aliases, prior decisions, verified diagnostic episodes | Contextual; authoritative only for explicit user preferences or statements |
| n8n conversation state | Current working context | recent messages, current task, temporary plan, recent tool output | Temporary and thread-scoped |

The precedence order is:

1. Current engineering database results and approved engineering notes.
2. Explicit user instructions in the current conversation.
3. Explicit, verified user memories stored in Mem0.
4. Verified historical episodes stored in Mem0.
5. Automatically inferred Mem0 memories.
6. Model inference.

If a memory conflicts with the engineering database or an approved engineering note, Jarvis must use the engineering source, disclose the conflict when relevant, and treat the memory as stale or incorrect.

## Deployment topology

The current Jarvis agent runs on the rack Raspberry Pi, while the engineering PostgreSQL database runs on the server. The memory deployment will preserve that division.

```text
Rack Raspberry Pi
├── n8n
│   ├── agent orchestration
│   └── short-term conversation state
├── Jarvis MCP
│   ├── engineering retrieval tools
│   └── controlled memory tools
└── no durable memory database
        │
        │ authenticated LAN API request
        ▼
Server
├── existing engineering PostgreSQL
│   └── authoritative engineering data
├── Mem0 API and administration dashboard
└── separate Mem0 PostgreSQL with pgvector
    └── agent memory only
```

### Raspberry Pi responsibilities

The Raspberry Pi will:

- continue running n8n and Jarvis MCP;
- identify the current user, agent, project, and session;
- decide when memory retrieval is useful;
- call the controlled Jarvis memory service;
- call existing engineering tools independently;
- present memory and engineering evidence as separate context sections;
- submit explicit memories and approved post-conversation memory candidates;
- continue without memory when Mem0 is unavailable.

The Raspberry Pi will not:

- run the Mem0 PostgreSQL database;
- manipulate Mem0 tables directly;
- reveal the Mem0 API key to the model;
- accept arbitrary identity scopes supplied by the model;
- make Mem0 a dependency of engineering database availability.

### Server responsibilities

The server will:

- continue hosting the engineering database;
- run the self-hosted Mem0 API and dashboard;
- run a separate PostgreSQL/pgvector instance for Mem0;
- hold persistent memory volumes;
- provide independent memory backups and restore procedures;
- optionally run Ollama later for local extraction and embeddings;
- restrict Mem0 API access to the Raspberry Pi and trusted administrators.

Keeping the Mem0 application next to its database reduces Raspberry Pi load, keeps stateful services together, and makes backup and future local-model deployment easier.

## Database isolation

The preferred deployment uses a separate PostgreSQL container or instance for Mem0:

```text
server
├── engineering-postgres
│   ├── existing engineering database
│   ├── engineering-specific role
│   └── engineering backup policy
└── mem0-postgres
    ├── Mem0 database
    ├── pgvector extension
    ├── Mem0-only role
    ├── separate persistent volume
    └── memory-specific backup policy
```

The Mem0 database role must not have permission to connect to or query the engineering database. The engineering application role must not have access to the Mem0 database.

A separate database on the same PostgreSQL instance is an acceptable resource-saving alternative, but a separate container or instance provides clearer migration, credential, backup, and failure boundaries. A shared database with separate schemas is not recommended.

## Mem0 model dependencies

Mem0 needs:

1. an LLM to extract useful memories from messages or completed episodes;
2. an embedding model to index and retrieve those memories;
3. PostgreSQL with pgvector for durable storage and similarity search.

The initial rollout will use hosted extraction and embedding models while keeping the Mem0 API and all stored memory data local. This minimizes initial operational complexity and establishes a reliable quality baseline.

A later phase may move extraction and embedding to Ollama running on the server. The Raspberry Pi should not host these models unless later hardware testing shows it can do so reliably.

Changing embedding models requires deliberate migration planning. Existing vectors may need to be regenerated into a test collection before the new embedder becomes active.

## Jarvis application changes

Jarvis will access Mem0 through a provider-neutral service boundary rather than exposing Mem0 directly to the agent.

The intended repository layout is:

```text
app/
├── core/
│   └── config.py
├── schemas/
│   └── memory.py
├── services/
│   └── memory.py
└── tools/
    ├── recall_agent_memory.py
    ├── remember_agent_memory.py
    ├── list_agent_memories.py
    ├── update_agent_memory.py
    └── forget_agent_memory.py
```

The new tools will be registered through the existing MCP registry, consistent with the current architecture:

- services contain business logic;
- schemas define stable results;
- tools provide thin MCP wrappers;
- the MCP registry exposes those tools to n8n and the agent.

### Provider-neutral interface

The service should expose concepts such as:

```python
class MemoryProvider:
    def remember(self, ...): ...
    def recall(self, ...): ...
    def list(self, ...): ...
    def update(self, ...): ...
    def forget(self, ...): ...
    def health(self): ...
```

The first implementation will be backed exclusively by Mem0. This boundary prevents Mem0-specific response formats from spreading into n8n prompts and leaves room for a future narrowly scoped provider without changing the agent-facing contract.

### Runtime configuration

Jarvis will need settings similar to:

```text
MEM0_ENABLED=true
MEM0_BASE_URL=http://<server-lan-address>:<mem0-port>
MEM0_API_KEY=<secret>
MEM0_TIMEOUT_SECONDS=<bounded timeout>
MEM0_DEFAULT_AGENT_ID=jarvis
MEM0_MAX_RECALL_RESULTS=5
MEM0_MIN_RELEVANCE_SCORE=<evaluated threshold>
MEM0_AUTO_WRITE_ENABLED=false
```

Secrets will live in the deployment environment, not source control, prompts, tool results, or n8n conversation data.

## Identity and scoping

Every memory operation must have a trusted scope:

```text
user_id
agent_id
project_id
session_id
```

For the initial single-user deployment, the starting identity may be:

```text
user_id: shane
agent_id: jarvis
project_id: jarvis-engineering or a specific project
session_id: stable n8n conversation identifier
```

n8n or Jarvis must inject and validate these identifiers. The language model must not be permitted to retrieve a different user or project merely by providing another identifier in a tool call.

Project scope should be applied before semantic retrieval so that unrelated projects do not contaminate results.

## Memory categories

### Semantic memory

Semantic memory holds durable context and facts about the user or workflow:

- response and formatting preferences;
- project aliases;
- stable development-environment context;
- durable user decisions;
- terminology the user commonly applies;
- explicit instructions about how information should be presented.

Example:

```text
Shane prefers the likely root cause before the detailed diagnostic procedure.
```

### Episodic memory

Episodic memory records selected prior experiences and outcomes:

- the situation;
- relevant evidence;
- actions attempted;
- unsuccessful approaches worth avoiding;
- verified resolution;
- reusable lesson;
- when the episode occurred;
- which project and conversation produced it.

Example:

```text
Situation: The D455 appeared on the Raspberry Pi host but was unavailable
inside the application container.

Resolution: Restoring the USB bus mount made the camera available.

Lesson: Compare host and container device visibility before changing camera
application configuration.
```

Raw transcripts and complete execution traces should not normally be injected as episodic memory. They should be distilled into small, sourced, verified episodes.

### Conversation summaries

Conversation summaries may capture durable decisions or unresolved follow-up work from a completed conversation. They are not substitutes for recent n8n messages and should not be created for trivial interactions.

### Procedural memory

Autonomously learned procedural memory is excluded from the initial implementation. Stable agent behavior belongs in version-controlled prompts, code, MCP tool descriptions, and reviewable documentation.

Mem0 may eventually store proposed process improvements as review candidates, but those candidates must not automatically change agent behavior.

## Memory record metadata

Every memory should include enough metadata to evaluate and govern it:

```json
{
  "user_id": "shane",
  "agent_id": "jarvis",
  "content": "Shane prefers the likely root cause before detailed diagnostics.",
  "metadata": {
    "project_id": "jarvis-engineering",
    "memory_type": "semantic",
    "category": "response_preference",
    "source_type": "explicit_user",
    "source_session_id": "session-123",
    "verified": true,
    "authority": "user_preference",
    "created_by": "jarvis-memory-pipeline"
  }
}
```

Recommended source types include:

- `explicit_user`;
- `conversation_extraction`;
- `verified_task_outcome`;
- `operator`.

Recommended categories include:

- `preference`;
- `identity`;
- `project_context`;
- `decision`;
- `task_outcome`;
- `diagnostic_episode`;
- `correction`.

Automatically inferred content must be distinguishable from explicit user memories.

## Memory write policy

Jarvis will not write all chat content to durable memory by default.

### Store immediately

- explicit requests beginning with or equivalent to “remember that...”;
- direct corrections to an existing user preference;
- explicit requests to retain a stable project alias or decision.

### Store after filtering or extraction

- stable preferences demonstrated clearly in conversation;
- durable project context;
- decisions that will matter in another session;
- completed and verified diagnostic episodes;
- useful corrections to a previous unsuccessful approach.

### Do not store

- passwords, access tokens, private keys, or credentials;
- raw engineering database results as new facts;
- wiring, pinouts, part numbers, or configuration copied from engineering sources;
- temporary task state;
- speculative model conclusions;
- unverified diagnoses;
- routine tool output;
- irrelevant social conversation;
- process changes that should be committed to code or prompts.

### Post-conversation formation

Automatic memory formation will eventually run as an asynchronous n8n branch:

```text
completed conversation or task
        │
        ▼
extract durable candidates
        │
        ├── useful in a future session?
        ├── stable enough to retain?
        ├── scoped to the correct user/project?
        ├── free of secrets?
        ├── distinct from engineering truth?
        └── verified when it describes an outcome?
        │
        ▼
deduplicate or identify correction
        │
        ▼
write approved memory to Mem0
```

This workflow must not delay the user-facing response.

## Memory recall policy

### Automatically available profile

A very small set of stable, explicit memories may be loaded automatically:

- user identity;
- response preferences;
- current project identity;
- explicitly pinned context.

This profile must have a strict token budget.

### On-demand recall

The agent should query Mem0 when the request refers to history or prior experience, including language such as:

- “again”;
- “last time”;
- “previously”;
- “what did we decide?”;
- “have we seen this before?”;
- “what worked before?”

Episodic recall should also be considered for diagnostic tasks where prior outcomes could improve tool selection.

### When memory is unnecessary

Direct engineering lookups should use engineering tools without automatically involving memory.

For example:

```text
Where does W001 terminate?
```

should call the exact engineering connection lookup. Memory is only relevant if the user also asks what happened previously or whether a similar issue was diagnosed before.

### Context separation

The model should receive distinctly labeled sections:

```text
AUTHORITATIVE ENGINEERING DATA
- Current records returned by engineering tools.

AGENT MEMORY — HISTORICAL OR PERSONAL CONTEXT; MAY BE STALE
- Relevant memories returned by Mem0.
```

The agent prompt and MCP instructions must reinforce this separation.

## Example request lifecycle

User request:

```text
Why might the D455 not be working again?
```

Processing flow:

1. n8n resolves the trusted user, agent, project, and session identifiers.
2. Jarvis recalls relevant semantic and episodic memories from Mem0.
3. Mem0 returns a prior verified episode involving container USB visibility.
4. Jarvis independently queries the engineering database for the current D455 record and configuration.
5. Jarvis reads the associated engineering note if the database result indicates that it is needed.
6. The agent receives engineering facts and historical memory in separate context sections.
7. The agent uses the prior episode to prioritize the investigation but uses engineering results for current facts.
8. After the problem is resolved, n8n may submit a compact verified episode to the asynchronous memory pipeline.

## MCP tools

The initial MCP surface should include:

### `recall-agent-memory`

Retrieves relevant memories within the trusted user, agent, and project scope.

Inputs should be limited to agent-relevant fields such as:

- query;
- memory types;
- project context;
- result limit.

Identity fields should be injected or validated outside model control.

### `remember-agent-memory`

Stores an explicit or approved memory with provenance and category metadata.

### `list-agent-memories`

Allows inspection and administration of memories in the current scope.

### `update-agent-memory`

Corrects or supersedes an existing memory while preserving appropriate history.

### `forget-agent-memory`

Deletes a selected memory or approved scope of memories and returns a verifiable result.

The Mem0 administration dashboard will complement these tools for operator inspection and maintenance.

## Security requirements

- Mem0 self-hosted authentication must remain enabled.
- Jarvis will receive a dedicated API key with the minimum necessary access.
- The API key will be stored only in deployment secrets.
- The Mem0 database port will not be exposed to the general LAN.
- The Mem0 API will be reachable only from the Raspberry Pi and trusted administration hosts.
- The dashboard will be restricted to the management LAN.
- No Mem0 service will be exposed directly to the public internet.
- The Mem0 database role will have no engineering database access.
- User and project scopes will be enforced before retrieval.
- Tool inputs and recalled content will be treated as untrusted text for prompt-injection purposes.
- Memory listings and exports will require an authorized scope.
- Secrets detected during memory formation will be rejected rather than embedded.

TLS can be added through a private reverse proxy when appropriate. For initial LAN deployment, authenticated HTTP may be used only when restricted by host firewall and trusted network boundaries.

## Availability and failure handling

Mem0 is an optional context service, not a required dependency for engineering retrieval.

If Mem0 is unavailable:

- Jarvis logs the failure without logging secrets;
- memory tools return a bounded unavailable result;
- engineering tools continue normally;
- the agent answers without durable historical context;
- the user is notified only when the question materially depends on unavailable history.

If a memory write fails:

- the user-facing response remains successful;
- the candidate may enter a bounded retry queue or operator-visible failure log;
- retries must be idempotent to prevent duplicate memories.

Every Mem0 request will have a short timeout and controlled retry behavior.

## Backups and recovery

Engineering and memory backups will remain independent.

The Mem0 backup plan should include:

- daily logical PostgreSQL backups;
- periodic backup of the Mem0 persistent volume;
- encrypted backup storage;
- retention rules appropriate for conversation-derived data;
- backup of pinned container versions and Mem0 configuration;
- backup or regeneration procedures for authentication configuration;
- a tested restore process;
- periodic verification that memories remain searchable after restoration.

The vector data should be backed up with the rest of the memory database. Reproducing vectors later may be impossible without the original content, embedding model, model version, and exact configuration.

## Observability and evaluation

The system should record operational metrics without exposing memory content unnecessarily:

- Mem0 availability;
- ingestion and retrieval latency;
- memory-write success and failure counts;
- recall result counts;
- tokens or characters injected into agent context;
- correction and deletion events;
- duplicate-memory rate;
- memories rejected by policy;
- retrieval calls that returned no useful result.

Quality evaluation should measure:

- recall precision;
- recall coverage;
- temporal correctness;
- contradiction handling;
- abstention when no memory is relevant;
- cross-user and cross-project isolation;
- engineering-source precedence;
- usefulness of recalled diagnostic episodes;
- successful deletion and forgetting;
- answer quality with memory enabled versus disabled.

The first evaluation set should include explicit preferences, project aliases, prior decisions, diagnostic episodes, contradictions, irrelevant-memory cases, deletion cases, and attempts to override engineering truth.

## Phased implementation plan

### Phase 1: deploy Mem0 on the server

- Create a separate Compose project for the memory stack.
- Deploy the authenticated Mem0 API and dashboard.
- Deploy a dedicated PostgreSQL/pgvector container and persistent volume.
- Restrict services to the private LAN.
- Create an administrator and dedicated Jarvis API key.
- Pin all container and application versions.
- Verify add, recall, list, update, delete, restart persistence, and backup/restore behavior.

### Phase 2: add the Jarvis provider adapter

- Add memory configuration to `app/core/config.py`.
- Add stable memory schemas.
- Implement the Mem0-backed service behind a provider-neutral interface.
- Add bounded timeouts, retries, idempotency, and graceful failures.
- Normalize Mem0 responses before returning them to the agent.
- Add unit tests that mock the Mem0 API.

### Phase 3: expose explicit MCP memory operations

- Add and register recall, remember, list, update, and forget tools.
- Enforce trusted identity and project scope.
- Support explicit “remember this” and “forget this” workflows.
- Keep automatic memory formation disabled.
- Add prompt instructions establishing engineering-source precedence.

### Phase 4: integrate recall into n8n

- Preserve n8n as short-term conversation memory.
- Load a small explicit user profile automatically.
- Trigger episodic recall for history-oriented requests.
- Label memory separately from engineering data.
- Apply strict relevance, result-count, and token limits.
- Ensure Mem0 failure does not block engineering answers.

### Phase 5: add asynchronous memory formation

- Add a post-response n8n branch.
- Extract durable candidate memories.
- reject secrets, speculation, temporary state, and duplicated engineering facts;
- deduplicate candidates;
- require verification for diagnostic outcomes;
- retain complete provenance;
- begin with operator review before enabling narrow automatic acceptance.

### Phase 6: evaluate and tune

- Run the Jarvis-specific memory test corpus.
- Tune result limits and relevance thresholds.
- measure whether memory improves recurring diagnostic work;
- inspect false recalls and stale memories;
- define retention and consolidation jobs;
- validate user/project isolation and deletion.

### Phase 7: optionally move models local

- Deploy Ollama on the server.
- Test a local extraction model against the hosted baseline.
- Test a local embedding model in an isolated collection.
- measure extraction quality, recall quality, latency, and resource use;
- migrate only after the local configuration passes the evaluation suite.

## Future Hindsight option

Hindsight is not part of the initial deployment. The provider-neutral boundary will allow it to be considered later for a narrow episodic-learning function.

If added, the intended separation would be:

```text
n8n        -> short-term conversation state
Mem0       -> semantic memory, user context, decisions, and ordinary episodes
Hindsight  -> only a proven, isolated class of verified experiential learning
Engineering sources -> authoritative system truth
```

Hindsight should only be introduced if evaluation demonstrates a material advantage for that isolated workload. The system should never send all conversations to both providers and merge two competing general-purpose memory results.

## Completion criteria

The first production-ready memory capability is complete when:

- Mem0 runs reliably on the server with its own PostgreSQL/pgvector database;
- the Raspberry Pi can access it through an authenticated, restricted LAN endpoint;
- Jarvis exposes controlled, tested MCP memory tools;
- users can remember, recall, inspect, correct, and forget memories;
- n8n remains responsible for short-term conversation state;
- engineering lookups continue to work without Mem0;
- memory and engineering evidence are clearly separated in agent context;
- current engineering sources always override conflicting memory;
- memory writes exclude secrets and duplicated engineering facts;
- backup and restore procedures have been tested;
- identity isolation and deletion tests pass;
- evaluation shows that recalled memories improve relevant answers without degrading direct engineering retrieval.

