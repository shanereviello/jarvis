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

# Engineering outcome — {{title}}

## 1. Original problem and accepted scope

{{intent_rationale_review_revision_and_accepted_changes}}

## 2. What actually changed and why

{{behavior_or_document_changes_rationale_and_evidence}}

## 3. Source references

- Repository / baseline / resulting commit: {{source_refs}}
- Changed relative files: {{changed_paths}}
- Review branch and PR: {{review_refs}}
- Exact diff reference and retrieval/verification time: {{diff_evidence}}

## 4. Acceptance criteria and validation

| Criterion | Evidence / check | Result | Provenance | Limitation |
| --- | --- | --- | --- | --- |
| {{criterion}} | {{evidence}} | {{result_or_unknown}} | {{provenance}} | {{limit}} |

## 5. Decisions and separate outcomes

- Worker/session result claim: {{reported_outcome}}
- Independently observed validation: {{observed_checks}}
- Human deliverable acceptance: {{decision_or_pending}}
- Branch/PR publication: {{publication_fact}}
- Merge approval and actual merge: {{distinct_merge_facts}}
- Deployment approval and actual deployment: {{distinct_deployment_facts}}
- Operational/field verification: {{verification_or_unknown}}
- This document's completion status: {{accepted_or_partial_or_failed_or_handoff}}

## 6. Deviations, failures and lessons

{{deviations_unresolved_issues_and_evidence_based_lessons}}

## 7. Follow-up work and dependencies

{{follow_up_ids_scope_and_priorities_without_implied_approval}}

## 8. Record quality and publication

- Coverage / missing evidence: {{coverage_and_unknowns}}
- Occurred-at versus recorded-at limits: {{time_provenance}}
- Supersedes/corrects: {{prior_document_or_none}}
- Human narrative acceptance/publication receipt: {{receipt_or_pending}}
- Authorized audience: {{operator_private_or_reviewed_shared_view}}
