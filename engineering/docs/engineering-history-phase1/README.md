# Engineering history and human interface: Phase 1 design

Status: **D1 direction accepted; detailed design ready for source review**, October22,2026. No schema migration,
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
   proposed flow, consistency, backup and rollout. The operator accepted direction D1.
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

## Decision register

| ID | Decision / current status | Boundary / remaining gate |
| --- | --- | --- |
| D1 **accepted** | Keep the root operational journal for execution authority/evidence; add a dedicated unprivileged engineering-history service/store, joined by stable IDs and exported receipt digests. | Operator approved the separate unprivileged service/store direction in this conversation on October22,2026. Existing journal ownership/authority stays intact; implementation and installation retain their own gates. |
| D2 | Start browser access as an authenticated, private-network, single-operator read-only client; select actual network/identity integration before any listener is deployed. | Actual VPN/reverse-proxy/identity-provider availability and access audience are not established. No public exposure, account system or authentication bypass is assumed. |
| D3 | Markdown is an immutable versioned view of canonical structured content; Git publication of curated documents is optional, with destination/visibility explicitly selected later. | Git replicas must not become a second mutable approval authority or accidentally publish private engineering notes. No notes repository is created here. |

The operator accepted D1 with “yes i approve of that direction” after the separate
unprivileged service recommendation. This records architectural direction, not a
claim of authenticated browser approval or original message timestamp. D2 remains
open before a web listener, while D3's optional Git mirror is outside the initial
implementation. Source merge remains separately controlled under AGENTS.md.

8. [Initial implementation specification](initial-implementation-spec.md): concrete
   local topology, versioned envelopes, write/receipt semantics, migration/export
   boundaries, command surface and testable initial-slice definition.

## Phase 1 exit

This package completes the Phase1 design deliverables for review: D1 is decided;
record/approval/privacy invariants, templates and an ordered backlog are specified;
integration coverage and remaining deployment decisions are explicit. Source merge
accepts the design baseline; the operational templates remain drafts until their
renderer/capture implementation is reviewed and tested.
D2 may remain a named gate before the web phase; no insecure placeholder deployment.
No product implementation or end-to-end capture is claimed by this design package.
