# Recording an architecture decision

This describes the existing scoped history operations and their limits. It is
not an automatic approval service. Codex may discuss a draft directly with the
operator in Linear or an interactive conversation; Jarvis is not required as an
intermediary.

1. Save the candidate architecture through the project history interface, and
   retrieve its exact document ID, version, Markdown SHA-256 and project head.
   Identify the relevant project and any affected work. A Linear document is a
   reading copy; the retained bytes and digest identify the candidate.
2. Present the candidate and material changes to the operator. Preserve the
   actual decision's source reference, text, author attribution and observed
   time. Do not infer approval from a board state, an agent message, a reaction,
   or an edited document. If the source or author cannot be established, ask
   the operator for an attestation; do not label the decision independently
   authenticated.
3. Submit a `decision.observe` reporting request for the retained candidate,
   preserving the source reference and an honest `attribution`. Use a stable
   client event key and retain the exact private request and resulting receipt.
   This records an observation: it grants no authority and does not designate a
   version, even if its state says `approved`.
4. Following the operator's actual agreement, submit a separate
   `architecture.designate` project request using the candidate version and
   digest and the exact current project head. Use the supported project/history
   interface with an authorized writer. A stale head must be reread and reviewed;
   it is not permission to silently choose different document bytes. Retain the
   request and receipt. A lost response is reconciled by replaying the same
   frozen request, not by inventing a second decision.
5. Read the project back and verify its governing version and digest. Update only
   the affected work assignments and their architecture pins through the existing
   explicit project operations, with their own expected heads. A new governing
   version does not silently rewrite historical work or prior evidence. Publish
   links and progress through the appropriate approved interface.

The reporting and project operations are separate durable writes; there is no
atomic cross-stream transaction. If recording succeeds and designation fails,
retain the decision receipt, leave the prior version governing and reconcile the
exact designation request. Do not turn a failed or uncertain write into a claim
that designation succeeded.

A disposable test covers the existing history behavior: an imported synthetic
Linear decision retains its source, exact request replay is idempotent, and the
governing version changes only after a separate explicit designation. This does
not establish human authorship, authorization of a real decision, live Linear
message capture, or end-to-end production acceptance. The actual operator's
message and approved bytes are required for a live test.
