---
template_version: engineering-document-draft-1
work_item_id: "{{work_item_id}}"
work_revision: "{{work_revision}}"
document_id: "{{document_id}}"
document_version: "{{document_version}}"
repository_id: "{{repository_id}}"
created_at_utc: "{{created_at_or_unknown}}"
visibility: operator_private
status: draft_not_approval
---

> Template only. Values come from canonical content and evidence; unresolved values
> stay explicit. Content/Markdown/template/renderer digests live in a companion
> manifest, avoiding self-referential hashes. A title/status field grants no authority.

# Engineering review — {{title}}

## 1. Problem and purpose

- Problem: {{problem}}
- Why this matters / why now: {{rationale_and_source}}
- Requested by / source provenance: {{request_source}}

## 2. Intended outcome and acceptance criteria

- Expected result: {{expected_behavior}}
- Criteria with stable IDs: {{acceptance_criteria}}
- Explicitly excluded outcomes: {{non_goals}}

## 3. Repository and starting state

- Repository identity: {{repository_id}}
- Mode/context: {{interactive_or_managed_context}}
- Baseline ref and exact commit, or unknown: {{baseline}}
- Starting working-tree evidence / attribution limits: {{starting_state}}
- Registration/admission status: {{registration_status}}

## 4. Scope and constraints

- Allowed relative paths: {{allowed_paths}}
- Denied paths / exclusions: {{denied_paths}}
- Instruction/configuration constraints: {{constraints}}
- Work revision / previous revision: {{revision_relationship}}

## 5. Proposed approach and alternatives

- Proposed steps (plan, not observed result): {{approach}}
- Alternatives and tradeoffs: {{alternatives}}
- Dependencies: {{dependencies}}

## 6. Validation and its limits

- Criterion-to-check mapping: {{validation_mapping}}
- Exact admitted recipe/argv where applicable: {{recipe}}
- Time limit and execution identity: {{validation_limits}}
- What the checks do not establish: {{validation_limits_of_inference}}

## 7. Execution limits and requested authority

- Context: {{interactive_recording_or_managed_execution}}
- Protected capture operation ID (not its own final digest): {{capture_operation_id}}
- Profile/model/config references from protected capture: {{protected_session_refs}}
- Worker time/attempt limits: {{worker_limits}}
- Spending controls and unenforced limits: {{spending_controls}}
- Requested action: {{exact_action_or_recording_only}}
- Separate approvals still required: {{merge_deployment_and_further_paid_runs}}

## 8. Risks, assumptions and open decisions

- Risks: {{risks}}
- Assumptions / evidence: {{assumptions}}
- Questions requiring human input: {{open_decisions}}
- Unknowns: {{unknowns}}

## 9. Evidence and provenance

{{claim_or_field_to_source_reference_table}}

## 10. Review disposition

- Current state: pending human review
- Decision receipt: not yet recorded
- Exact document/capture digests: supplied by the protected companion manifest/view
- Scope changes require a new revision and applicable approval; editing this copy
  does not update the approved record.
