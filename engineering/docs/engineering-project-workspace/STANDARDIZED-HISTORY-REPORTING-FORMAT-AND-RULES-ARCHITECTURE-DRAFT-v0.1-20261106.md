# Standardized History Reporting Format and Rules

Architecture document — draft v0.1  
Date: November 6, 2026, America/New_York  
Proposed repository: `jarvis`  
Status: **For human review. This detailed architecture has not been approved for implementation.**

The human has established the governing principle: **every project must have an
architecture document, without exceptions. Human agreement to an exact version
of that document establishes the contract for the work it contains. Its broken-out
work items must correlate explicitly with the work items reported in history.**

This draft translates that principle and the preceding workflow research into a
proposed implementation. Creating this file does not create database records,
approve the entire design, authorize coding, change installed rules or start a
Hermes job. Earlier merge/deployment approvals for Engineering History Workspace
belong to that completed effort; authorization for this new effort must be clear
in its own context.

## 1. Purpose and intended outcome

Establish one consistent way to define, authorize, execute and report engineering
work across interactive Codex development and Hermes-driven managed work. Keep
the work the human agreed to, the work the agents execute and the work displayed
in history aligned through stable identities and exact version references.

The motivating failures were missing recording at the start of an interactive
conversation and several independently assessable deliverables being grouped
under a single work item. The existing history service can preserve records and
the webpage can browse them. This project adds the shared policy, workflow
integration, traceability and verification needed to use those capabilities
consistently.

Success means that a person can open a project and answer:

1. What exact architecture and work breakdown did the human approve?
2. Which reported work item implements each part of that agreement?
3. Which architecture/work revisions and policy version governed each execution?
4. What was attempted, changed, validated, accepted, merged and deployed?
5. What remains incomplete, blocked, deferred or outside the agreement?

## 2. Scope and boundaries

### Included in this project

- A mandatory architecture and explicit human agreement for every project.
- An architecture-contained work breakdown, with one-to-one stable bindings to
  reported work items and visible coverage/discrepancy checks.
- A reviewed, versioned common policy and shared lifecycle/context validation.
- Interactive Codex start, resume, work-switch, checkpoint and finish integration.
- Integration with the existing approval-driven Hermes/managed coding path.
- Durable event capture and delivery, including interruptions and uncertain
  results, using the existing separate operational/history trust boundaries.
- Focused webpage additions for approved work-plan coverage and compliance.
- Remediation of existing projects missing an architecture document or agreement.
- Cross-mode acceptance, reviewed rollout and an explicit final closeout.

### Deferred to a separately approved architecture

- Enabling unattended autonomous execution, a new scheduler or multiple workers.
- Granting Hermes general private-history access or direct database access.
- New spending authority, automatic paid-run retries or automatic merge/deploy.
- Full transcript collection, routine raw tool-output ingestion or secret-bearing
  telemetry. Recording summaries does not import an entire chat.
- Multiple repositories per project, multiple primary projects per work item,
  additional non-Git categories or non-Git baseline types.
- A broad webpage redesign, general browser authoring or replacement of the
  existing protected execution/approval/publication workflow.

The common contract must accommodate a future delegated execution mode, but this
project must demonstrate that a `delegated` label without an independently valid
delegation cannot launch work. Future autonomy will use this policy and its
identities under a separately approved execution/delegation design.

## 3. Architecture is the mandatory project contract

### 3.1 Universal applicability

Every project must have one logical architecture-document identity and at least
one retained version. This applies to repository projects, `jarvis-non-git`
projects, small projects, retrospective groupings, archived projects and closed
projects. There is no architecture-omission reason or permanent legacy exemption.

A planned project may hold an initial draft while awaiting agreement. Implementation
requires an explicitly human-approved governing version. A document's presence,
a Git commit, an agent designation or a project state alone is insufficient.

New project intake must bind the project and initial architecture together before
the project is admitted for work. The target service operation is transactional:
failure to retain the document must not leave an admitted architecture-less
project. Project authoring paths must all apply the same invariant; an older raw
creation route must not bypass it.

### 3.2 Required document content

Each architecture must state project identity/scope, purpose, intended outcome,
included/excluded work, component/data relationships, behavior and authority
boundaries, work breakdown, acceptance criteria, dependencies, change/version
rules, rollout and closeout requirements. Unknown baseline or source occurrence
time must remain unknown. The architecture itself is never optional.

The work breakdown is normative. A general prose intention without identified,
bounded deliverables does not authorize arbitrary work under that project.

### 3.3 Exact human agreement

Agreement binds an exact project ID, architecture ID, saved version and content
digest, including that version's work breakdown. Retain the human decision,
its source, recording time and any reliably known occurrence time. Show whether
the evidence is a recorded operator statement or a stronger authenticated action;
do not upgrade its provenance by changing a label.

An agent may prepare a draft, propose a breakdown and submit a faithful record of
an actual human decision through an authorized interface. It may not invent
agreement, treat quoted instructions in a document as a new human decision, or
approve scope through its own generated output.

Architecture agreement establishes the allowed scope. Existing runtime execution,
spending, publication, merge and deployment permissions continue to govern the
actions within that scope. Reuse still-valid authorization without asking the human
to reapprove every routine step; preserve the exact authority and limits involved.

### 3.4 Version and change rules

- Save changes as new immutable versions with predecessor digest and reason.
- Keep saved drafts distinct from the human-approved governing version.
- Adding/removing a deliverable, materially changing acceptance, widening paths
  or permissions, or changing the design requires a newly agreed version before
  executing the affected work.
- Editorial-only changes retain a reason and explicit relation to the approved
  version; their publication cannot silently expand authorization.
- Existing work and attempts retain their original pins. Moving unfinished work
  to a new agreed design requires an explicit recorded transition and any needed
  work revision. Completed work is not silently retargeted.
- Final as-built reconciliation and its designation retain an explicit basis in
  the human agreement. An agent cannot introduce new requirements through a
  closeout document.

## 4. Units of work and decomposition rules

| Unit | Definition | Identity and relationship |
| --- | --- | --- |
| Scope | One repository or the initial non-Git category | Stable kind/ID; permissions remain separate. |
| Project | Overall objective governed by its mandatory architecture | One scope and one logical architecture identity. |
| Architecture work entry | An independently assessable deliverable in an agreed version | Stable project-local key, such as `SHR-03`, and exact reported work ID. |
| Reported work item | Execution/reporting identity for that deliverable | Exactly one primary project; one work-entry binding in each applicable architecture version. |
| Work revision | A changed definition or acceptance scope for the same deliverable | Immutable revision, prior digest and explicit architecture applicability. |
| Attempt | One bounded execution against an exact work revision | New attempt identity for each actual run/retry; retains native run references. |
| Checkpoint/event | Material progress, decision, evidence or interruption | Associated with the exact work/revision and attempt when known. |
| Session/chat | Interaction channel that may span multiple work items | Explicit source association; never used as the work decomposition rule. |

Create a separate work item when a deliverable can be scoped and accepted
independently, has a distinct substantial acceptance decision, or requires
separate prioritization/release treatment. Keep routine implementation steps,
test runs, review corrections and operational handoffs inside the relevant work.

A retry is another attempt against the same work revision unless the scope actually
changes. A discovered defect becomes another work item when it needs independent
tracking/acceptance. It must appear in a newly agreed architecture version before
implementation. Investigation may identify and report the issue without silently
expanding the currently executing work.

Use descriptive titles that continue to match the deliverable. Titles, chat names,
branch names and PR numbers do not establish identity or project membership.

## 5. Architecture-to-history correspondence

For each work entry, the agreed architecture contains its key, exact proposed
work ID, title, purpose/deliverable, dependencies and acceptance criteria. The
history record retains the same key and work ID with references to project,
architecture version/digest and exact work revision.

The validator must establish both directions:

- Every agreed work entry has its identified reported work record, or is explicitly
  shown as approved but not yet registered. All entries must be registered before
  project implementation begins in the standard path.
- Every new reported work item assigned to the project appears in an applicable
  human-approved architecture version. Unplanned items cannot be hidden under a
  generic implementation item.
- Keys and work IDs are unique within their defined scope. One work item cannot
  satisfy several independent work entries by being counted repeatedly.
- Work revisions preserve the binding; they do not turn one deliverable into a
  collection of unrelated deliverables.
- Splitting or replacing an entry requires a new agreed version and explicit
  relationships/dispositions. Earlier entries and their reported history remain.
- A historical work entry may be removed from a later plan with an explicit human
  decision and disposition; current-work coverage and historical coverage must
  remain distinguishable.

Do not put a document's own content digest inside the bytes being hashed. Work
IDs can be allocated in a draft before approval; the approval and history records
then reference the digest of the completed exact document. Names and mutable
file URLs are insufficient bindings.

## 6. Proposed components and responsibilities

| Component | Responsibility |
| --- | --- |
| Versioned common policy | Human-readable rules, validated contract definitions, compatibility expectations and acceptance cases in Jarvis. |
| Project/architecture intake | Retain initial architecture, human agreement, work plan and immutable bindings; refuse inconsistent admission. |
| Shared context validator | Verify current project/work/revision/design/policy/scope and recording status before implementation and critical transitions. |
| Interactive adapter | Select/resume/switch exact work, call the recording client, restore context and expose pending/incomplete state. |
| Managed adapter/trusted runner | Bind reviewed job and work context before launch; capture execution facts outside the worker and apply existing authority checks. |
| Durable recording bridge | Deliver permitted records with stable keys and receipts; reconcile operational facts with private history. |
| History service | Authoritative private record storage, scoped access, immutable revisions, agreement/work-plan validation and consistent reads. |
| Read-only webpage | Display agreed architecture/work coverage, compliance, evidence and incomplete states. |

Repository `AGENTS.md` should carry concise mandatory expectations and references
to the common policy. A reusable skill should provide the repeatable procedure.
Small agent-specific adapters must use the same policy release and shared checks.
The architecture, policy and operational history have distinct identities and
versions; loading one does not imply that the others were approved or captured.

The existing managed runner already injects task-specific instructions outside the
editable worktree. Extend that reviewed handoff rather than introducing another
executor. Prevent a worker from changing the policy or validator that decides its
own admission and completion.

### Context required for governed implementation

The logical context must bind scope ID, project ID, architecture ID/version/digest,
agreement reference, work-entry key, work ID/revision/digest, policy release/digest,
baseline or applicability, permitted paths/validation requirements, execution mode,
attempt and native-session references when known, and applicable existing execution
authorization. Unknown native session IDs remain null.

Current schemas do not carry every proposed field or guarantee every new gate.
Introduce reviewed versioned contracts/bindings and an explicit migration where
needed. Preserve existing serialized records, receipts, signing keys and historical
views; do not rewrite old records to make them appear originally compliant.

## 7. Shared lifecycle and reporting format

### 7.1 Before implementation

Resolve the real repository/workspace, load the applicable policy and establish
the exact approved architecture. Create/read back the identified work records and
bindings, attach the actual session when available, and obtain durable recording
acknowledgment. Confirm the project permits work and the current execution path
is supported. Missing agreement, mismatched work, stale context or incomplete
initial recording blocks implementation.

Discussion and preparation of the initial draft precede architecture approval.
They do not grant implementation authority. The human's request to prepare this
draft is that preparation authority for this document only.

### 7.2 During work

Each executing agent has one explicit active work context at a time. Switching
deliverables selects another identified work item; resuming a chat does not
silently select its last broad project item. Delegated helpers receive an explicit
parent work/revision and attempt relationship; independent deliverables require
their own agreed work entries.

Record milestones, material decisions, validation results, scope-change requests,
blockers, handoffs and interruptions. Do not require a history checkpoint for
every shell command or harmless exploration.

The standard checkpoint contains:

| Field group | Required meaning |
| --- | --- |
| Identity/context | Exact project/work/design/policy references and attempt where applicable. |
| What changed | Bounded factual summary of progress and deliverable effects. |
| Decisions and basis | Decision, reason, source and applicable agreement/authority. |
| Validation/evidence | Actual checks/results and immutable references; unknown or unrun remains explicit. |
| Remaining work/blocker | Unresolved requirements and their practical effect. |
| Next action/handoff | What continues and who/which role must act. |
| Provenance and time | Source identity/classification, recording time and optional known occurrence time. |

Use source-system identifiers and facts where a trusted runner can supply them.
Narrative summaries remain attributed agent reports. Imported journal facts retain
their imported provenance. A valid schema or hash is not proof of human approval
or deliverable correctness.

### 7.3 Pause, interruption and resume

Persist context and pending events before handoff where possible. On resume,
revalidate project/work heads, architecture applicability and execution authority;
resume the same work ID. A crash can prevent end hooks from firing: detect the
incomplete attempt through retained runner evidence and reconcile it honestly.
Do not invent an outcome because a process or conversation ended.

### 7.4 Work completion

Record delivered scope, actual validation, unresolved items and exact evidence.
Keep reported outcome, independent validation, human acceptance, branch/PR
publication, merge and deployment as separate facts. Completion of a chat turn,
successful tool invocation or mechanical test alone does not complete a work item.

The finalizer validates the selected work revision and required evidence, retains
any pending/incomplete delivery state, and records an accurately attributed
outcome. Human-only acceptance criteria require a real human decision. Routine
steps covered by existing permission must not acquire unnecessary repeated prompts.

### 7.5 Project closeout

Reconcile every applicable architecture work entry against its reported work,
outcome and required acceptance. Unfinished work needs explicit disposition;
deferring an agreed deliverable requires a human scope decision and a revised
agreement rather than an agent-only completion claim.

Retain the final agreed architecture, exact work-plan bindings, current Git
baseline or honest omission/applicability, acceptance evidence and dated signed
closeout. For this project all nine agreed deliverables must be accepted, or its
architecture must be explicitly revised by the human before claiming completion.

## 8. Interactive Codex integration

Use global guidance to establish the actual repository and load its policy even
when a chat starts in an outer directory. Repository guidance and the coding-work
skill then establish the active project/work context.

Use supported startup/resume/compaction/tool/interruption/stop hooks where they
are verified on the actual deployed surface. Hooks can restore context, detect
missing registration and collect bounded events. A stop hook can check pending
work; it must not automatically declare the work complete.

Hook support and coverage must be rehearsed on the installed desktop/remote/CLI
paths. A hook is not a universal filesystem or authorization boundary. Where an
interactive path cannot apply the required gates, implementation must use a
reviewed controlled launch/write path. Mark unsupported paths clearly; do not
silently advertise them as enforced. Guided instructions alone are an interim
assurance level and cannot satisfy the final enforced-path acceptance claim.

All context selection uses verified record IDs. Deriving the project from a
similar title, guessing a session ID or copying unrelated environment variables
cannot establish the execution context.

## 9. Hermes and managed-work integration

Hermes proposes or selects an agreed work entry. The trusted preparation/capture
path verifies scope and exact bindings before any coding worker launches. Record
the accepted work/architecture/policy context and attempt using the existing
operational journal and approved passive history interface.

The runner supplies the worker with the exact assigned contract. It records launch,
stop, validation and publication evidence outside the worker where the current
workflow already owns those facts. Worker summaries remain separate claims.

Retain the existing fixed-identity preparation boundary, protected approvals,
one-use execution fences, independent validation and separate publication/merge/
deployment permissions. Hermes must not receive the operator's unrestricted
private-history socket, database, root journal or provider credentials to make
recording convenient. A narrow trusted adapter performs allowed transfers.

Reuse stable work IDs and explicit operational-to-engineering revision mappings.
Revision numbers in the two stores need not match. Project/work-plan association
must also be explicit; the bridge must not infer it from a native task title.

Future autonomous orchestration will select only eligible agreed work and present
valid bounded delegation. Record deadlines/budgets/retry/cancellation limits as
required by that future authority contract; this design creates no such authority.
An autonomous retry remains another attempt with its own valid authorization and
evidence, not a duplicate work item or a hidden continuation of a consumed approval.

## 10. Reliability, authority and privacy

- Initial project/work/design association requires confirmed durable recording
  before implementation. During an already admitted attempt, a history-service
  outage may use the existing durable local spool while its write succeeds and
  execution authority remains valid. New scope/attempt admission and finalization
  wait for reconciliation and receipts.
- Failure of local durable recording blocks further modifying actions through the
  controlled path. Supported read-only diagnosis and orderly stop remain available.
- Delivery replay uses the same stable keys. Replaying history never launches a
  worker, consumes another approval, repeats a paid call, merges or deploys.
- Missing/uncertain receipts remain visible. Do not delete a spool or restore a
  database to hide uncertain outcomes.
- Keep authoritative context, policy and gate code under reviewed custody. Hook
  observers and model instructions complement the trusted execution boundaries.
- Retain per-scope authorization and the distinction between private history and
  curated material readable by Hermes. Capture does not automatically publish.
- Capture allowlisted structured facts and bounded summaries. Raw transcript,
  arbitrary tool arguments, environment dumps and credentials are excluded.
- Concurrent agents use distinct active contexts and explicit work/attempt
  relationships, stale-head checks and the existing execution serialization.
  This project does not enable parallel managed workers.

## 11. Read-only webpage changes

Add an architecture work-plan view within the existing project workspace. It must
show the approved architecture reference and agreement provenance, each work key
and title, linked reported work ID, applicability/version, current outcome and
recording/acceptance completeness. Links open the existing work detail.

Provide clear counts for agreed work entries, registered work records, completed
reported outcomes, accepted deliverables and unresolved/discrepant entries. Do not
combine these counts into a single inferred success percentage.

Expose missing architecture, approval pending, missing/extra/duplicate work
bindings, stale applicability and pending delivery where trusted visibility exists.
Historical views show the plan and compliance as of their snapshot, not a later
rewritten mapping. Preserve the existing five tabs, exact document/diff/download
behavior, authentication, scope filtering and private-state clearing.

No general browser editing or new browser decision authority is included. The
initial human decision continues through an explicitly identified authorized
operator path and is retained with its actual provenance.

## 12. Work breakdown for this project

These are the proposed deliverables for the human to agree to. Each row maps to
exactly one proposed reported work ID in Section 13. The acceptance criteria in
each row define the minimum evidence for that work; Section 14 adds cross-cutting
project acceptance. All nine items are **proposed/planned in this document only**.

| Key and title | Deliverable and boundaries | Depends on | Acceptance criteria |
| --- | --- | --- | --- |
| **SHR-01 — Architecture agreement and work-plan contracts** | Versioned project/architecture agreement and work-plan bindings; initial-architecture intake invariant; explicit preservation/migration design. | Human agreement to this architecture; bootstrap in Section 15. | Project intake cannot admit a project without its architecture. Unapproved/stale design and missing/extra/duplicate work bindings refuse governed implementation. Prior bytes, identities and signed historical views survive the reviewed upgrade. |
| **SHR-02 — Shared policy and recording lifecycle** | Reviewed common policy, context validator and client start/resume/switch/checkpoint/finalize interface; durable recording integration. | SHR-01 | Exact project/work/design/policy context is validated. A chat can switch between two identified work items and a later session can resume one without duplication. Missing initial receipts, stale revisions and failed local recording block the specified transitions. |
| **SHR-03 — Interactive Codex integration** | Global/repository guidance, explicit skill entry and verified interactive hook/controlled-launch integration. | SHR-01, SHR-02 | Actual selected Codex surface records context before implementation, survives resume/compaction/work switches, and reports interruption/pending delivery. Uncovered paths are identified and cannot be presented as enforced. A turn ending cannot manufacture completion. |
| **SHR-04 — Hermes managed coding integration** | Bind preparation, capture, approved launch and runner evidence to the same project/work-plan/policy contracts. | SHR-01, SHR-02 | Model-free protocol rehearsal proves exact assigned context, attempt identity and runner-origin evidence. Existing one-use approval, scope, credentials and publication boundaries remain enforced. Missing agreement/delegation cannot launch. No paid run without its separate authorization. |
| **SHR-05 — Durable event delivery and reconciliation** | Operational/history event mapping, stable keys, receipts, pending visibility and controlled reconciliation for both modes. | SHR-01, SHR-02; integration evidence from SHR-03/04 | Outage, lost response, duplicate delivery, interrupted capture and stale head preserve evidence without duplicate work, fabricated success, secret leakage or execution retry. Operational and engineering revisions stay explicitly mapped. |
| **SHR-06 — Work-plan and compliance webpage** | Focused read-only display of agreed plan, actual work links, agreement/provenance and discrepancies. | SHR-01, SHR-02, SHR-05 | Every agreed entry links to its actual reported work. Missing architecture/agreement/mappings and distinct completion/acceptance counts are visible. Exact historical plan/document views, scope denials and private-state clearing pass browser/API checks. |
| **SHR-07 — Existing-project architecture remediation** | Inventory all existing projects and obtain genuine retained architectures/agreements/work-plan mappings where missing; preserve actual historical provenance. | SHR-01, SHR-02; display verification through SHR-06 | Every existing project has a retained architecture; every new execution has a valid agreement. The two retrospective Jarvis groupings are explicitly reviewed. Missing historical knowledge/approval remains marked unknown, with no invented dates, scope, acceptance or original design. No project receives a permanent exemption. |
| **SHR-08 — Cross-mode acceptance and failure evidence** | Independent integration fixtures and operator-guided acceptance of the full lifecycle and invariants. | SHR-03, SHR-04, SHR-05, SHR-06, SHR-07 | Section 14 scenarios pass on pinned source/runtime configurations. Synthetic, observed, imported and operator-reported evidence are distinguished. Any unverified platform path or authorized-run dependency remains explicit and blocks an overstated completion claim. |
| **SHR-09 — Reviewed rollout, runbook and project closeout** | Pinned packages, staged activation, operator procedure, final architecture/baseline/work coverage and explicit closeout. | SHR-08 | Source and host gates pass; existing data/auth/grants remain preserved except exact approved changes; operator accepts the selected live paths; all agreed work has evidence/disposition; final architecture/baseline and dated closeout read back exactly. |

These rows define deliverables rather than a requirement for nine PRs or nine
separate chats. PRs, sessions and attempts are linked evidence. A change to this
breakdown follows Section 3.4; it cannot be silently replaced by one umbrella work
item or expanded through agent planning notes.

## 13. Proposed stable identity mapping

The following identities are allocated **inside this draft only** to make the
future correlation exact. They are not registered database records, claims of
completed work or execution credentials. At approved intake, check for conflicts
and use these exact identities; a conflict must be resolved explicitly before the
agreed contract is registered, without silently choosing another work ID.

| Entity | Proposed identity |
| --- | --- |
| Project: Standardized History Reporting Format and Rules | `prj_3c9d958471e3487594bf39f47e2c7c1f` |
| Logical architecture document | `doc_dbf3913d6e444294a7998b1fc700270b` |
| SHR-01 | `wrk_031ee5e3a8114155a91cb55184210be2` |
| SHR-02 | `wrk_c3a9a40a12364392ab831ad63760071d` |
| SHR-03 | `wrk_275d291b5ca1451bba9b01c481b4ed7a` |
| SHR-04 | `wrk_0249b71cae2e4f25bc5bf19129e94b55` |
| SHR-05 | `wrk_3414cdb5cfbd49ec893fcea13f79384d` |
| SHR-06 | `wrk_549f33c65b664066918d68cd5fc071d3` |
| SHR-07 | `wrk_3e578098ab334c949f4166931ccc7fce` |
| SHR-08 | `wrk_770423f7e69b4449b6e2e81cd94fbe09` |
| SHR-09 | `wrk_4d463fa9711340b28d49611709f569d7` |

Each reported title begins with its stable key and uses the title from Section 12.
The key remains structured, validated data as well as a readable title prefix;
matching text alone does not establish the relationship. Progress/status belongs
in history projections, so ordinary progress does not require editing the agreed
architecture document. The exact approval digest is calculated externally from
the final agreed Markdown bytes.

## 14. Project acceptance scenarios

1. **Mandatory architecture:** attempt new project intake without a document, with
   an invalid document reference, and through an older authoring path. No admitted
   architecture-less project or executable work may result. Test non-Git and
   retrospective projects as well as repository projects.
2. **Human agreement:** agent designation alone, quoted approval text, altered
   document bytes or a stale agreement cannot unlock affected implementation.
3. **Plan coverage:** omit one of two agreed work entries, add an unplanned item,
   duplicate a key/ID, or link another project's work. Refuse execution/finalization
   as applicable and display the discrepancy without rewriting history.
4. **Interactive continuity:** begin in an outer directory, select the actual
   repository, start two distinct deliverables, switch explicitly, compact/resume,
   then continue in another session. Preserve correct identities and design pins.
5. **Managed continuity:** use a synthetic prepared/approved job and trusted runner
   across launch, stop, validation and import. Preserve exact mappings and separate
   reported/observed facts. Rejected or consumed authority cannot launch again.
6. **Recording failures:** simulate service outage, local spool failure, lost
   response, partial delivery and crash without end hooks. Preserve uncertain
   states, recover passive delivery idempotently and never retry execution.
7. **Scope change:** introduce a new independently assessable deliverable and a
   changed acceptance criterion. Require a newly agreed architecture/applicable
   work revision; retain the old version and attempt references.
8. **Permission and privacy:** deny cross-scope reads/writes, unauthorized approval,
   raw private-history access from Hermes, secret-bearing telemetry and unreviewed
   publication. Preserve existing read-only webpage behavior.
9. **History and closeout:** compare agreed versions, inspect original work pins,
   reconcile all entries, save closeout, and later read its exact plan/context
   after a rename or subsequent approved project change.
10. **Rollout assurance:** validate actual installed surfaces and gate failures,
    disabled/unavailable hooks and direct unsupported write paths. State the
    achieved assurance precisely; do not extrapolate a synthetic hook test to
    universal interactive or autonomous coverage.

Use model-free fixtures where they establish the boundary. Any real paid execution,
privileged installation or changed production permission retains its required
explicit authorization; the architecture does not manufacture those permissions.

## 15. Bootstrap, existing-project remediation and rollout

### This project's initial agreement and recording

The requested draft is the pre-project design artifact. After the human agrees
to an exact version and authorizes implementation, retain its exact Markdown and
decision before creating implementation records. Use the existing authorized
interfaces to save/designate it and register the nine work identities and project
memberships. Verify all links before the first implementation step. If registration
is incomplete, preserve its durable intent/receipts and pause implementation.

The approved document exists before project registration, so the architecture
requirement applies from the outset. The existing platform's multi-call setup
provides a procedural bootstrap; it must not be represented as the transactional
enforcement that SHR-01 will deliver. No bootstrap step permits implementation
without the approved architecture or collapses this effort into the completed
Engineering History Workspace project's work item.

Until SHR-02 publishes the shared policy release, Sections 3–10 of the exact
human-agreed architecture are the bootstrap policy, identified by that architecture
version/digest. Existing repository and execution permissions still apply. Record
the initial work keys through the document's exact ID mapping and supported
history references; SHR-01 adds the structured validated binding without rewriting
the initial records. Transition to the implemented policy/bindings explicitly and
retain the earlier context. This avoids requiring an as-yet-unbuilt policy engine
to authorize its own first implementation, and avoids claiming that engine is
already enforcing the bootstrap.

### Existing projects

Inventory every project, including archived/closed records. A missing architecture
or agreement is a current compliance defect, displayed explicitly. Retain readable
historical evidence while blocking new implementation under an incomplete contract.
This is a remediation state, not an exception to the mandatory architecture rule.

The existing Engineering History Workspace project already has retained design
versions and an accepted closeout. The retrospective Engineering History Foundation
and Dashboard and Managed Coding Workflow Documentation groupings currently lack
their own recorded architectures. SHR-07 must prepare current, honest retrospective
documents and obtain human agreement before declaring the estate compliant.

Human agreement to a retrospective architecture authorizes the current documented
grouping and any explicitly agreed future work. It cannot authenticate an unknown
original design or approve earlier actions retroactively. Do not change old work
bytes, invent source times or silently reopen a completed historical project.

### Staged activation

First prove contracts and passive checks, then the shared lifecycle, each agent
adapter and delivery path, the compliance view and remediation. Run the cross-mode
acceptance before production enforcement is claimed. Retain an observable audit
stage during deployment verification; it does not authorize work lacking an agreed
architecture and cannot qualify as final enforced acceptance.

Stage exact reviewed packages and policy versions. Preserve existing database
records, signing keys, authentication and grants; separately review any exact new
principal or tool capability required for the adapters. Use an explicit stopped-
service migration only where required. Retain diagnostic evidence on failure;
recovery must preserve later history and must not restore a database to repair
deployment metadata.

Finish with live operator acceptance, an accurate per-work outcome/acceptance
matrix, a retained final architecture and Git baseline, and explicit project
closeout. Source merge, deployment and agreement remain identifiable records.

## 16. Assumptions proposed for review

- This is a new `jarvis` project with the nine deliverables and identities above.
- The mandatory-architecture principle is confirmed; the detailed mechanics,
  first-release scope and work breakdown in this draft remain proposed.
- A draft architecture is required at project creation; a human-approved governing
  version and registered work breakdown are required before implementation.
- The first release covers interactive Codex and the existing approval-driven
  Hermes coding path. Autonomous execution authority remains a future project.
- Existing projects must be brought into compliance through honest retained
  documents and human decisions, with no historical backdating or exemptions.
- Initial admission requires confirmed recording; the bounded in-progress outage
  policy in Section 10 permits durable buffering but blocks new admission and
  finalization until reconciled.
- The webpage additions are limited to work-plan correspondence and compliance;
  broader visual customization remains separate.

These are concrete proposed choices for the human's review, not claims that they
have already been approved by requesting a draft.

## 17. Design inputs and compatibility references

Existing local architecture and contracts:

- [Retained history/data architecture review](JARVIS-HISTORY-ARCHITECTURE-AND-DATA-REVIEW-20261105.md).
- [Approved project workspace architecture v0.2](JARVIS-PROJECTS-AND-WEB-UI-ARCHITECTURE-DRAFT-v0.2-20261106.md).
- [Project workspace implementation reconciliation](PROJECT-WORKSPACE-AS-BUILT-ARCHITECTURE-20261107.md).
- [Completed v0.2 project evidence](PROJECT-WORKSPACE-v0.2-COMPLETED-20261107.md).
- Jarvis `engineering/docs/engineering-history-operator-runbook.md`,
  `engineering/docs/workflow-record-contracts.md`,
  `engineering/docs/workflow-operator-runbook.md`,
  `engineering/tools/rras_native/manual_runner.py`, and the existing project,
  history-client and managed-link contracts/implementations.

Official documentation reviewed for the preceding research:

- [Codex instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
- [OpenAI skills](https://learn.chatgpt.com/docs/build-skills).
- [Codex hooks and coverage limits](https://learn.chatgpt.com/docs/hooks).
- [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode).
- [Hermes context files](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files).
- [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills).
- [Hermes hook types and failure behavior](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks).

External documentation informs adapter options; it neither proves support in the
installed pinned runtimes nor changes this agreed scope when the upstream page
changes. SHR-03/04 must verify actual compatibility and retain the selected runtime
and policy versions in acceptance evidence.
