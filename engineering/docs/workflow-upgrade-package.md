# Workflow package and upgrade contract

This source prepares an inactive candidate and a reviewable upgrade plan. A
dedicated inactive stager and read-only evidence inspector are implemented below;
service activation/rollback and installation approval remain separate.
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

The inactive preflight/stager and evidence inspector are implemented below.
Build the separate activation/rollback path that rechecks protected evidence,
drains the native gateway, confirms the
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


## Dedicated inactive staging and inspection

`stage_workflow_upgrade.py stage --candidate PATH --manifest-sha256 SHA256` is an
administrator-only deployment tool, not a worker command or an automatic service.
Its reviewed bootstrap must use approved source and the exact reviewed candidate
manifest. It accepts schema2 upgrade candidates only, checks committed-source
ancestry on canonical main, bounds and verifies every payload/plan digest, and
rejects existing release/journal roots instead of adopting or overwriting them.

Before creating upgrade roots it checks the actual current configuration/profile
hashes, expected old command-wrapper bytes, existing history MCP entry, pinned
Hermes image/running identity and all seven mounts. It requires the task unit and
UID996 to be idle and refuses an existing drain marker. It verifies installed
state-directory roles, including the existing root:root0755 job parent; individual
coding jobs retain their separate root/worker access rules.

Private rollback copies of operator/Hermes configuration, compose, the container
inspect descriptor, original file ownership/modes/inodes and old/new wrapper bytes
are saved beneath
`/var/lib/rras-workflow-upgrades/<release-id>` (root0700, files0600). These can
contain private settings and never belong in Git, public output or projections.
The stage copies only public code/reference registration/vendor bytes to the new
root-owned release and prepares a two-mount compose overlay. It does not replace
live wrappers, edit configuration/compose, initialize/reset SQLite/history,
request drain or create/start/stop/rename containers. Provider credential files
are not opened. The existing image's YAML parser is used only to verify the
already configured history entry, without dumping configuration.

A before/after fingerprint checks configuration, wrappers, journal bytes, history
index and container identity/start/restart state. A concurrent journal/projection
change defers the upgrade rather than freezing or overwriting that data. Journal
hashing is bounded to 64 MiB; nonempty SQLite sidecars also defer staging. The
stager never opens SQLite or removes a sidecar.

`inspect --journal /var/lib/rras-workflow-upgrades/<release-id>` verifies private
rollback files, plan/manifest, staged payload and current preconditions without
writing or retrying. Completed unchanged stages report `staged_inactive_verified`;
compatible external fingerprint changes report `external_state_changed`; unsafe
changed preconditions refuse. Interrupted copying/postchecks leave an explicit
started receipt and private diagnostic with no completion receipt. Inspection
reports `incomplete_stage_preserved`, without adopting, cleaning or completing it.
If even the initial receipt is absent, it reports `unidentified_stage_preserved`.
Neither case authorizes adoption. There is no recovery command that mutates
production in this slice.

Tests use real disposable files, actual candidate hashes and the real package
builder, with explicit fake administrator/ownership/Docker/slot adapters. They
cover preservation, precondition and tamper refusal, partial-write evidence,
concurrent journal changes, read-only inspection and first-install separation.
This is source acceptance, not root staging against the actual private installation.
The full installer flag remains false until activation/rollback is implemented.
