# Workflow package and upgrade contract

This source prepares an inactive candidate and a reviewable upgrade plan. It does
not implement an upgrade installer, switch services or grant installation approval.
The live foundation remains `workflow-421ce120c6da` until a separate approved cutover.
The old first-install staging/activation commands are not upgrade commands.

## Complete payload

`prepare_workflow_release.py` includes the full control/history, finish, native
observation, independent-validation, publication and draft-PR runtime module set.
A static audit rejects omitted literal sibling dependencies using the supported
`local()`/`with_name()` conventions before creating a candidate. Dynamic dispatch
still needs code review; this audit is not a Python sandbox or general dependency
resolver. All payload bytes come from the selected exact current Git commit.
Uncommitted local edits never enter the candidate.

The builder retains the existing locked offline Python dependencies; no pip,
network, model or runtime-version change occurs. Tests import every packaged
module plus jsonschema using isolated Python without builder site-packages.

The package also contains:

- `entrypoints/draft-pr.py`: named-operator CLI wrapper using the protected vendor
  directory and bridge. This is not installed as a worker tool or Hermes MCP.
- `entrypoints/draft-pr-frontend.js`: one trusted async function expression embedding
  both the reviewed frontend bridge and concrete operator tool binding. Call it
  with `{tools, release, packagePath, workspace}` in the operator's connected Codex
  tool context. The embedded bridge cannot be overridden through those options.

Load frontend code only from the installed root-owned immutable release and check
its bytes against the protected release manifest before evaluation. Handoff files,
worker output and arbitrary repository JavaScript are not frontend bootstrap code.
The current source entrypoint has not been installed or accepted against a real
managed remote publication.

## Concrete frontend binding

The binding selects literal existing `exec_command`, `write_stdin`, GitHub fetch/
create and task-attachment tools. It invokes the protected installed CLI with the
existing native Python interpreter, fixed package/workspace arguments and exact
shell quoting. It resumes the same process when a tool returns a session ID;
nonzero exit, malformed/oversized JSON, protocol mismatch or a lost response never
causes an action to be rerun. The helper emits `operator_binding_protocol=1`, so an
older helper cannot silently substitute for the reviewed protocol.

Only `prepare`, `arm`, `complete` and `unknown` CLI actions and GitHub fetch/create
operations are exposed. Connector credentials stay in the operator frontend;
none enter a shell command, candidate, worker or new server daemon. Unknown create
outcomes retain existing fences. Valid created URLs are attached to the task;
attachment errors remain visible without another creation. Human merge/deployment
and paid-task authorization keep their separate decisions.

Source acceptance uses fake tools in the actual frontend JavaScript runtime,
including composed package entrypoint checks. A separate Python shell parser
verified hostile fixture paths/JSON retain quotes, dollar signs, backticks and
newlines literally. No managed GitHub PR was created by those tests.

## Upgrade plan

Supply all four explicit builder options to prepare an upgrade candidate:
`--upgrade-from`, `--operator-config-sha256`, `--hermes-config-sha256` and
`--hermes-compose-sha256`. These must describe the actual protected installed
state captured for review, not remembered defaults or fixture hashes. The builder
validates their shape; the eventual root installer must independently reread and
compare current protected bytes before mutation. No private configuration content
is copied into Git or the upgrade plan.

Upgrade candidates have manifest schema2/kind `workflow_upgrade_candidate` and
plan scope `inactive_upgrade_candidate_only`. The schema1 first-install stager
rejects them before contacting the host. The plan explicitly reports
`installer_implemented=false` and `activation_authorized=false`.

The plan preserves existing operator configuration bytes, journal, history,
approval/fence/job/task state, session profile and credential selection. The bundled
reference registration is not applied to the live configuration. It expects the
existing history MCP entry and replaces only the workflow code mount's source,
keeping the other entries/mounts. The three existing command wrappers must switch
to the new release with protected rollback copies; the frontend is an absolute
release entrypoint, not a newly provisioned server credential or background agent.
Preserving old approvals is evidence retention, not a promise that changed code
will still satisfy their captured hashes.

## Remaining installation work

Build a dedicated upgrade preflight/stager/activation/recovery path that verifies
current-state hashes and source approval, drains the native gateway, confirms the
global task slot/UID996 are idle, preserves private rollback evidence and atomically
switches the intended code references. It must preserve the existing journal and
operator configuration and verify the history MCP after cutover. Interrupted
changes require evidence-based recovery, not automatic retries or adoption.

Independent validator host boundaries already passed fourteen offline cases using
PR30's exact source, with no API calls or production config/journal changes. That
acceptance does not install this expanded package or prove the new frontend's
real authenticated managed remote path. The package/upgrade must receive its own
appropriate acceptance and separate installation decision. A paid task and remote
publication acceptance still require their own bounded scope.
