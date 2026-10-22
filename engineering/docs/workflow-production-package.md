# Production workflow package and installation gates

Current installation and acceptance status: see [phase closeout](workflow-phase-closeout.md) and the [operator runbook](workflow-operator-runbook.md). The active release is `workflow-b51bcece0851`; finish/native observation, independent validation, managed draft publication and journal reads have been exercised. Descriptions of source slices and their original pending gates below are historical development context, not the current installation status. Closeout publication corrections still await their own release.

## Component design and historical delivery notes

PRs15–20 provide the contracts, control, journal, reader and model-free acceptance.
This slice adds reproducible production packaging, explicit snapshot publication and
an inactive staging/preflight tool. It does not authorize production installation,
create a real task, expose the private journal or restart Hermes.

## Candidate contents and runtime

`prepare_workflow_release.py --source REPO --commit EXACT_HEAD --output ABSENT_DIRECTORY`
reads operational source through `git show` at an exact current commit. Uncommitted
working files cannot enter the payload. It copies the exact offline dependency
versions in `engineering/config/workflow-dependency-lock.json`, requiring the current
pinned Python3.13.16 builder. No pip download, model, service or credential access.
Installer provenance/direct_url and host RECORD files are excluded from public vendor
metadata. Manifest/file hashes and the committed source identify a deterministic
release; fake acceptance workers and probe code are excluded.

The release contains real runner/control modules, schema, the bounded Jarvis
registration, the reader/publisher and existing schema dependencies. It does not
contain private live configuration, session values, journals, provider keys or GitHub
authentication. It refers to the existing root-protected `operator-project-trust-v1`
profile/base Codex configuration by path and digest. Hermes/Codex/native Python pins
remain unchanged. Python invocations use native-10's existing interpreter.

Supported release entrypoints prepend only the protected release's offline vendor
directory. `entrypoints/operator.py` requires a configured journal for capture/review/
approve/launch, closing the earlier compatibility interface for the installed workflow.
`entrypoints/journal.py` provides passive import/status/history/evidence commands;
`entrypoints/publish.py` explicitly publishes sanitized history. No dispatcher, timer,
model-spending authorization or automatic projection refresh is added. Repositories
remain selectable through protected registration/configuration, not launcher edits.

## Planned paths and principals

| Purpose | Planned path | Ownership/access |
| --- | --- | --- |
| Immutable code/schema/vendor | `/opt/rras-engineering/releases/workflow-<payload-id>` | root-owned, readable code, no credentials |
| Bounded Jarvis operator configuration | `/etc/rras-engineering/workflow/jarvis.json` | root-private0600, protected parent |
| Real workflow journal | `/var/lib/rras-workflow/journal` | root-private0700, database0600 |
| Published history | `/var/lib/rras-workflow/history` | root:1000 directory0750, files0440 |
| Private installation/rollback evidence | `/var/lib/rras-workflow-installations/workflow-<payload-id>` | root-private0700/0600 |

Existing jobs, workers, root approval records, native runtime and task evidence retain
their current paths. No old approvals are rewritten or reused after source changes.
The Jarvis registration remains limited to `engineering/docs` on main with a whitespace
smoke recipe; it is not general code correctness validation or broad repository admission.
A larger scope/recipe requires a newly reviewed registration and work item.

The planned private journal starts empty unless a separate explicit historical import
is reviewed. This package does not silently convert chat history, acceptance fixtures
or prior GitHub PRs into observed managed executions. Explicit interactive import
retains its provenance. No paid task is needed to initialize or verify these components.

## Explicit projection generations

`publish_workflow_views.py --store PRIVATE_STORE --directory HISTORY --reader-gid 1000`
requires an existing caller-owned0750 reader-group directory disjoint from the private
store. A private publisher lock serializes cooperating publishers. It reads one
validated in-memory journal snapshot and builds at most256 bounded pages in a private
staging directory. Pages get unique generation names; no previous page is overwritten.
The writer fsyncs page bytes and the directory before atomically replacing `index.json`.

The reader therefore follows either the previous complete index or the new complete
index. Failure before the switch preserves the previous index; unique orphan pages
may remain after failure, and older generations are deliberately retained. No garbage
collection or silent visibility revocation is claimed. The existing strict projection
allowlist strips objectives, free text, raw references, session values/argv, raw artifact
bytes and private artifact metadata. The public directory never contains the database
or publisher lock. Publication grants metadata read access only, not execution rights.

A publisher generation is a coherent source snapshot. Multiple client calls can still
span different generations if the operator publishes between calls; each page reports
its own revision/cursors. There is no background refresh. Run explicit publication
when making new journal facts visible, and use private history for unexported facts.

## Inactive staging/preflight

`stage_workflow_review.py --candidate DIRECTORY --manifest-sha256 EXACT_SHA256` is a
separate administrator operation, not run by the builder or source merge. Before it
runs, the candidate's source commit must be an ancestor of canonical Jarvis main and
the user must review its fixed manifest. Hash mismatches, symlinks, stale pins or
existing per-release staging roots refuse rather than adopting unknown state.

The tool stages only a new protected inactive code release. It verifies pinned profile/
base configuration, expected Hermes image/running state, five existing mount targets
and the exact live configuration digest. Private originals, a candidate YAML with
only the history MCP entry added, the original Compose and container descriptor, and
a two-read-only-mount Compose overlay are stored in the root-private journal. Full
configuration/container environment data must never be copied into Git or user logs.
YAML transformation round-trips through the existing Hermes parser; other configuration
values and MCP entries retain their semantics. No live file, container or mount changes.

It then tests the new publisher against a separate synthetic journal and projection
tree. A real UID1000 child must read the sanitized files while being denied database
and index-write access. Production journal/configuration paths are not created. The
successful result is `inactive_workflow_release_staged` with activation_authorizedfalse.
Preserve all staging/evidence after any error; do not blindly rerun or remove fences.
This preflight is needed for the new publisher even though earlier host checks passed.

## Concrete activation and rollback requirements

Only after inactive preflight succeeds and private candidate/configuration/Compose
hashes are known, prepare the final activation helper and request a separate explicit
installation decision. The approved procedure must:

1. Recheck source/file/configuration/container pins, no new mount/entry conflicts,
   empty managed slot and UID996, protected ancestors and exact permissions.
2. Initialize the new private journal and deliberately empty published generation,
   save immutable installed configuration and make operator entrypoints discoverable.
   Do not create execution approvals, tasks or synthetic records in the real journal.
3. Use native Hermes drain with an exact fresh epoch, refuse an existing drain marker,
   wait for a fresh live gateway with zero active agents and preserve private originals.
4. Apply only `rras-workflow-history` and the two read-only code/history mounts. Keep
   the existing image, five mounts, six MCP entries, private environment and settings.
   A restart/recreation is explicit maintenance, with no image pull/build.
5. Verify real UID1000 MCP2 list/read, exactly the two history tools, expected mounts,
   all previous integrations, private-store denial, unchanged runtime pins and no model
   calls. Confirm the gateway is healthy and active operator configuration requires
   the journal before declaring installation complete.
6. Retain exact private original configuration, Compose/container descriptors and an
   original-container rollback until verification. On failure restore the previous
   configuration/Compose and container behavior; retain new journal/events/artifacts,
   approvals, consumption and task evidence. Never retry a task as rollback.

Source merge or inactive staging is not that decision. A real managed coding task
requires a later exact scope/baseline review and explicit one-use spending approval.
Native finish/custody/publication receipts, production index delivery, GUI/autopilot,
full cancellation/recovery and other [roadmap](workflow-roadmap.md) deferrals remain
separate. Initial production visibility is structured metadata; richer explicitly
shared prose is not silently introduced by packaging.

## Installed October20,2026

Following explicit human installation approval, the staged release
`/opt/rras-engineering/releases/workflow-421ce120c6da` is active. Native Python,
Hermes/Codex/image and session-profile pins remain unchanged. The supported commands
are `/usr/local/sbin/rras-workflow`, `/usr/local/sbin/rras-workflow-journal` and
`/usr/local/sbin/rras-workflow-publish`; each exposes `--help`. The root-private
operator configuration is `/etc/rras-engineering/workflow/jarvis.json` and requires
`/var/lib/rras-workflow/journal`. The bounded Jarvis admission described above remains
in effect. Ordinary interactive Codex work is not restricted to that managed recipe.

Hermes now has the additive `rras-workflow-history` entry and read-only mounts at
`/opt/rras-workflow` and `/opt/rras-workflow-history`. The original five mounts and six
integration entries remain. Installation acceptance verified UID996/1000 private-store
denial, UID1000 projection read/write-denial, kernel read-only flags and write denial
inside Hermes, existing preparation MCP discovery, the two history tools and an
empty-page response. Independent post-installation checks confirmed a live running
gateway, all seven configured integrations and seven expected mounts. No model or
paid task ran; remote providers were not called to exercise every integration.

The real journal and projection begin empty. This deployment neither imports prior
chats/PRs nor automatically refreshes history. Explicit imports retain provenance;
run explicit publication to expose newly recorded facts. Native execution completion
and publication receipts remain the next integration slice, so installation must not
be presented as end-to-end task/release-note automation.

The original container is retained stopped as
`hermes-rollback-workflow-421ce120c6da`. Root-private rollback descriptors, failed
attempt evidence and the exact administrator helper remain under
`/var/lib/rras-workflow-installations/workflow-421ce120c6da`; preserve them pending a
separate retirement decision. The first attempt stopped before drain due to a missing
journal directory; a later attempt rolled back after its MCP2 verifier used the wrong
result-field spelling. Both were corrected and the final activation passed. The
private journal, task evidence, approvals and fences must survive any future rollback.
Do not reuse the one-time installation/recovery runners as routine upgrade commands.
