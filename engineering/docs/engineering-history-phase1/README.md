# Engineering history and human interface: Phase 1 design

Status: **proposal for architecture review**, October22,2026. No schema migration,
service, account, hook, credential, network listener or runtime change is authorized
by this document. The prior operator workflow phase remains deployed and complete.

## Outcome

Managed Jarvis tasks and interactive Codex work share discoverable engineering
history: intent, decisions, actual changes, evidence, review documents and outcomes.
A standard protected-capture review document supports human decisions. A later web
interface reads the same data and eventually requests narrowly authorized actions.
Plans, claims, observations and approvals retain distinct meanings.

## Read this design

1. [Existing capability map](capability-map.md): code-backed facts and gaps.
2. [Architecture decision](architecture.md): storage alternatives, recommended boundary,
   proposed flow, consistency, backup and rollout. Decision D1 needs human input.
3. [Record and document contract](records-and-documents.md): identities, lifecycles,
   revision/digest binding, authority and rendering.
4. [Interactive integration](interactive-integration.md): explicit capture first,
   supported hook opportunity and evidence/coverage limits.
5. [Interfaces and access](interfaces-and-access.md): browser/Jarvis/Codex permissions,
   conceptual API and future authenticated controls. Decision D2 remains open.
6. [Implementation backlog and acceptance](backlog-and-acceptance.md): ordered slices,
   deliverables, dependencies, failure cases and rollout gates.
7. Templates: [review](templates/review.md), [checkpoint/handoff](templates/checkpoint.md),
   [completion](templates/completion.md). [Worked scenarios](scenarios.md) exercise them.

## Decisions requiring the operator

| ID | Proposed decision | Why approval matters |
| --- | --- | --- |
| D1 | Keep the root operational journal for execution authority/evidence; add a dedicated unprivileged engineering-history service/store, joined by stable IDs and exported receipt digests. | New persistent service/store and identity boundary; existing journal must not simply be made writable/readable by clients. Alternative: a narrow privileged intake broker extending the current journal. |
| D2 | Start browser access as an authenticated, private-network, single-operator read-only client; select actual network/identity integration before any listener is deployed. | Actual VPN/reverse-proxy/identity-provider availability and access audience are not established. No public exposure, account system or authentication bypass is assumed. |
| D3 | Markdown is an immutable versioned view of canonical structured content; Git publication of curated documents is optional, with destination/visibility explicitly selected later. | Git replicas must not become a second mutable approval authority or accidentally publish private engineering notes. No notes repository is created here. |

D1 is the first blocking architecture decision. The recommendation does not assume
approval for a second database/service. D2 blocks web deployment, not template design;
D3's document-authority principle follows the proposed roadmap, while any Git mirror
requires a concrete destination/privacy decision. Source merge is separately human
controlled under AGENTS.md. Architectural approval is not deployment/paid-task approval.

## Phase 1 exit

Design complete means D1 is decided, record/approval/privacy invariants and templates
accepted, integration coverage is honest, and the implementation backlog is agreed.
D2 may remain a named gate before the web phase; no insecure placeholder deployment.
No product implementation or end-to-end capture is claimed by this design package.
