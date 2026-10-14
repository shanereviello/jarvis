# Host-native engineering source candidate — 2026-10-05

Implements the credential-free packaging slice of [the host-worker assessment](rras-native-host-worker-assessment.md). No accounts, installed releases, units, credentials or activation were changed. The existing worktree branch and baseline remain unchanged; all earlier work is preserved.

## Reviewable result

Bundle: `/tmp/rras-native-host-review-20261005-02`.
Manifest SHA-256: `c31c023f01ec11a38cf4e521e48fa9928ba569b4d5bc027537377b533d9a8aeb`.
Builder: `tools/rras_native/prepare_host.py`.

The bundle contains the exact committed Hermes source archive, dependency lock, reviewed Codex software/resources, separate profile/Codex settings, RRAS activity utility, host activation plan and a **help-only** systemd check candidate. There is no Docker build/run path, task execution service, timer, API key, copied personal configuration or relocatable installed venv. The help unit has no Install section and does not dispatch tasks. Root-owned release installation and the worker-owned 0700 state tree remain proposals under `/opt/rras-engineering` and `/var/lib/rras-engineering`.

Verified public upstream commit `76952ba54f5dd83f4f5bd0246059171b4b9d1c4a` declares Hermes 0.20.4. The committed Codex transport matches the earlier inspected image hash. Packaging uses `git archive` of that commit, not dirty checkout contents or live container state. This verifies transport correspondence, not byte-for-byte correspondence of every installed image file. The dependency lock has 253 packages across optional/platform resolutions; the actual core installation selected 61 packages.

Pins:

- `pyproject.toml`: `1f928b1560b0669291b3f7d562aa78c99ac4f927375939ca97fd3c3e7494cb91`
- `uv.lock`: `8fd868b9da8b6bc2f4aa94a845e210eccdd5e31be7a0b404f0a8527ced0fddec`
- Python 3.13.16; Hermes requires >=3.11,<3.14.
- uv 0.12.23, observed binary SHA-256 `abdc39eab8b4ad341dca91f3823a23a343fae94bdb22ebdd9e91694415206f2f`; fetched as an exact public PyPI package into `/tmp`, not installed system-wide. This observed hash is not an independently authenticated publisher checksum. Client is not included in the release bundle.
- Codex 0.159.0 main binary pin remains as recorded in [step three](rras-native-step3-runtime-preparation.md); software resources only, no personal identity.

## Actual validation

A cleared-environment `uv sync --frozen --no-dev` built the exact source's core environment under `/tmp/rras-native-host-build-20261005-01/source/.venv` using Python 3.13.16, disabled Python downloads and private cache. No dependency lock regeneration or extras were requested. The exact setuptools 83.0.0 build backend is declared upstream. Temporary build source is editable; it is **not** the deployment trust boundary. At deployment, build a non-editable environment at its final reviewed release path; do not copy this temporary venv as if it were relocatable.

Actual credential-free CLI checks passed: `hermes kanban --help`, `hermes kanban create --help`, `hermes kanban dispatch --help`. Task creation exposes the RRAS utility's expected flags. No task or dispatch was executed. [Machine-readable evidence](rras-native-host-candidate-evidence.json) records the dependency inventory hash and runtime scope. Build logs and package inventory remain in the private build directory. gpt-5.4 remains a candidate setting, not verified entitlement or a model call.

Source tests: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_rras_native*.py' -v`: **21 passed**. New tests prove wrong-revision/pin rejection before preparation, packaging committed rather than dirty source, inventory hashing, absent-only destination handling and nonactivating help service semantics. Runtime packaging is stubbed in the host unit test; real pinned executable packaging and the actual dependency/CLI build were validated separately.

## Native lifecycle decision that remains

The pinned source's default continuous dispatcher lives inside the gateway. `hermes kanban daemon` is deprecated and requires a hidden force escape hatch; do not use it as our architecture. The supported CLI has a one-pass `hermes kanban dispatch --max 1 --json`. The candidate sets native concurrency/spawn caps to one and keeps gateway dispatch disabled for this separate home.

One pass is a promising manual-first entry point, but a systemd oneshot around it cannot yet be assumed to preserve spawned workers after the parent exits: KillMode=control-group may terminate them. Therefore this bundle intentionally ships only a help check, not an invented task-runner unit. Next model-free acceptance must establish native worker parent/child lifetime and choose a supported foreground/manual or native gateway dispatcher arrangement. If a gateway is necessary, verify isolated engineering-only operation without messaging integrations; do not duplicate the production gateway's identities or board.

The proposed `rras-engineering` assignee/profile must also be registered using native profile semantics. A profile config copied into the base home alone does not prove that Kanban can resolve an assignee with that name. Actual native profile selection, effective toolsets, CODEX_HOME inheritance, approvals and board/workspace permissions remain acceptance requirements.

## Next bounded slice

Prepare a disposable native dispatcher fixture using the built source and an explicitly fake coding child, with zero API access. Exercise native project/worktree admission, profile selection, concurrency caps, child lifetime and evidence export; avoid hand-written lifecycle substitutes. Then prepare the administrator's dedicated-UID acceptance and reviewed installation/rollback sequence. Actual account provisioning and service installation remain pending. The host-native approach must pass real sandbox tests under the dedicated UID before credentials/canary; earlier UID 1000 tests do not substitute for those gates.

Verify the present bundle without execution:

```bash
python3 -B - <<'PY'
import hashlib, json
from pathlib import Path
review = Path('/tmp/rras-native-host-review-20261005-02')
manifest = review / 'manifest.json'
assert hashlib.sha256(manifest.read_bytes()).hexdigest() == 'c31c023f01ec11a38cf4e521e48fa9928ba569b4d5bc027537377b533d9a8aeb'
files = json.loads(manifest.read_text())['files']
assert {str(p.relative_to(review)) for p in review.rglob('*') if p.is_file() and p != manifest} == set(files)
for name, expected in files.items():
    assert hashlib.sha256((review / name).read_bytes()).hexdigest() == expected, name
print('Host review candidate verified; nothing installed')
PY
```

No administrator action is required at this checkpoint. Keep the existing gateway and Phase 5B services, records, fences and disabled reconciliation timer unchanged. Portal budget controls remain the selected interim policy.

Next checkpoint: [native dispatcher acceptance](rras-native-dispatcher-acceptance.md) records the successful 11-case fake-child integration and superseding 03 review bundle. Cgroup, dedicated-UID and real-session gates remain unfinished.
