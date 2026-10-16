# RRAS engineering agent instructions

Work on a dedicated `codex/` task/review branch. Preserve existing work and keep canonical/default branches human-controlled.

The operator has granted standing authorization to commit and push admitted source changes to the task's own review branch in the admitted Jarvis/robot_ws repositories, and to create/update draft PRs. Do not ask for permission for each ordinary branch push. Report validation results and material limits. Never force-push, delete branches, push tags/default branches or overwrite another task's branch under this permission.

Merge and deployment require a separate explicit human decision. Execution of paid coding tasks retains its separate approval contract; branch-push permission does not authorize model spending or new task execution. Do not bypass external tool/platform approval review.

Follow the admitted task contract. Coding workers using `leave_uncommitted` must leave edits for the trusted post-validation publisher; standing branch permission does not override that worker contract or give the sandbox GitHub credentials. The publication adapter must enforce repository/assigned-branch and evidence policy. Direct operator-facing development agents may publish their reviewed source branch using the session's authorized Git connection.

Keep secrets, full local configurations, private runtime records and raw credential-bearing logs out of Git. Publish source/tests/docs and appropriate validation summaries, not private operational artifacts. Do not change repository protection or credential permissions as a side effect of publication.

Use focused tests for changed behavior. Current source navigation is in `engineering/docs/README.md`; standing publication policy is in `engineering/docs/publication-policy.md` and `engineering/config/publication-policy.json`. No source merge by itself authorizes installation, service activation, database migrations or legacy-directory deletion.
