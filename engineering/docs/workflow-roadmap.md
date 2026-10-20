# Hermes/Codex workflow: loose roadmap

Accepted October19,2026. This is the working roadmap, not permission to activate
services, spend on a coding task, merge/deploy changes or expand worker authority.
Adjust implementation detail as evidence warrants; preserve the intended outcomes.
The filesystem/source migration is complete and is not the next product slice.

## Intended product

An operator prepares bounded work with Hermes, explicitly approves managed
execution, inspects independently validated results/evidence and publishes an
assigned review branch/draft PR. Human merge and deployment remain separate.
Registered repositories use the same workflow through configuration rather than
per-objective scripts. Ordinary interactive Codex work remains supported.

Interactive, approval-driven and future delegated/autopilot modes share identities,
records and eventual control interfaces. A GUI will be another client. Describing
delegated mode does not enable it. Hermes preparation does not approve execution.
Start with one managed task globally; retain exclusion when stopping is uncertain.

The durable history includes interactive and managed work, requests, decisions,
approvals, scope changes, attempts, validation, artifacts, commits/PRs and later
merge/deployment/verification outcomes. Mark imported and human-reported claims
separately from observed evidence. Work journals include failures and unfinished
work; release summaries distinguish produced/published/merged/deployed/verified.
External tools/chats are not automatically observed: explicit import/reconciliation
and provenance are required. Local evidence survives ledger outages; indexing is
secondary to durable artifacts and must not trigger coding retries.

## Next phase: reusable operator control and record foundation

1. **Shared contracts (current slice):** versioned repository registrations,
   revisioned work items, immutable attempts and append-only event envelopes;
   stable identities, modes, actors, UTC timestamps, provenance and artifact
   references. Map existing request/approval/export/publication formats without
   rewriting their authority contracts. No storage, launch or ledger activation.
2. **Repository admission and operator interface:** adapt existing capture,
   approve, launch and evidence components into consistent supported commands.
   Introduce bounded Jarvis admission and separate historical robot recipes.
   Adding an ordinary repository should need registration/validation configuration,
   not new launcher code. Never promote model-supplied shell to privileged validation.
3. **Recording and visibility:** implement durable events/artifacts, status/history
   queries for operator and Jarvis, explicit interactive-session imports and
   reviewable summaries. Queue future ledger indexing through a durable outbox.
4. **Acceptance and packaging:** source/model-free checks, then appropriate isolated
   UID996/systemd acceptance before installing changed privileged components.
   Update supported architecture, operations and installation guidance together.

Step1 defines data and consistency rules only. Steps2–4 must implement authenticated
capture, admission, write ordering/idempotency, storage and read permissions. A
valid schema or a self-declared actor/provenance value is never an approval.

## Next-phase acceptance criteria

- Two different repositories/objectives use the same commands without generated
  launch scripts; another ordinary repository is added through registration.
- Preparation never authorizes execution. Changed scope, baseline or configuration
  invalidates approval; one-use approval and global managed-slot exclusion remain.
- Successful, failed and unfinished attempts are discoverable by work/repository.
- Interactive work is explicitly linkable; no automatic universal chat observation
  is claimed. Imported assertions retain their provenance and uncertainty.
- Operator and Jarvis retrieve bounded summaries/references without credentials or
  private logs being exposed. Read permissions remain distinct from execution rights.
- Summaries preserve verified-versus-reported distinctions and never label merely
  produced or unmerged changes as released. Human acceptance stays explicit.
- Restart/outage tests prove durable records and retained pending index events.
- No paid task is needed to prove this phase. Source fixtures are not privileged
  host acceptance; repeat changed host boundaries with harmless fixtures.

## Deferred tasking

Later slices include full guarded cancellation/interrupted-launch recovery, unified
finish/custody/publication with draft-PR receipts, and production ledger indexing.
Ledger availability/schema/grants must be inspected before a separate cutover;
current stopped schema1–8 is not upgraded merely because source includes9–11.

GUI, autopilot execution/delegation enforcement, multiple workers, local budget
limits, richer recipes/robot field evidence, centralized/off-host backup work and
stronger containment for demonstrated needs remain deferred. Portal spending policy
is current practice; no local task/day/month ceiling is claimed. Do not upgrade
Hermes/Codex/model pins or resume robot example work to implement this roadmap.

## Progress

- Step1: shared contracts merged in PR15.
- Step2: admission preparation merged in PR16; trusted operator control merged in
  PR17. The bounded Jarvis documentation configuration is installed. Other ordinary
  repositories still require their own reviewed registration and validation recipe.
- Step3: journal/artifact/outbox and interactive imports merged in PR18; configured
  managed recording, receipt reconciliation and projection-only history MCP merged
  in PR19. These interfaces are now installed. The real journal starts empty;
  explicit imports and explicit snapshot publication remain operator actions.
- Step4: actual Hermes MCP2, disposable read-only same-image fixture and offline
  root/UID996/systemd acceptance passed; see [acceptance](workflow-acceptance.md).
  PR21 added committed-source/offline packaging and atomic projection publication.
  After separate human installation approval, release `workflow-421ce120c6da` was
  activated and independently verified on October20,2026. See the
  [installed paths and verification](workflow-production-package.md#installed-october202026).
- This completes installation of the control/record foundation. It does not claim
  an end-to-end successful managed coding task or completion of every product
  acceptance criterion. Native finish/custody/publication and draft-PR receipts
  are the next unfinished integration slice. Ledger delivery, GUI/autopilot and
  the other deferred slices remain pending. No paid task ran during installation.
