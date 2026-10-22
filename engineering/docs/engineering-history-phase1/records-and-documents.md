# Proposed engineering record and document contract

Design specification, not an implemented JSON Schema or amendment to workflow-v1.
Names below are conceptual and must be frozen in a reviewed schema slice after D1.

## Records

| Record | Identity/binding | Rules |
| --- | --- | --- |
| Engineering work | Stable work ID, one repository ID, descriptive title, current revision | Unknown/unregistered repository can be documented but cannot execute through managed admission. |
| Work revision | Work ID + revision + previous digest | Intent, rationale, exact scope, criteria, baseline or explicit unknown, validation, constraints. Immutable. |
| Session association | Session link ID + client/session source namespace + work ID/revision | Many sessions per work; one session may attach to several works only with explicit active context. No silent repository switch. |
| Attempt association | Attempt ID + exact revision + execution mode + operational references | Interactive/managed mode belongs to execution context. Map v1 work-mode bindings explicitly; a mode switch may require a new operational work revision. |
| Document manifest | Document ID, type, version, content SHA256, work revision digest, template/renderer digests | Review/checkpoint/completion; exact stored Markdown bytes, language and visibility. Supersedes only explicitly. |
| Claim / evidence link | Claim ID, statement, evidence refs, source and observation scope | 'Observed' names a trusted collector and what it actually checked. Missing facts are unknown, not successful. |
| Decision | Decision ID, authenticated decider or human_reported source, subject, target digest, action, time | Decision record does not itself perform an action. Retrospective chat import stays human_reported and has explicit unknown original time. |
| Relationship | From/to stable IDs, relation, rationale | continues, depends_on, supersedes, related; cycle/refusal rules for dependencies. Cross-repository initiative groups per-repo work, not a repository change inside one work ID. |
| Publication receipt | Source system, original identity/digest, remote state and retrieval time | Branch/PR/merge/deploy separately referenced. A git commit records exact diff, not the reason by itself. |

All submissions have schema version, client event key, caller identity established
by transport, source kind, occurred_at nullable when unavailable, recorded_at assigned
by server, object digest, visibility and references. Do not invent missing source
session IDs or timestamps. Server receipt includes durable record/head and whether
the result was inserted or previously accepted. Hostnames/absolute paths are private
metadata; shared documents use repository IDs and relative allowed paths instead.

## Content and review approval

A managed review package has two layers:

1. Machine-enforced core from protected capture: registration/work/config/profile
   hashes, exact baseline, allowed paths, recipe argv/timeouts, model/authority limits,
   assigned branch and operation ID. Rendered directly; free text cannot override it.
2. Curated intent/rationale/approach/criteria: reviewed input frozen into the package,
   with unknowns and assumptions explicit. A generated approach is a proposal, not
   proof that a tool will follow it or that the outcome will succeed.

Capture creates canonical content + exact Markdown bytes + manifest. A companion approval envelope binds the existing protected review digest,
document-manifest digest and exact Markdown digest (never embedding a document
digest in its own bytes). The capture operation ID may appear inside the document;
the final envelope digest is displayed externally. This binding covers all three, template/renderer version and existing capture
identities. The approval validates and displays the exact document digest and action.
No new root authority derives from engineering-store draft content. Scope/baseline/
config/content changes require a new capture/revision. Layout-only re-rendering also
creates a different document; it cannot replace the approved bytes. Old approvals
continue their old semantics until a deliberate versioned rollout invalidates or
retires them; no silent upgrade to new approval meaning.

Interactive review documents use the same structure but can state unknown baseline,
flexible scope or unadmitted validation. Their acceptance records engineering intent,
not a managed paid-run grant. Real Git/config checks must establish a bounded managed
contract before handing off. Interactive Codex's existing sandbox/permission gates
and separate merge/deployment decisions remain.

## State dimensions (not a single success label)

Track proposal/captured revision, execution attempt status, validation status,
deliverable acceptance, source publication, merge, deployment and operational
verification independently. Checkpoints can exist at any stage. A work item may be
paused/unfinished with successful earlier attempts; human acceptance may later be
superseded by a correction. Explicitly display rejected/uncertain/no-evidence states.

Completion means the recorded outcome of a scope, not necessarily merge/deployment.
A record may say 'documentation accepted and merged; deployment not applicable'.
The current root `release_status=not_inferred` remains intact; future product views
must state their release threshold and cite the exact qualifying events.

## Document publication

Each narrative field records its origin: human input, agent synthesis, imported
source or observed evidence, with references where possible. Sharing requires a
trusted publication decision/policy, not a model-authored visibility string. Default
new text to operator-private draft. Jarvis-shared content is a separately published,
bounded view that excludes raw prompts, credentials, full logs and private paths.
If the human chooses automatic publication later, that is an explicit policy change.

A Markdown export is a replica, never an editable authority. Edited external copies
are new proposals. Search indexes only authorized current content, retaining enough
supersession metadata to explain corrections without surfacing withdrawn text.
