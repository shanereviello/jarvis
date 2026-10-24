# Standard managed review document: passive binding constructor

`engineering/tools/rras_history/managed_review.py` produces the existing ten-section
engineering review template from an exact supplied managed capture, an explicit
engineering work revision and a bounded curated proposal. It returns a passive
`document.render` request, deterministic Markdown, the ordinary immutable document
manifest and an external companion binding. No file, database, network, root-state
or approval write occurs. This source constructor is not installed in production.

## Machine core and narrative

The caller supplies a capture and its exact review digest. The constructor checks
its v1 shape, request contract, no-authority flags and referenced digests. It checks
repository, ordered allowed paths and exact baseline against the separately curated
engineering revision. Operational task ID and engineering work ID remain explicitly
bound in the companion; matching identities are not inferred from task-name syntax.

Machine-owned fields come from that capture or the validated engineering revision:
objective, acceptance criteria, baseline, scope, recipe, timeouts, commit policy and
profile/config/runner hashes. A complete canonical JSON copy of the capture appears
in the evidence section so policy, admission and branch references cannot silently
be omitted from the review. Its absolute paths and metadata are private. The
constructor opens none of the referenced repositories/configs and reads no secret
bytes. It does not recheck live admission or claim the baseline is still clean.

The exact curated field set is approach, alternatives, dependencies,
validation_mapping, risks, assumptions, open_decisions, unknowns, non_goals and
denied_paths. Each needs explicit text (including `unknown` where appropriate).
These are labeled proposals, not observations; callers cannot inject machine-field
keys. Untrusted strings inside generated core/proposal values use JSON code fences
longer than any contained backtick run. This preserves the fixed document structure;
it does not make Markdown safe for a future browser. Browser sanitization is a
separate deployment requirement.

## Binding and limits

The companion `engineering-managed-review-binding.v1` contains the capture review
ID, operational task ID, engineering work ID/revision hash, document-request hash,
manifest hash, Markdown hash and binding-renderer hash. The document manifest in
turn pins content, template and document renderer. No digest is embedded inside
its own bytes. Any changed capture, work revision, curated content, document bytes,
template or renderer needs a newly reviewed package. `verify` regenerates and
compares the whole package, not just a caller-provided Markdown hash.

Use the source API with reviewed dependency bytes:

```python
package = managed_review.build(capture, review_id, work_request, narrative, document_id)
verification = managed_review.verify(package, capture, review_id, work_request, narrative)
```

Narrative values are at most 8192 UTF-8 bytes; existing intake/document bounds apply
as well and can reject a large capture or combined content. The package is private
and its document remains `draft_not_approval`. Source attribution is imported.
Unknown occurrence time remains null. No session ID, observed result, spending
ceiling, authenticated human decision or execution identity is fabricated.

## Authority and next rollout

A caller can forge a capture and recompute a digest. This constructor validates
consistency, not protected custody. Only a separately reviewed trusted adapter may
supply a capture read through existing protected approval state. Even a perfectly
consistent package grants no authority. The companion explicitly says
`approval_protocol=existing_v1_unchanged` and `authority_granted=false`.

Existing captures and one-use approvals keep their current semantics. This change
does not make the existing approval/launch adapter require the companion. Next work
must add protected package custody and an explicitly versioned approval envelope
binding capture, manifest and Markdown, test stale/cross-package/replay refusal,
then rehearse host installation. An ordinary stored history document cannot become
that protected approval. No source merge authorizes activation or a paid run.

Source tests cover deterministic rendering, exact capture/core/work association,
package/narrative/template tampering, fence injection, refused pre-authorized input
and immutable passive storage. These tests do not establish root custody or a
production document-bound approval. Automatic export triggers, curated Jarvis
publication and GUI/web controls remain later work.
