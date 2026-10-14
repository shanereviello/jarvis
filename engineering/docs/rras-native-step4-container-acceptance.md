# Native container checkpoint — 2026-10-05

Continues [step three](rras-native-step3-runtime-preparation.md) and the approved [native-first architecture](rras-native-first-architecture-review.md). Branch remains `phase5b/guarded-host-orchestration`, HEAD `f0d8a6eaf016153708c3e46a32e204a93bd11a97`; existing changes preserved.

## Demonstrated, without credentials or inference

Two isolated derivative-image builds succeeded using the exact locally installed Hermes configuration image ID, reviewed Codex 0.159.0 software resources, no pulls and network-disabled build commands. Disposable execution used no production mounts or published ports, a read-only root, capped memory/CPU/PIDs, dropped capabilities and no-new-privileges. Board and task-workspace roots are separate; the candidate explicitly supplies `HERMES_KANBAN_WORKSPACES_ROOT` and isolated `CODEX_HOME`.

First run `430178dd83874a9d8f9bfe9e026c7378` failed before probing because the launcher named `/usr/local/bin/python3`; corrected to the image's verified `/usr/bin/python3`.

Second run `15eebfda4a0643e28c8c8705771701d8` verified the actual installed Hermes environment helper, synthetic unrelated-token filtering, native App Server initialization and isolated Codex-home reporting. Both admitted writes failed: `bwrap: No permissions to create a new namespace`. **Container acceptance failed.** Its raw sibling-write denial is inconclusive because the sandbox could not execute admitted commands. A new regression and probe prerequisite prevent that false-positive classification; original evidence is preserved.

Both runs removed exactly owned containers and temporary image tags. The existing gateway remained running and unchanged; reconciliation timer remains disabled. No installed release, service, credentials, runtime records, writer fences, migrations or paid tasks were changed. Build cache was not globally pruned. [Machine-readable evidence](rras-native-step4-container-evidence.json) includes original receipt hashes and interpretation.

## Smallest next slice

Diagnose and prepare a narrowly scoped, disposable container sandbox-compatibility test. Host user namespaces are already enabled (`unprivileged_userns_clone=1`, maximum 127455). Docker reports builtin seccomp, AppArmor and cgroup namespaces. [Docker's official seccomp documentation](https://docs.docker.com/engine/security/seccomp/) describes namespace syscall restrictions: container policy is a likely cause, not yet a proven attribution between seccomp and AppArmor.

Inspect the installed Docker policy and exact bubblewrap namespace syscall requirements before proposing any policy change. Retain all unrelated default restrictions. Acceptance must demonstrate successful task/board writes, denied sibling writes, no network, clean ownership-based cleanup and unchanged gateway. Do not enable privileged mode, blanket unconfined policies, disable Codex sandboxing or change daemon/sysctl settings to obtain a pass. A host-native engineering lane is the alternative if a small supported container policy cannot be established.

After compatibility: exercise full Hermes profile/dispatcher/tool callbacks and approval behavior without inference; prepare reversible deployment; provision the dedicated API identity only for a separately authorized bounded canary. Repo admission, task/evidence linkage and human merge/deploy review remain required. Custom budget enforcement remains deferred to operator API-portal controls. Full native worker lifecycle and authenticated automated coding are not demonstrated by this checkpoint.

## Revised review candidate

Credential-free bundle: `/tmp/rras-native-container-checkpoint-baooa2kt/candidate`.
Manifest SHA-256: `f0c854004f2d383f5afcc09d60aa3273028f5fb759814c360e8c1c164537724d`.
It contains the corrected launcher and denial prerequisite; it has not been rebuilt or executed. Repeating identical container restrictions is not expected to resolve the observed failure. No operator installation or activation is requested at this checkpoint.

Verify the bundle without Docker or credentials:

```bash
python3 -B - <<'PY'
import hashlib, json
from pathlib import Path
review = Path('/tmp/rras-native-container-checkpoint-baooa2kt/candidate')
manifest = review / 'manifest.json'
assert hashlib.sha256(manifest.read_bytes()).hexdigest() == 'f0c854004f2d383f5afcc09d60aa3273028f5fb759814c360e8c1c164537724d'
files = json.loads(manifest.read_text())['files']
assert {str(p.relative_to(review)) for p in review.rglob('*') if p.is_file() and p != manifest} == set(files)
for name, digest in files.items():
    assert hashlib.sha256((review / name).read_bytes()).hexdigest() == digest, name
print('Review inventory and hashes verified; no execution performed')
PY
```

Focused source validation: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_rras_native_activity.py -v`: **18 passed**. The new test distinguishes namespace startup failure from meaningful denial. Runtime source compilation and candidate inventory/hash verification also pass. No full legacy-suite rerun is required for this slice.

2026-10-05 bounded follow-up: [host-worker assessment](rras-native-host-worker-assessment.md) records a single namespace diagnostic and stops the container lane at the custom-policy cost threshold. Its host-native candidate proposal supersedes the next-slice recommendation above; existing receipts remain historical evidence.
