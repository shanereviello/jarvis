# Native-first engineering architecture

Hermes owns native Kanban tasks, runs, worktrees and worker lifecycle. Codex App
Server owns the coding session and workspace sandbox. RRAS supplies repository/path
admission, one-use human approval, traceability, independent validation, verified
stop, protected evidence export and human publication/merge/deployment boundaries.

The installed workflow is `/opt/rras-engineering/releases/workflow-b51bcece0851`.
Protected per-repository configuration selects the admitted canonical Git baseline,
exact paths, reviewed validation recipe and session profile. Hermes prepares mutable
proposals without execution authority. A root operator captures/reviews/approves an
exact snapshot. Only that one-use approval can start the fixed managed slot under
UID996. Changed baseline/configuration revokes the approval. Worker clones/worktrees
are separate from canonical Git, and workers receive no GitHub credentials.

Stopped-worker finish capture preserves reported claims. A read-only native database
snapshot independently checks stored agreement without authenticating worker behavior.
The isolated post-worker validator reconstructs the exact review tree, checks it
against baseline (including added files), captures observed results and gates the
source-only operator handoff. Mechanical validation is separate from human task
acceptance. The named operator publishes the exact assigned branch and creates a
draft PR through the existing frontend GitHub connection. Merge/deployment require
separate explicit human decisions; no model result grants either authority.

The root-private SQLite journal stores append-only records/artifacts and a durable
pending index outbox. Jarvis sees only explicitly published sanitized history pages
on a read-only mount. Status/history/summary and explicit provenance-preserving
interactive imports exist; ordinary chats are not automatically observed. Local
history survives ledger outages because production ledger indexing remains disabled.
The separate legacy activity ledger remains stopped; no schema upgrade is implied.

The first managed documentation task was accepted and merged as PR38, with explicit
acceptance/merge entries recorded. This establishes that bounded path, not arbitrary
repository recipes, unattended execution, broad model autonomy or robot field safety.
[Phase closeout](workflow-phase-closeout.md) gives evidence levels and remaining gaps;
the [runbook](workflow-operator-runbook.md) is the current operator command reference.

Cancellation/interrupted-launch recovery, ledger delivery, richer engineering-memory
summaries, GUI/autopilot, multiple workers, local hard budgets and centralized backup
remain deferred. API portal spending controls remain the current operator practice.
Two publication integration corrections are source changes awaiting installation;
the live runtime and pinned Hermes/Codex/model versions remain unchanged.
