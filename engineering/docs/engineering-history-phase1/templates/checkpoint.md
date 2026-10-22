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

# Engineering checkpoint / handoff — {{title}}

## 1. Context and objective

- Work revision / originating review document: {{review_refs}}
- Session / attempt links, or explicitly unavailable: {{context_refs}}
- Checkpoint kind: {{progress_or_pause_or_handoff_or_interruption}}

## 2. Work actually performed

{{completed_actions_with_claim_provenance_and_evidence}}

## 3. Decisions and rationale

{{decision_subject_target_evidence_and_rationale}}

## 4. Current source and evidence state

- Repository / branch / HEAD at capture: {{source_state}}
- Dirty files and attribution uncertainty: {{working_tree_state}}
- Validation performed and results: {{validation_evidence}}
- Commit/PR/deployment facts, separately: {{publication_and_release_state}}

## 5. Incomplete work, uncertainty and blockers

{{unfinished_work_failures_unknowns_and_open_questions}}

## 6. Scope / authority changes

- Changes proposed versus accepted: {{scope_changes}}
- Applicable approval receipts and their limits: {{approval_refs}}
- No new paid run, merge or deployment is authorized by this checkpoint.

## 7. Next action / receiving context

- Next concrete step: {{next_action}}
- Required input/approval: {{needed_input}}
- Handoff relationships: {{continues_or_depends_on}}
- Capture coverage: {{explicit_or_hook_assisted_or_retrospective_and_gaps}}
- Delivery receipt state: {{recorded_or_pending}}
