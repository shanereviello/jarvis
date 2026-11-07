# Linear project, execution issue, and architecture decision templates

Use the Reviello Robotics workspace selected by the operator. Discover and confirm
its actual team/project UUIDs through the authorized connection. Names below are
templates, not claims that any Linear object already exists.

## Project

Name: Standardized History Reporting Format and Rules

Overview: Robust owned engineering reference and debugging, using Linear for work
and direct Jarvis/Codex communication, evaluated capture, and the existing history UI.

Resources: retained governing architecture/version/digest; Jarvis project URL;
starting Git baseline; this work breakdown. Keep the human as project lead/owner.
Agents participate as distinct app actors/delegates rather than project leads.

## Execution issue

Title: SHRR-xx: bounded deliverable

- Jarvis project ID and work ID; architecture plan ID; Linear issue UUID after creation.
- Governing architecture document/version/SHA-256 and human agreement source.
- Objective, scope/exclusions, acceptance criteria and dependencies.
- Current work revision and Git baseline; relevant branch/PR when present.
- Human assignee, active agent/delegate, optional coordinator, native/runtime session references.
- Engineering checkpoints, validation/evidence, open questions, next step.

Use the eight existing SHRR definitions from the architecture. Resolve existing
UUID mappings before creating anything; uncertain writes need reconciliation,
not another issue with a new name. Keep approval/decision and parent grouping
issues distinct from the execution issue set counted as delivered work.

## Architecture decision / deviation issue

Title: Architecture decision: project and exact candidate version

- Retained candidate document/version/SHA-256 and readable content link.
- Current governing version; exact diff/change summary.
- Affected plan/work IDs and what implementation is waiting.
- Reason, alternatives and consequences.
- Human decision requested, recorded response source, attribution and designation.

Bundle related material changes into one decision. The operator can reply directly
to Codex, including through its Linear agent conversation. No additional Jarvis
relay, endorsement, or per-test approval is required. Preserve a human-authored
source; an agent's own message must not be imported as the human decision.
