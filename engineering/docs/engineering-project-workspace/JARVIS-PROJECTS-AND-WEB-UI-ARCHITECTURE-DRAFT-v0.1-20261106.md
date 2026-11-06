# Jarvis project organization and history webpage architecture

Version: **0.1 — first proposal for review**  
Date: November 6, 2026  
Status: Draft; decisions below are proposed and have not been implemented.

## 1. Purpose and relationship to the retained review

This document proposes the architecture for two additions to the engineering-history system:

1. Organize related work items into projects, with an overview, baselines and a versioned architecture document for each project.
2. Make that organization the basis for browsing projects and their work on the webpage.

The retained [November 5 architecture and data review](JARVIS-HISTORY-ARCHITECTURE-AND-DATA-REVIEW-20261105.md) describes the existing system. It remains the starting-point assessment and is unchanged. This document describes the proposed next system. Later revisions of this proposal should retain their own version and change summary rather than replace that baseline review.

This pass defines organization, data relationships, document history and webpage behavior. Broader visual customization and other webpage features can be added in subsequent design passes. No application changes, data migrations or deployment were performed for this document.

### Proposed organizing principle

```text
Repository or non-Git category
    └── Project
        ├── Overview and scope
        ├── Baseline history
        ├── Versioned architecture document
        ├── Work items and their existing records
        └── Project change and closeout history
```

A project is a durable engineering effort with a purpose and design. A work item is a bounded piece of work contributing to that effort. A project may span many work items, chats, commits and PRs.

## 2. Requirements and first-pass design choices

### Requirements from your request

- Related work items can be aggregated under one project.
- Each project has associated overview information and baselines.
- Each project has an architecture document with retained versions and visible changes as the effort develops and closes.
- Projects are organized by the repository they concern, including `jarvis`, `robot_ws` and other repositories, or by a category outside Git work.
- The webpage reflects this organization.

### Recommended choices for this first version

| Choice | Proposal | Reason |
| --- | --- | --- |
| Project home | Each project has one repository or one non-Git category. | Gives it a clear location and access boundary. |
| Work membership | A work item has at most one current primary project. | Avoids double counting and ambiguous ownership. |
| Existing work | Work without a project remains visible as **Unassigned work** within its existing scope. | Preserves existing records without guessing their purpose. |
| Project design | One logical architecture document per project, with immutable numbered versions. | Provides one identifiable design history. |
| Governing design | An explicit designation selects the architecture version governing current work. | Saving a draft should not silently change the agreed design. |
| Baselines | Versioned baseline sets, separate from individual work-item baselines. | A project starting point and a later task starting point can differ. |
| Project closure | Record an explicit closeout snapshot and retain all earlier history. | Preserves what the project meant and contained when it closed. |
| Initial webpage | Read-only project browsing, document history/comparison and work navigation. | Fits the deployed read-only architecture; editing controls can be designed later. |

These are recommendations for review, especially the single-repository project and single-primary-project rules. Cross-repository initiatives and secondary work associations are possible later extensions; they are not assumed in this first pass.

## 3. Repository and non-Git organization

Use an **organization scope** to mean either a repository identity or a non-Git category. This is a data-model term; the webpage can simply say “Repositories” and “Non-Git projects.”

### Repository scopes

- Preserve existing stable repository identities such as `jarvis` and `robot_ws`.
- Store a display name and, when explicitly recorded, a credential-free repository URL.
- Treat additional repositories as distinct identities.
- The webpage may group less frequently used repositories under **Other repositories**, but projects still retain their actual repository identity.
- Do not store every additional repository as a generic `other` repository: that would discard the identity needed for history and access checks.

Adding a display identity does not admit a repository for managed execution. Repository execution admission continues to belong to the existing protected workflow.

### Non-Git scopes

Non-Git categories have stable category IDs, display names and descriptions. They allow projects that have no meaningful repository association.

Possible labels, for discussion, include **Research**, **Operations**, and **Planning**. These are examples, not categories created by this proposal. An **Uncategorized** non-Git scope can preserve an explicitly non-Git project whose category has not yet been selected.

Non-Git records must identify themselves as non-Git. They must not pretend to be repository `other`, use a fake commit, or be attached to `jarvis` solely because its database stores them.

### Example navigation hierarchy

All names below are illustrative; they do not assert existing project assignments.

```text
Repositories
  jarvis
    Engineering History Workspace
    Managed Workflow Improvements
    Unassigned work
  robot_ws
    Navigation Reliability
    Unassigned work
  Other repositories
    actual_repository_name
      Project name

Non-Git projects
  Research
    Local Model Evaluation
  Operations
    Backup and Recovery Planning
  Uncategorized
    Project awaiting category selection
```

**Unassigned work** means a work item lacks a project. **Uncategorized** means a non-Git project lacks a more specific category. They solve different problems and should remain distinct.

## 4. Project model

### Project information

The following describes the desired logical data, not a final JSON schema or SQL migration.

| Attribute | Meaning |
| --- | --- |
| Project ID | Stable identity independent of its name; proposed prefix `prj_`. |
| Organization scope | Exactly one repository identity or non-Git category identity. |
| Name | Human-readable title; names may change without changing identity. |
| Overview | Concise description of the effort and why it exists. |
| Intended outcome | What the project is expected to deliver. |
| In scope / out of scope | Boundaries used to interpret its work and design. |
| Owner | Optional explicitly recorded owner; unknown remains unknown. |
| State | `planned`, `active`, `paused`, `completed`, or `cancelled`. |
| Current architecture reference | Exact designated governing document ID/version/digest, or explicit “not designated.” |
| Starting and current baseline references | Exact baseline-set references, or an explicit not-recorded state. |
| Revision and provenance | Immutable revision identity, recording time, optional source occurrence time, submitting principal and reported source. |
| Archive state | Whether the project is hidden from default browsing; independent of completion/cancellation. |

The project overview is a structured summary for browsing. The architecture document is the longer design governing how the effort will be built. They should agree, but neither should be generated from the other in a way that silently changes scope.

### Project history rules

- Metadata edits create a new revision with a reason and previous-revision reference.
- A proposed edit supplies the project head it was based on; stale edits fail rather than overwrite a newer change.
- State changes, architecture designation, baseline changes, work membership changes and closeout are separately identifiable history events.
- Renaming preserves the project ID and old recorded names.
- A project stays in its original organization scope in the first implementation. Moving a whole project between repositories/categories requires a separately designed reclassification procedure.
- Archiving affects default visibility only. History, links and downloads remain available to authorized readers.

### Relationship to work items

Each work item keeps its existing identity, scope revisions, session associations, checkpoints, outcomes and documents. Project membership is an additional relationship; grouping a work item must not rewrite its original records or change its work-revision digest.

New work can be explicitly assigned to a project. Existing work can be assigned retrospectively, with the assignment's real recording time and an explanation. No project membership is inferred from a similar title, shared chat, branch name or PR.

For repository work, the work item's repository must match the project's repository. Non-Git work must match its project's category. A project association does not change repository permissions.

## 5. Work membership and design traceability

### Membership information

| Attribute | Purpose |
| --- | --- |
| Work ID and project ID | Explicit association of the existing work with its project. |
| Association event ID | Stable identity for assignment, reassignment or removal. |
| Previous association reference | Preserves the history of where the work belonged. |
| Reason | Why the relationship was created or changed. |
| Governing architecture reference | Exact architecture version this work is intended to follow, or explicit “not designated.” |
| Recorded/source times and provenance | Distinguish a retrospective association from original creation. |

The same work cannot have two current primary projects. A reassignment atomically ends the old current membership and establishes the new one, retaining both in history. Concurrent assignments use an expected-association head to prevent conflicting current memberships.

Reassignment is limited to projects in the same organization scope in this first version. Removing membership returns the item to that scope's **Unassigned work**. Assignments to archived or closed projects are refused until an explicit reopening/unarchive action, as appropriate.

### Which architecture governed a work item?

At assignment, explicitly record the project's governing architecture version as the work's design reference. If no governing version exists, record that absence; do not invent one.

If architecture v3 later becomes governing, work previously associated with v2 continues to show v2. Moving ongoing work to v3 requires an explicit recorded design-reference change. Historical references remain visible.

This prevents a later document edit from making earlier work appear to have been designed against requirements that did not yet exist. Existing work may be linked to an older architecture version retrospectively only with a clear reported basis and recording time.

Changing the project design reference does not itself revise a work item's accepted scope. If the work objective, criteria or allowed paths change, the existing work-revision process must also record that change.

### Counts and aggregate status

Project work counts use distinct work IDs, not numbers of revisions, sessions or events. Current membership supplies current counts; historical snapshots use membership as of their snapshot.

Show reported outcome counts separately from the operator-recorded project state. A `completed_claim` is not verified acceptance, and an outcome tied to an older work revision must be labeled with that revision. A project does not become completed automatically because its work items report completion.

## 6. Baselines: preserve the starting point and later changes

A project baseline records an agreed reference point. It may include code, requirements, prior documentation, configuration descriptions or other evidence. The baseline is a record of what was selected and known; recording it does not automatically verify the source.

### Baseline sets

A baseline set is an immutable, versioned collection of entries. Each revision has an ID/version/digest, previous-set reference, change summary, provenance and recording time. Project history explicitly selects the starting set and subsequent current sets. The original starting set remains retrievable.

| Entry kind | Information to preserve |
| --- | --- |
| Git source | Repository ID, exact commit, recorded ref/branch label, capture time and verification basis. A ref alone is not an exact source baseline. |
| Retained document | Document identity/version, exact content digest and its role in the project. |
| External reference | Source identity/URL, description, source time if known, optional content digest and retrieval/verification limits. A URL alone does not preserve its bytes. |
| Recorded state | Bounded description of a starting operating/configuration state, supporting evidence references and explicit unknowns. Avoid secrets and full private configurations. |

An entry also has a label and purpose, such as “existing implementation,” “requirements starting point,” or “closeout reference.” Unknown values remain explicit. Referencing a private source does not grant access to it; a reader sees only what their existing permissions allow.

Architecture versions pin the baseline set they describe. Later changes to project baselines do not silently retarget older architecture versions.

### Project versus work-item baseline

Example:

- Project starts from commit **A** and the retained November 5 review.
- Work item 1 starts at **A** and produces a change merged at **B**.
- Work item 2 starts at **B**.
- A revised architecture adopts baseline set 2, identifying **B** and the new requirements.

All four facts can coexist. Updating the project's baseline does not overwrite work item 1's baseline or imply that every subsequent work item started at the same commit.

For a non-Git project, a baseline can consist entirely of documents, external references and recorded state. It need not contain a Git entry.

## 7. Versioned project architecture document

### Identity and immutable versions

Each project has one logical architecture document, identified independently of its filename. Its versions are numbered consecutively and retain:

- Document ID, project ID and version number.
- Exact stored UTF-8 Markdown bytes and SHA-256 digest.
- Previous saved version's identity/digest.
- Title and meaningful change summary.
- Project revision and exact baseline-set reference at creation, including explicit missing-baseline state where applicable.
- Author/source attribution, submitted principal, recording time and nullable source occurrence time.
- Optional external/Git source reference when imported.

Saving changed content creates a new version. Version numbers and digests in this model are separate from Git commit identities and from this proposal's editorial version label `0.1`.

### Draft versus governing design

Saving a version retains a draft. An explicit **design designation** event selects which saved version governs the project, with its reason, exact version/digest and provenance.

For example:

```text
v1 saved → v1 designated as governing
v2 saved as a draft → v1 still governs
v2 designated as governing → v1 retained as the earlier governing design
v3 saved as a draft → v2 still governs
```

The governing pointer is the result of designation history; old versions are never rewritten to change their original content. If an earlier version must govern again, record a new designation and reason rather than erase intervening versions. Concurrent saves and designations use expected heads/version references and atomic service validation.

“Governing” means the recorded design the operator selected. It does not grant execution, paid-task, merge or deployment authority, and reported author labels are not authenticated human identity.

### Required reader behavior

- Open any authorized saved version and download its exact Markdown.
- Show current governing version separately from the latest saved draft.
- Compare any two versions; default to the governing version and its preceding governing version when available.
- Show exact added/removed text as the authoritative comparison. An optional narrative summary cannot replace that diff.
- Display who/what reported the change, when it was recorded, the change summary and applicable baseline set.
- Show which current work items reference each architecture version.
- Return the same historical bytes after templates, renderers or webpage layout change.

The initial webpage can retain the current exact Markdown text viewer and add a text comparison view. Rich Markdown rendering is a separate presentation choice, not required to preserve version history.

### Recommended architecture template

1. Project purpose, overview and intended outcome.
2. Scope, exclusions and assumptions.
3. Baselines and existing architecture.
4. Requirements and acceptance expectations.
5. Proposed components, data and relationships.
6. Work breakdown and design dependencies.
7. Webpage behavior, where relevant.
8. Validation approach and evidence limits.
9. Open decisions, risks and deferred work.
10. Version change summary and closeout reconciliation when applicable.

Project architecture documents are a new document role. The current `review`, `checkpoint` and `completion` work-document types must remain intact; project design should not be hidden in a fabricated work item or relabeled as a task review.

## 8. Project closure and historical views

Completion is explicitly recorded. The proposed completion rule requires:

- A designated governing architecture version.
- A closeout summary describing what was delivered and what remains.
- A final baseline-set selection, or an explicit explanation that final baseline evidence was not recorded.
- Recorded disposition of unfinished work: remains pending, handed to another active project, deferred or cancelled. No fabricated completion claims.

The resulting closeout snapshot pins the project revision, governing architecture version/digest, selected baseline set, membership and design-reference state at closure, plus the exact work revisions/outcome records considered. Later work notes or reassignment must not alter this historical snapshot.

A final architecture version should reconcile the intended design with what was actually delivered, including deviations and deferred parts. It can be designated before closure. Cancellation records a cancellation reason and snapshot of whatever design/evidence exists; it does not require inventing a final architecture document.

Reopening appends an explicit event and starts a new active period. Earlier closeout snapshots remain available. The project header distinguishes **Current view** from **At closeout on [date]**, and an old closeout document is never labeled as the latest design after reopening.

Project state remains distinct from PR merge, deployment and runtime verification. Those facts retain their existing evidence/provenance requirements.

## 9. Webpage information architecture

### Primary browsing path

The proposed default path is **scope → project list → project workspace → work item**. Preserve a direct **All work** view and per-scope **Unassigned work**, so existing history is accessible before classification is complete.

The navigation uses:

```text
All projects
All work
Repositories
  jarvis
  robot_ws
  Other repositories
Non-Git projects
  [configured categories]
```

Only authorized scopes appear. “Other repositories” is a navigation grouping; selecting it shows the actual repository identities rather than flattening them into one identity. A selected repository/category has a project list and an unassigned-work entry. Breadcrumbs preserve context when opening a work item or an older document version.

### Project list

Each row/card shows:

- Name and short overview.
- Repository or non-Git category.
- Explicit project state.
- Number of currently assigned work items.
- Governing architecture version, with a separate draft indicator if newer drafts exist.
- Last project update and last associated work activity as separately labeled times.

Filters cover scope, project state and archive visibility. Initial project search matches project name, overview and intended outcome within authorized scopes. Document-content and whole-history search can be designed later. Do not show a percentage-complete indicator unless its meaning is separately agreed.

### Project workspace

```text
jarvis / Projects / Engineering History Workspace

Engineering History Workspace                       Active
Overview of the project and its intended outcome
Governing architecture: v2     Newer draft: v3
Work: 8 items                 Baseline set: v2

[Overview] [Work] [Architecture] [Baselines] [History]
```

The numbers and versions in this illustration are examples only.

| Tab | Required content |
| --- | --- |
| Overview | Purpose, outcome, scope/exclusions, owner if known, state, design/baseline references and closeout summary where present. |
| Work | Existing work grouped under the project; title, current scope revision, reported outcome with its revision, design version and last recorded activity. Open the existing work detail from here. |
| Architecture | Governing document, saved-version list, change summaries, exact view/download, version comparison and work associations. Clearly distinguish drafts. |
| Baselines | Starting/current/closeout selections, immutable set versions, entries, source/verification limits and links to retained evidence. |
| History | Project revisions, state changes, assignments/reassignments, baseline changes, saved/designated architecture versions, closeout and reopen events. |

The existing work-detail tabs—Overview, Timeline, Documents and Evidence—remain available. Add project identity and the work's architecture reference to their context. The back link returns to the originating project/filter rather than resetting navigation.

### Historical navigation

- Version-specific URLs identify exact document versions; renaming a project does not break them.
- Closeout URLs identify an exact snapshot.
- Views explicitly say whether they show current membership or membership at a historical snapshot.
- Counts and list pages in one historical view use the same snapshot boundary.
- A project without architecture or baselines shows a useful empty state, not an error or an invented default.
- An empty authorized scope says “No recorded projects”; it does not imply no engineering occurred there.

Project management and document editing buttons are outside this initial read-only webpage slice. Categorization and document changes need supported explicit authoring/intake commands, but that does not require introducing browser action authority now.

## 10. Storage and service architecture

### Extend the private engineering-history service

Keep the private history service as the owner of project records, relationships, document bytes and authorized read projections. SQLite remains suitable for this addition. The webpage should consume project-oriented service reads rather than reconstruct the new relationships by scanning unrelated work in browser JavaScript.

The current submission format assumes every operation has a work ID and validates only the existing work operations. Therefore project records must not simply be inserted into the existing log without a new contract and compatible reader path.

Recommended storage direction:

| Logical collection | Responsibility |
| --- | --- |
| Scope records | Repository display identity or non-Git category identity and revision history. Execution admission remains separate. |
| Project records/events | Immutable metadata revisions, lifecycle changes, document designation, baseline selection and closeout snapshots. |
| Membership events | Append-only work assignment, removal, reassignment and per-work architecture reference history. |
| Project document versions | Exact Markdown bytes and immutable manifests. |
| Baseline-set versions | Exact entries and provenance for each saved set. |
| Read projections/indexes | Current scope/project lists and snapshot views; rebuildable from authoritative records. |

The preferred implementation is additive tables within the existing service-owned database, with a versioned project contract and explicit transaction handling. Exact SQL and wire schemas belong in the implementation design after this logical model is reviewed. Existing v1 submission bytes and receipts remain untouched.

All new writes need idempotency keys, receipts, digest validation, stale-head protection and atomic relationship validation. A reassignment cannot transiently count the work in two current projects; a closeout cannot mix independently advancing project/work heads. Snapshot construction must bind the exact records it uses.

The service's current 10,000-record and bounded-read limits remain implementation constraints to review. An additive schema alone does not establish larger-scale performance. New list/read endpoints should paginate and carry a consistent view boundary rather than require the current full-repository scans.

### Supporting non-Git work honestly

Existing private work definitions require `repository_id`. Non-Git work therefore requires a new versioned work contract, not just a new webpage filter.

The proposed new work scope is an explicit choice between:

```text
Repository work:  repository identity
Non-Git work:     category identity
```

Readers interpret existing v1 work as repository-scoped using its existing `repository_id`; they do not rewrite its original request/digest. New non-Git work uses the new contract. Adapters must support both before non-Git intake is enabled. Per-work baseline handling must also allow document/state baselines without a fabricated Git baseline.

### Authorization and compatibility

Project reads and writes inherit the same organization-scope boundary as their contents. Repository permissions continue to be explicit; non-Git categories need equally explicit category grants. Assignment, document lookup and comparison validate both the target identity and its scope. Aggregated counts/search must not disclose inaccessible projects or work.

The dashboard remains a read-only principal. Authoring uses the appropriate explicit operator/service interface. No wider Jarvis MCP access follows from adding projects; curated publication remains separate.

Managed export/import continues to bind operational work identity and its exact engineering scope. Project membership is a separate private-history association, so importing an existing managed event does not recreate work, change its baseline or create a project automatically. The root workflow journal and legacy PostgreSQL ledger do not need to become project-management stores.

## 11. Existing-history adoption and delivery sequence

This is a proposed implementation order for later authorization, not work performed now.

1. **Review the model:** settle the scope/membership rules, baseline meaning, document governance and closeout semantics below.
2. **Specify contracts and migration:** additive project storage, compatible reads, non-Git work representation, explicit grants, receipts and recovery. Exercise migration/reopen on a disposable copy and preserve original data/receipts.
3. **Add explicit authoring/intake:** create/revise projects and categories, assign existing work, save/designate architecture versions and record baseline sets. No automatic classification or document scraping.
4. **Review existing assignments:** produce a reviewable work-ID-to-project mapping. Unknown memberships stay unassigned. Capture retrospective reasons/times without claiming original project intent was known.
5. **Build the read-only webpage slice:** scope navigation, project list/workspace, historical architecture comparison and contextual work detail.
6. **Validate and review before rollout:** demonstrate the acceptance scenarios below, then make a separate deployment decision.

If you choose this effort as the first project, a possible name is **Engineering History Workspace**, under `jarvis`. The retained November 5 review could be one starting baseline document, and an accepted revision of this proposal could become its first governing architecture. Those are suggested assignments, not records already created.

## 12. Acceptance scenarios for the eventual implementation

| Scenario | Required result |
| --- | --- |
| Create two projects in `jarvis` | Work can be grouped separately and browsed without confusing project names with repository identities. |
| Add a `robot_ws` project and another repository | Each stays under its true repository; “Other repositories” preserves the additional repository's identity. |
| Create a non-Git project/work item | Uses a real category identity and non-Git scope, with no fake repo or commit. |
| Assign an existing work item | Existing work bytes, digests, receipts and documents are unchanged. |
| Reassign work within a scope | Exactly one current primary membership; old association and reason remain visible. A conflicting/stale assignment is refused. |
| Save architecture v2 while v1 governs | v2 is visible as a draft; v1 remains governing until explicit designation. |
| Designate v2 | New work can reference v2; prior work's v1 reference is preserved unless explicitly changed. |
| Compare/download old versions | Exact earlier bytes and an accurate diff remain available after later saves. |
| Update a baseline set | Starting and older architecture/work baselines remain intact. |
| Read legacy and new work together | v1 repository work and the new contract remain retrievable without rehashing old records. |
| Close and reopen a project | The prior closeout membership/design/work references remain reproducible. Current and historical views are distinguishable. |
| Denied scope access | No metadata, counts, document bytes, comparisons or search results leak through project aggregation. |
| Lose an intake response | Retry recovers the original receipt without duplicate versions or assignments. |
| Browse before classification | Unassigned work remains discoverable and existing direct work links keep working. |

## 13. Decisions to review before the next draft

1. **Project scope:** is one repository/category per project right for this first version, or does one of your current efforts need multiple repositories immediately?
2. **Work membership:** should work have one primary project, as proposed, or do you need the same work counted under several projects?
3. **Non-Git categories:** which initial names and distinctions would be useful to you?
4. **Project information:** are overview, intended outcome, scope/exclusions, optional owner, state and baseline references enough for the first pass?
5. **Design versions:** does an explicitly designated governing version plus separately saved drafts match how you want to work?
6. **Baselines:** do you want the full set model—Git commits, retained documents and other recorded state—or a narrower initial baseline?
7. **Webpage:** does scope → project → work, with Overview/Work/Architecture/Baselines/History, match the way you want to browse?

## 14. Document history and source basis

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | November 6, 2026 | First proposal for project grouping, repository/non-Git organization, baselines, architecture-document versions and the corresponding webpage structure. |

Retained baseline review: `JARVIS-HISTORY-ARCHITECTURE-AND-DATA-REVIEW-20261105.md`, SHA-256 `75c9c49933245dc40f7ac1eaae78a6de59ce19161cee12ac564baa9903de496e`.

Source recheck on November 6: the local reviewed source at `40d739949ac6f4194e0ccf0fe96dcfd75f624d51` still has no file differences from GitHub `main`, whose additional PR #88 merge is `87fb60b1f13003daf90ad94cbed6d96053d04ec6`. Current-implementation statements above are grounded in the retained review and these pinned sources:

- [Existing private-history contract](https://github.com/shanereviello/jarvis/blob/87fb60b1f13003daf90ad94cbed6d96053d04ec6/engineering/contracts/engineering-history-v1.schema.json): work-oriented operations, required repository identity and existing document roles.
- [Existing store](https://github.com/shanereviello/jarvis/blob/87fb60b1f13003daf90ad94cbed6d96053d04ec6/engineering/tools/rras_history/store.py): immutable submissions, receipts, current-head checks and storage bounds.
- [Service access boundary](https://github.com/shanereviello/jarvis/blob/87fb60b1f13003daf90ad94cbed6d96053d04ec6/engineering/tools/rras_history/access.py): explicit repository-scoped access.
- [Current webpage read model](https://github.com/shanereviello/jarvis/blob/87fb60b1f13003daf90ad94cbed6d96053d04ec6/engineering/tools/rras_history_web/history.py): repository history aggregation and work/document projections.
- [Current webpage routes](https://github.com/shanereviello/jarvis/blob/87fb60b1f13003daf90ad94cbed6d96053d04ec6/engineering/tools/rras_history_web/app.py): authenticated read-only presentation.

This proposal is a design artifact for your review. The retained review, source records and deployed system remain separate from the proposed project records described here.
