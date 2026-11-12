# Per-issue Codex workspaces — scoped deployment

The installed v2 runtime authorizes execution for eight mapped issues. Its policy binds every admitted
issue UUID to a distinct, non-overlapping canonical workspace and a distinct
issue-specific native socket. Dispatch and thread resume use the installed
issue binding, never a path selected by the Linear message. Each candidate
socket activates an App Server whose systemd working directory and only explicit
repository writable path are that issue's checkout. Runtime session metadata
records the actual selected workspace.
The existing single-active-or-uncertain-executor rule remains conservative
across the entire runtime.

The explicit journal migration requires the runtime to be stopped and exclusively locked,
refuses active or uncertain turns and changed organization, app, executable or
work pins, and binds its plan to fingerprints of the existing journal rows and
new policy. It preserves the old sessions, turns and events. Existing sessions
are marked legacy: an exact already-recorded dispatch can still be replayed, but
a new turn must use an explicitly linked new session rather than pretending
that the old thread has moved to a different checkout. A failed migration plan
or policy mismatch refuses startup; no prior journal is reset.

The v2 migration can retain `execution_authorized=false` while the runtime and
issue-specific sockets are checked. A separate, plan-bound and journaled v2
authority transition changes only the execution flag and its reference; it
refuses changed workspace/work pins and unresolved turns. This permits checking
the deployment without accidentally starting paid coding and supports a later
explicit disable transition. The disabled configuration and journal cutover
passed host readiness and unauthenticated-denial checks; the operator then
authorized execution for the eight mapped issues. Live paid execution and
acceptance using the new issue-specific runtime remain outstanding.

The scoped deployment depends on the following checks and decisions:

- Prepare a separate native-owned checkout and task branch for each issue from a
  verified baseline, without exposing operator credentials or the canonical
  checkout to writes. Preserve the existing retained task checkout and diff.
- Verify the installed systemd writable-path and actual Codex sandbox behavior:
  an issue's turn can edit its own checkout and cannot edit another issue's
  checkout or the main checkout. Distinct paths in configuration alone do not
  establish process-level isolation; all native sessions currently share one OS
  account and App Server boundary.
- Verify old and new policy bytes, the live runtime journal and the transport's
  pending/uncertain state. Prepare a recovery plan and a consistent backup as
  required before migration. Never replay an uncertain engineering turn to fix
  policy or reporting.
- Carry the v2 contract through packaging, n8n admission, history reporting,
  native sandbox and service tests. Test distinct issue sessions, wrong paths,
  locked journals, changed migration plans, restart and legacy-session refusal.
- Separately authorize the exact production configuration and any paid live
  test. Preparation does not turn execution on. Operator/user authority, issue
  delegation, architecture approval, merge and deployment remain distinct.

A fixture can establish routing and journal semantics; it cannot prove the
installed OS sandbox, live model behavior, or the cost of a task.

A disposable, model-free `:workspace` sandbox check run as the operator account
allowed a file write in the selected fixture directory and returned a read-only
filesystem error for a sibling directory. This does not test the native service
identity, its systemd restrictions, App Server's effective sandbox profile, or
all possible paths; those checks remain required before activation.

An additional local App Server probe exposed why separate directories alone
were insufficient: with a shared server started in another directory, granting
the selected checkout in `writableRoots` also left the server's startup
directory writable. Starting a distinct fixture App Server in the selected
checkout allowed its own write and denied a sibling write, with no model turn.
These operator-account tests do not establish production native-service
isolation. At that stage the inactive per-issue unit candidate passed
`systemd-analyze verify` before installation.

The operator subsequently ran the disposable two-issue App Server fixture as
`rras-codex-native` under systemd restrictions and with networking disabled.
Both directions passed: each actual App Server thread selected its own fixture
directory, could write there, and was denied a write to the other fixture
directory. No model or production configuration was involved. The operator
also staged eight separate clean native-owned, remote-free task checkouts at
commit `65b6ceef7ff28222b6e96112c7f7f43a8c2919ba`. The canonical checkout and
the earlier uncommitted REV-50 acceptance checkout were preserved. The
v2 runtime and its eight socket units are now active. Paid coding has been
authorized for the mapped issues and still requires live validation.
