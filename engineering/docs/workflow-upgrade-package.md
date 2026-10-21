# Workflow package and upgrade contract

This source prepares an inactive candidate and a reviewable upgrade plan. A
dedicated inactive stager and read-only evidence inspector are implemented below;
guarded activation/rollback source is also implemented below. Host acceptance and
installation approval remain separate.
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

Source now implements inactive staging, evidence inspection and guarded activation/
rollback. A protected tools bootstrap is implemented below. An isolated Docker/native lifecycle acceptance runner is implemented below; its
actual host run remains pending. Only after acceptance should current private
metadata be captured, an actual candidate prepared and inactive staging reviewed.
A separate human decision is required for production activation. The plan's full
installer flag deliberately remains false until the protected installation path
and host acceptance are ready.
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
Neither case authorizes adoption or activation.

Tests use real disposable files, actual candidate hashes and the real package
builder, with explicit fake administrator/ownership/Docker/slot adapters. They
cover preservation, precondition and tamper refusal, partial-write evidence,
concurrent journal changes, read-only inspection and first-install separation.
This is source acceptance, not root staging against the actual private installation.
The full installer flag remains false pending protected bootstrap and host acceptance.


## Guarded activation and explicit rollback source

`activate_workflow_upgrade.py` is a separate administrator deployment tool, never
part of the worker payload. A protected bootstrap must copy it and the staging
module from reviewed source into root-owned custody before loading either one.
No such production bootstrap or activation is authorized by a source merge.

`preflight --journal PATH --manifest-sha256 SHA256` rechecks source ancestry, stage
hashes, unchanged live fingerprint, wrapper bytes/metadata, reserved container
names and a fresh running native gateway without changing services. Activation
requires the additional explicit `--approve-activation` flag and a separate human
decision. A global private flock excludes concurrent upgrade/rollback processes;
a one-use activation directory refuses activation retries after any partial run.

Activation records intent before each external change, requests an exclusive
native drain marker, binds its receipt to inode/hash and gateway PID/start time,
and requires a fresh draining/zero-agent acknowledgement plus an idle fixed task
slot. It rechecks that acknowledgement immediately before stopping the gateway.
The exact original container is retained. The replacement uses the same image ID,
configuration, host settings, network aliases and seven runtime mounts, changing
only the read-only workflow source plus upgrade/compose labels. It retains the
existing configuration and compose files; the protected compose overlay is linked
through container labels. It verifies native health and both existing preparation/
history MCP interfaces using the actual MCP `is_error` field. History may already
contain pages. Three wrapper replacements use expected bytes, recorded ownership/
mode/inode receipts and atomic renames; no database or projection is restored.

`rollback --journal PATH --manifest-sha256 SHA256 --approve-rollback` is separately
approved recovery, never automatic. It validates protected original evidence,
container IDs/descriptors/names, wrapper receipts and configuration pins, drains a
running replacement, retains it under a failed name, restores original wrappers
and restarts the original container. Journal/history data added after activation
survives. Damaged candidate code does not prevent loading protected original
rollback evidence. A durable owned drain can be completed after interruption;
foreign/replaced markers, unrecorded containers, external wrapper changes or an
unresolved create with no matching owned candidate stop recovery for inspection.
A lost create response can be reconciled only by reading the exact nonce-labelled
candidate descriptor; it never causes another create request. Containers, private
errors, state receipts and temporary files are retained, with no deletion, pull,
build, model call or credential-file read.

Tests use disposable real files and atomic wrapper replacements with explicit
fake root/Docker/native-gateway boundaries. They exercise complete round trips,
lost mutation responses, partial wrapper writes, later journal preservation,
corrupt new code, marker/identity/configuration/network drift, drain races and
lock exclusion. They do not prove actual Docker descriptor normalization, native
drain behavior or privileged service cutover; the separate host fixture must do
that before production staging/activation is proposed. Operator maintenance must
also keep unrelated root administration idle during cutover; the upgrade lock is
not a lock taken by every possible root command.


## Protected deployment-tools bootstrap

`workflow_upgrade_bootstrap.py` is a standalone stdlib-only bootstrap. The human
operator must review and hash-pin this file before invoking it with sudo; a file
being in a checkout does not make it root-trusted. It does not import either
candidate deployment module, invoke a workflow action, change sudo policy or grant
workers access. Its `verify-only` action needs no privilege and parses candidate
syntax without evaluating it.

A `deployment-tools-manifest.json` contains exactly `schema_version: 1`,
`scope: "workflow-upgrade-tools-only"`, an exact `source_commit` and a `files` map
of SHA256 digests for `stage_workflow_upgrade.py` and
`activate_workflow_upgrade.py`. Copy their bytes from the selected reviewed Git
commit, not from uncommitted working files. Invoke `stage --candidate PATH
--manifest-sha256 SHA256` only through the separately reviewed hash-pinned runner.

Before writing anything, staging verifies the bounded regular candidate files,
manifest digest, source ancestry on canonical main and exact `git show` bytes for
both modules. Git calls use `--no-replace-objects`, explicit canonical
`safe.directory` and disabled hooks. Workflow staging and activation preflight
share that same source-ancestry helper, so root can read the intentionally
user-owned canonical checkout without relaxing global Git settings.

The bootstrap copies only those public tools and receipts to
`/opt/rras-engineering/releases/workflow-upgrade-tools-<manifest-prefix>` with
root-owned 0755 directory and 0444 code/manifest/receipts. It refuses existing
paths. Interrupted copying retains its start receipt and root-private diagnostic;
no automatic completion, adoption, retry or cleanup occurs. `inspect --release
PATH --manifest-sha256 SHA256` verifies the protected files and completion receipt
without rewriting anything. Once staged and inspected, a later reviewed runner
can invoke the protected deployment tool with isolated Python. That invocation
still requires the corresponding separate staging/activation/recovery approval.

Tests use actual disposable Git commits, bounded files, source-byte comparisons
and installation receipts with fake administrator/ownership boundaries. They
verify no candidate evaluation, ancestry/byte tamper refusal, special-file and
size bounds, duplicate-key rejection, partial-copy preservation and inspection.
No root installation or actual host acceptance has happened from these tests.

## Isolated host acceptance runner

The installed pinned gateway source supports running with no messaging platforms;
it remains alive for cron execution. Use a new empty fixture home with no cron,
provider credentials, chat history or tasks and a container network with no
external access. Do not mount production data/configuration, jobs, Docker socket,
credentials or the canonical checkout inside the fixture. Use fixed isolated
container names and synthetic mounts/wrappers, and enforce that the test transport
cannot name the production Hermes container or mutate a non-fixture resource.

Acceptance must exercise actual Docker create/inspect normalization, image ID
preservation, read-only workflow/history mounts, native running-to-draining fresh
idle acknowledgement and process identity, MCP discovery with nonempty synthetic
history, retained-container rollback and preservation of later synthetic journal
writes. Source adapter tests do not establish those host facts. Keep failed
fixture evidence, stop only fixture containers, and report the tested boundaries
and any untested production-network behavior explicitly. The production activation
approval and later paid task/managed remote acceptance remain separate.


The source runner is `run_upgrade_host_acceptance.py` with the separate
`upgrade_acceptance_transport.py` allowlist. A reviewed hash-pinned bootstrap must
copy the exact acceptance candidate, locked offline vendor payload and harness
into protected custody before executing it. The runner refuses the fixed fixture
root `/var/lib/rras-workflow-upgrade-acceptance-20261020-attempt02` if it already exists.
It uses the pinned existing image without pulling or rebuilding it.

The fixture maps configuration, wrappers, database, history and seven source
mounts into a new synthetic root. Production paths are never mounted. The original
staging/activation/rollback engine runs unchanged; the adapter translates only
logical container names, network names and aliases into random labelled fixture
resources. Its read and mutation paths validate labels, image, explicit UID1000,
command, exact credential-free environment, capabilities, namespace settings,
read-only root and source mounts before touching the daemon. New containers have
one CPU, 1 GiB memory and 256-process limits. The new bridge is internal and no
ports are published. This does not establish behavior on production `jarvis-net`,
or exclude access to the internal bridge's host address; no credentials, tasks or
real messaging adapters enter the fixture. Docker access remains in the root
host harness and is never mounted into a container.

A real synthetic workflow journal and nonempty projection are created. The runner
starts a native gateway, stages an upgrade, drains it, replaces it, checks actual
MCP discovery/read-only mounts, appends a later SQLite event and publishes history,
then explicitly rolls back. It checks later data survives, wrapper recovery and
activation replay refusal. Success/failure both stop only positively identified
fixture containers and retain containers/network/files/private diagnostics. Stop
failure prevents a successful completion receipt. It never automatically reruns
activation or attempts production recovery.

Source tests exercise the adapter's allowlist and complete harness orchestration
with real package bytes/SQLite/files but fake root/Docker/native boundaries. Only
the separately executed sudo acceptance can establish actual host behavior. Its
success is still not production deployment approval or managed paid-task/remote
publication acceptance.


The first host attempt stopped before fixture startup: Docker omits the false
`ReadOnly` default in inspected writable HostConfig mount entries. The acceptance
adapter now treats an absent flag as false, while protected code/history mounts
still require explicit true. The first stopped container, network and private
fixture evidence remain intact. The reviewed second attempt uses a new root and
manifest; the original one-time runner must not be rerun.


The live Hermes configuration's established access role is UID/GID1000 mode0640.
Upgrade readers accept exactly UID/GID1000 with mode0600 or0640 for that specific
configuration path, retaining its bytes, group and permissions. Other user-owned
inputs, including native drain markers, require UID/GID1000 mode0600. Foreign
groups, group-write/world access and special permission bits refuse. This is a
reader correction, not a chmod/chown operation or an architecture change.
