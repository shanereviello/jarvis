# Repository admission preparation

This is the first part of roadmap step2. `repository_admission.py` prepares a
content-addressed candidate from an operator-selected repository registration and
work item. It does not enroll the repository, authenticate a claimed actor, approve
execution, install files, invoke a recipe, contact a model or launch a worker.
Existing installed preparation tools and historical robot policies are unchanged.

## Source interface

Use the development interpreter with `engineering/requirements-contracts.txt`
installed. These are interface examples; replace every placeholder deliberately.
No generated per-repository launcher is required.

```sh
python engineering/tools/rras_native/repository_admission.py prepare \
  --registration /absolute/operator-selected-registration.json \
  --work-item /absolute/operator-selected-work.json \
  --hermes-project registered_project_name \
  --state /absolute/private-candidate-directory

python engineering/tools/rras_native/repository_admission.py inspect \
  --state /absolute/private-candidate-directory \
  --candidate-id EXACT_SHA256_FROM_PREPARE
```

The registration and work item follow the [shared contracts](workflow-record-contracts.md).
The work must bind the exact registration digest, select approval-driven mode, an
admitted named baseline with exact commit, exact requested file names and a named
validation recipe. The current executor supports SHA-1 repositories; SHA-256 Git
repositories are explicitly refused until its baseline handling is extended.
Interactive imports and delegated execution are separate later adapters.

Preparation checks a clean canonical Git root, object format and selected ref.
Requested files must fall under allowed roots without touching denied roots,
reserved instruction files or `.git`/`.aws`/`.codex` components. Directory grants,
symlink traversal and submodules are refused, both in the current checkout and the
selected baseline. A new file under a safe directory may be proposed. Validation
argv comes exclusively from the selected registration, and still runs as the
engineering worker under the existing executor contract. Root must never execute
an arbitrary registration recipe. Config selection by itself is not trusted admission.

The private candidate contains original records plus deterministic legacy request,
preparation-policy and registry representations. There is no active registry change
or legacy proposal receipt. A digest changes with scope, objective, registration,
recipe, baseline or Hermes project. Repeating identical preparation is idempotent;
a conflicting existing file is preserved and refused. `inspect` verifies the digest,
recompiles the translation and repeats baseline inspection. It returns bounded IDs,
hashes and baseline rather than the private objective or argv. Output is an operator
view, not an implemented Jarvis read-permission boundary. Files remain private to
the preparing OS user. Durable stream storage/locking and atomic recovery after
an interrupted candidate write belong to step3; an incomplete file is refused.

## Bounded Jarvis starting candidate

`engineering/config/jarvis-registration.candidate.json` records a proposed
`/srv/git/jarvis` admission restricted to `engineering/docs` and main. It is a
source-reviewed candidate, not a live registration. Its provenance records the
accepted roadmap as human-reported scope; it is not an observed enrollment receipt.
The named `documentation-whitespace` recipe is only `git diff --check`: a whitespace
smoke check, not correctness or complete documentation validation. A broader code
scope or stronger recipe requires a newly reviewed registration/work snapshot.

The existing `coding-preparation-policy.json` remains the historical robot-specific
installed interface. Do not overwrite it with a candidate or resume old robot tasks.
Other ordinary SHA-1 repositories use their own explicit registration and named
validation configuration through these same commands; no Jarvis/robot ID is embedded
in the translator. Specialized repositories may require additional validation work.

## Remaining trusted integration

Before a candidate can launch, an operator-owned admission configuration must be
captured at the root boundary and its exact registration/work/baseline and project
bindings carried into review, approval and launch. Recheck freshness at launch;
changing a live registration or named baseline must invalidate prior approval.
Continue to use exclusive one-use approval and the existing global systemd slot.
Schema/digest validity does not establish source authenticity or execution authority.
Do not copy candidate fields into root execution paths as an installation shortcut.

Next add consistent trusted capture/approve/launch/evidence commands around the
existing components, then durable journal/status/history/outbox and isolated host
acceptance before deploying changed privileged code. No new paid task is necessary.
