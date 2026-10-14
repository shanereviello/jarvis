# Native CLI construction and harmless credential delivery

2026-10-12. Continues [canary preparation](rras-native-manual-canary-preparation.md). Source work is complete through the next administrator acceptance boundary. No installed release/profile, runtime records, secrets, service or timer changed. No inference or real credential use.

## Actual source validation

[probe_cli_credentials.py](../tools/rras_native/probe_cli_credentials.py) constructed the **real HermesCLI and real AIAgent** via native `_init_agent`, not a substitute constructor. Eight development checks passed: actual agent construction, codex_app_server mode, no inference attempt, network guard installed, no network attempt, exact kanban/skills, approval bypass off, and identical harmless file-to-environment delivery. Real conversation execution and turn/start are explicitly blocked in the fixture. [Machine-readable evidence](rras-native-cli-construction-evidence.json) records UID 1000 and systemd_delivery=false; this is not dedicated-account delivery acceptance. Private homes and all development attempts remain retained under `/tmp/rras-cli-construction-20261012-*`.

First construction attempted an optional Tirith download, which was blocked. Native `security.tirith_enabled: false` eliminates that background install in the Codex-only candidate. This does not disable Codex sandboxing or manual approvals. No Hermes terminal/MCP callback is configured. If that callback is enabled later, revisit its scanner policy before granting access. Earlier failed/no-network-attempt results are retained; they are not counted as acceptance.

Correct profile uses `provider: openai-api`, explicit `api_mode: codex_app_server`, disabled bfl, manual approvals and Codex network-off workspace-write. Profile review `...-04` supersedes -01/-02/-03; no installed configuration is replaced. Full provider resolution and actual CLI construction both passed with the harmless sentinel. This does not demonstrate a model turn, entitlement, actual lifecycle completion or callback behavior during inference.

Focused suite: **39 tests passed**, including five new refusal regressions (wrong identity, nonprivate directory, unexpected credential environment, malformed sentinel, symlink/directory). Python syntax, administrator Bash syntax, exact bundle inventory file hashes and operator-script hash passed. No full legacy repository suite rerun.

## Reviewed candidate and execution boundary

Candidate: `/tmp/rras-cli-credential-review-20261012-03`.

- `manifest.json` SHA256: `f6b823f9cbf0b04d82658950375abe01a8c03bafffb37a1f6a443548f20631a9`.
- Manifest covers probe source, corrected profile.json and codex-config.toml.
- Operator sidecar `operator-acceptance.sh` is separately pinned: `af80b165b716d52f81b6b95fe4ac28a845603f7d024c0796521ba82610a8a213`. Repository copy: [run_cli_credential_acceptance.sh](../tools/rras_native/run_cli_credential_acceptance.sh).

The script creates only a new root-owned review, unique root-owned nonsecret source fixture, unique private UID996 work directory and bounded transient systemd unit. It installs no persistent service, updates no installed profile/release, provisions no real credential and activates no timer. Existing native-10 is read-only source/runtime. The probe rejects any credential whose bytes differ from its fixed public sentinel, requires the delivered file inside CREDENTIALS_DIRECTORY and verifies the worker cannot open the original root-owned file. It never prints credential values. LoadCredential provides the read-only delivered copy; PrivateNetwork isolates the fixture and Python guards block attempted connections/inference. No claim this tests paid execution or production token secrecy from coding subprocesses.

Noninteractive sudo returned `a password is required`; therefore the actual systemd test has **not run**. Run this self-contained block on server01, once:

```bash
(
set -euo pipefail
SCRIPT=/tmp/rras-cli-credential-review-20261012-03/operator-acceptance.sh
EXPECTED=af80b165b716d52f81b6b95fe4ac28a845603f7d024c0796521ba82610a8a213
test -f "$SCRIPT"
test ! -L "$SCRIPT"
printf '%s  %s\n' "$EXPECTED" "$SCRIPT" | sha256sum --check -
bash "$SCRIPT"
)
```

The script defines every path/identity, verifies UID/GID/groups and disabled legacy service state, validates source hashes before root publication and validates root-owned bytes before execution. It prints **SAVE RUN_ID, UNIT, WORK, SOURCE_ROOT** before fixture creation. Enter the sudo password only in your terminal. Success requires nine passing cases (including original-source unreadability), UID996, systemd_delivery=true, no blocked attempts and zero model/API calls. Return the complete output and saved ID. Do not run a paid task or provide the real key.

## Exact retention/recovery policy

Stop at the first failure. Preserve printed WORK, SOURCE_ROOT, root review, output.log, evidence and unit identity. Never rerun the entire absent-only installation block once `/opt/rras-cli-credential-review-20261012-03` exists; send the failed stage for an exact resume procedure. No recursive ownership repair, wildcard cleanup, old-record deletion or fence release. A failed creation response does not prove ownership of a planned unit name.

Normal success needs no destructive cleanup: native agent close runs, the process exits, systemd collects the transient unit and its credential copy, while the harmless source fixture and evidence stay retained. RuntimeMaxSec=90 and TimeoutStopSec=10 bound fixture lifetime. On failure inspect only the saved exact unit; stop it only if confirmed-created and active. No unrelated account/process/unit may be signaled. Root-owned review/source fixture deletion is not needed and is outside this block.

After dedicated acceptance passes, prepare the bounded fresh repository/manual-canary invocation, native completion/evidence procedure and real credential provisioning review. The one-pass dispatcher can leave its child alive; the final canary invocation must keep the owning cgroup alive until verified completion and preserve evidence on timeout. No paid command or unattended service is authorized by this checkpoint. Portal spending policy remains operator-managed; application hard budgets remain deferred.

## Failed installed-systemd attempt and compatibility correction

Operator run `46f46fe045f54aa79db5e8fb99369f9f` exited status 1 before native CLI construction: the delivered credential argument was not a regular existing file. This is **not acceptance passed**. Preserve `/var/lib/rras-engineering/cli-credential-46f46fe045f54aa79db5e8fb99369f9f`, `/opt/rras-cli-credential-source-46f46fe045f54aa79db5e8fb99369f9f`, and review -02. The probe failed before creating its Hermes/Codex home, writing its JSON receipt or constructing an agent; output.log retains the failure. No real key was accessed.

Host systemd is 249. Its installed systemd.exec documentation explicitly supports `${CREDENTIALS_DIRECTORY}/name` expansion in ExecStart. The old command relied on `%d`; the observed output alone does not expose its resolved value. Revised command preserves literal `${CREDENTIALS_DIRECTORY}` through Bash for runtime expansion by the service manager, both in the cleared environment and credential argument. No shell runs inside the service. A new regression executes the generated command with a recording sudo stub and verifies the exact argv, LoadCredential source and absence of `%d`. It does not substitute for actual host delivery acceptance.

Fresh review -03 contains unchanged probe/profile/Codex bytes (same manifest pin) and a separately re-pinned corrected operator script. No old installation or evidence is overwritten. Run the current block above once; it chooses a fresh run ID. The failed unit exited status 1 and --collect was requested; no old-unit stop/removal is needed to submit this separate model-free fixture. Retain the failed paths.
