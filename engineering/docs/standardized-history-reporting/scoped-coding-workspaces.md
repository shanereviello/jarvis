# Per-issue Codex workspaces — source candidate

The installed v1 runtime has one fixed `cwd` for every mapped issue and its
execution policy remains disabled. The proposed v2 policy binds every admitted
issue UUID to a distinct, non-overlapping canonical workspace. Dispatch and
thread resume use the installed issue binding, never a path selected by the
Linear message. Runtime session metadata records the actual selected workspace.
The existing single-active-or-uncertain-executor rule remains conservative
across the entire runtime.

This is a source candidate, not activated service configuration. The explicit
journal migration requires the runtime to be stopped and exclusively locked,
refuses active or uncertain turns and changed organization, app, executable or
work pins, and binds its plan to fingerprints of the existing journal rows and
new policy. It preserves the old sessions, turns and events. Existing sessions
are marked legacy: an exact already-recorded dispatch can still be replayed, but
a new turn must use an explicitly linked new session rather than pretending
that the old thread has moved to a different checkout. A failed migration plan
or policy mismatch refuses startup; no prior journal is reset.

Before production activation, all of the following remain necessary:

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
