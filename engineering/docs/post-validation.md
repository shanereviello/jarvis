# Independent mechanical validation

Current installation and acceptance status: see [phase closeout](workflow-phase-closeout.md) and the [operator runbook](workflow-operator-runbook.md). The active release is `workflow-b51bcece0851`; finish/native observation, independent validation, managed draft publication and journal reads have been exercised. Descriptions of source slices and their original pending gates below are historical development context, not the current installation status. Closeout publication corrections still await their own release.

## Component design and historical delivery notes

The source workflow now separates the worker's reported checks from an independent
host validation attempt. This source is not installed. Real root/UID996/systemd
acceptance and an updated package/upgrade procedure must pass before deployment.
No paid coding task or production unit is needed for the source tests.

## Candidate and recipe

`post_validation.py` recompiles the captured registration/work item and requires
the exact reviewed request, registered recipe, timeout, repository, task, branch
and baseline. The plan binds the review commit, export and protected finish
receipt digest. A plan alone does not authorize execution or authenticate inputs.

`validation_workspace.py` implements root-only `validation-stage` and
`validation-stage-verify`. Both take `--finish-custody`, `--package` and
`--destination`. Staging authenticates protected finish/handoff custody and bundle
hash, reconstructs from that bundle without network or operator Git configuration,
and rechecks the single baseline parent and exact admitted changed paths.

HEAD remains at the baseline with unstaged proposed contents. New files receive
intent-to-add, including explicitly admitted ignored files. Otherwise the current
`git diff --check` recipe would either inspect a clean review commit or skip new
files. Actual Git tests prove whitespace errors in those additions are detected.
The receipt binds the plan, bundle, handoff, exact regular-file inventory, review
tree and Git index/configuration. Verification compares actual bytes/modes and
additions/deletions, without trusting a stale index. Partial stages are retained;
a fresh destination cannot silently reuse one.

The stage stays root-private, mode700. The fresh inner clone uses readable
directory/file modes so UID996 can inspect its read-only private service mount
even when the root operator used umask077; the outer stage still denies host
access. Git metadata is non-executable, and review executable file modes remain
intact. Symlinks/submodules anywhere in either tree
are currently refused; they are never flattened. The current Jarvis source has
neither. Limits are 16,384 files, 64 MiB per file and 256 MiB total regular content.
Arguments containing `$` or `%` are refused by the service renderer to prevent
systemd expansion; supporting those literals needs a tested invocation wrapper.

## One-use execution and custody

`validation-execute` takes the same three arguments, with `--destination` naming
the existing stage. It verifies the stage and dedicated account, checks the global
slot, then exclusively creates a root-owned fence in the original coding job.
A mirror is retained in finish custody. Duplicate finish captures or alternate
stages cannot rearm the same coding launch. A partial write or interrupted client
preserves the fence; there is no reset/retry command.

The command reuses `rras-coding-task.service`, UID/GID996 and existing resource
bounds. Systemd acquires that fixed unit before exposing the candidate through a
**read-only private service mount** at `/run/rras-validation/repo`. The host stage
is never made worker-accessible or writable. This avoids the interval where a
competing coding process under the same UID could alter staged validation input.
These proposed namespace/ownership properties still require real host acceptance.

The service receives no provider/GitHub credential, uses an empty initial
environment and private networking, hides credential/workflow/job roots, and
protects the filesystem. The fixed Git safe-directory entry and optional-lock
setting allow inspection of the immutable root-owned checkout. The validator's
registered recipe runs as UID996, never root. Private temporary storage is
available; the candidate itself stays read-only. Recipes needing writable source
or build trees require a reviewed scratch-directory contract in a later slice.

The root client captures at most 2 MiB of combined output and waits no longer than
the registered timeout plus 30 seconds. Exceeding a bound kills only that client;
it does not claim the unit or worker stopped. RuntimeMaxSec/KillMode and a separate
fixed-slot/UID idle check govern stop evidence. Uncertain stop, client failure,
truncated output or changed protected input remain uncertain and retain the fence.
A nonzero service attempt fails but does not prove the recipe itself started:
service setup may have failed. Exit zero only establishes an independent check
when complete capture, stopped identity and unchanged exact review tree agree.

Root-only result and output files stay in finish custody. There is no mutable
worker Git inspection after execution: the candidate was immutable in the service
namespace and the protected stage is reverified. The staging filesystem reader
must never be reused for active or previously writable worker directories.

## Recording and publication gate

`validation-record` rechecks protected inputs, global/local fences, result/output
hashes and classification. It repairs prerequisite finish journal facts and adds
an idempotent **observed** validation event linked to the exact review commit.
Recording never executes a recipe. Raw output is not a journal payload or Jarvis
projection; only bounded facts/digests are recorded. The worker's imported terminal
claim remains imported; mechanical validation does not establish task correctness,
human acceptance, merge, deployment or release.

`validation-release` requires success, records the journal event durably, then
writes a small root-protected `independent-validation.json` to the handoff package.
A journal outage blocks that release without authorizing another execution.
Replaying release/recording repairs files/events only.

New managed packages from `publication-prepare` require this proof. The named
operator handoff reader, publisher and draft-PR bridge refuse missing or mismatched
proof before proceeding. Publication receipt capture requires and retains the
same proof; recording verifies its binding. The proof identifies the exact
handoff/commit/baseline/export and private result/plan digests; it grants neither
merge nor deployment. Existing legacy source packages remain explicitly outside
this new managed gate; their imported publication claims are not retroactively
relabelled as independently validated.

## Remaining acceptance and installation

Source tests use real disposable Git/SQLite and harmless bounded subprocesses.
Administrator/ownership, account and systemd boundaries are explicit fake adapters.
They do not demonstrate the actual service namespace, UID isolation, read-only
mount, credential denial or stop behavior on this host.

Next: model-free root/UID996/systemd acceptance of these changed boundaries;
complete the protected frontend binding; update the dependency graph and upgrade
procedure while preserving the current journal/configuration; obtain separate
installation approval. A real paid task and managed remote publication acceptance
still need their own exact scope/authorization. No deployment or API spending
follows from merging this source.
