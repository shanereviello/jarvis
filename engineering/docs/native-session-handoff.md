# Native task-instruction handoff correction

The MK1 documentation worker explicitly deleted temporary AGENTS.md/RRAS_TASK.md files. Native completion succeeded, but the post-run restoration guard correctly refused acceptance. The recovered documents later passed structural checks and still needed human-directed completion. These are two separate issues: brittle instruction transport and insufficient semantic acceptance evidence.

## Smallest supported correction

Keep Hermes dispatch, native worktrees and worker lifecycle; keep the pinned Codex App Server transport and sandbox. Put the entire bounded task objective, exact paths, validation argv and explicit native completion command into the fresh private Codex home's native `developer_instructions` setting. Do not change vendor code, inject repository files, or rely on Hermes's capped task-body rendering for the full objective. Preserve normal repository instructions. Approved root job/request custody, worker scope, process-stop verification and publication controls are unchanged.

The setting is documented by [OpenAI's configuration reference](https://developers.openai.com/codex/config-reference). The unchanged pinned Hermes session starts Codex using the private CODEX_HOME. Model-free native config/read verifies the complete instruction string, including a >8KB Unicode objective, along with existing sandbox/approval/network/app/MCP policy checks. This demonstrates configuration compatibility, not model obedience or semantic completion. One separately approved paid test remains necessary after host acceptance and reviewed installation.

No stronger theoretical custom containment was added. Same-UID worker copies are not immutable authority: the approved root job remains authoritative. The native sandbox bounds tool writes; after verified stop the controller also rejects changed private session config and out-of-scope repository edits. No in-memory expected copy is restored over worker evidence. Base configs already defining developer_instructions are refused rather than silently merged. Existing failed records and installed releases are not upgraded or reclassified.

## Regressions and acceptance

Unit tests cover unchanged repository instructions, absent-control deletion pattern, tracked-control deletion/alteration refusal, long Unicode objectives, retained config tampering, pre-existing instruction refusal and sanitized errors. Fake-worker acceptance covers success, validation failure, outside scope, crash, worker timeout, validation timeout, absent-control deletion, tracked-control deletion and private-config alteration. Unknown stop prevents validation/export; fixture-only cleanup signals exact owned child identities and does not implement production cancellation.

Evidence now separates lifecycle stage, fixed diagnostic code, eligibility for validation, mechanical validation outcome and pending human deliverable review. Source scope is rechecked after validation. The review summary explicitly requires comparing the task's requested deliverables with the diff and factual evidence. This does not claim an automated semantic acceptance engine.

Deployment order: review source PR; run disposable credential-free UID996/systemd acceptance from a new root-owned review directory; merge only with human approval; stage a new immutable operator release through the existing reviewed release procedure; capture a fresh approved task against the new runner hashes; request one paid end-to-end task separately. Old approvals/reviews must not be reused to authorize changed source. No in-place installed release or unit edits, credential provisioning, migrations, timer activation or automatic retry.

## Source validation checkpoint

The source suite passed 206 tests with two existing dependency/deprecation warnings. The final supported acceptance entrypoint passed nine native no-turn configuration checks and nine fake-worker cases under the operator UID, with zero inference requests and no real credentials. These process checks do not establish installed UID996/systemd acceptance. That remains the next administrator step; no installed production release has changed.
