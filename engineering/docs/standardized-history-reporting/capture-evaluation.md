# First capture comparison — Linux synthetic evidence

Executed November 7, 2026 with no provider/model calls, real credentials, or real
session reads. Neither collector was enabled in a real checkout. The evaluation
had an isolated home, empty synthetic Git repository, no remotes, and explicitly
disabled cloud/analytics flags. No packet-level network audit is claimed.

| Candidate | Official release archive | Verified SHA-256 |
| --- | --- | --- |
| SpecStory CLI 2.17.0 | `SpecStoryCLI_Linux_x86_64.tar.gz` | `5e4b0275a0f71ad0825207688ba7c8c844ad301326a94e814fd59f7e20a90b69` |
| Entire CLI 0.13.1 | `entire_linux_amd64.tar.gz` | `c7afbecd5e18bee7a97b69ec318ff9f14033994eae309746c98ec7eed9c33048` |

Archives came from the respective official GitHub release assets. Published asset
digests were checked before extraction and execution. The standalone fixtures
run under the normal restricted development environment, without global installs.

## Findings

- SpecStory retained prompts and answers in both legacy `event_msg` and modern
  `item_completed` UI-event fixtures. Repeated exports were stable; a running
  watcher picked up an appended exchange into a private output directory.
- A response-item-only fixture exited successfully but produced no conversation
  text. This is an explicit negative coverage result, not a successful capture.
  Intake must check coverage and content; a zero exit and a Markdown file are
  insufficient. The actual installed session format still needs a reviewed check.
- Entire installed seven Codex hooks in the synthetic repository with automatic
  transcript pushes and telemetry disabled. All four supplied lifecycle hook
  calls succeeded, and the ended session was inventoried. This no-code session
  did not create a persistent checkpoint ref in the exercised automatic path.
- Collector operations did not change the synthetic native transcript. The
  synthetic repository had no Git remotes.

[Sanitized result](capture-fixture-result.json) retains versions, executable
hashes, flags/settings and coverage limits. Replay the source evaluator with
fresh state and the two reviewed binaries; it refuses an existing result folder.

## Remaining before selecting a production collector

The running Hermes container (`b99f4564d5e1`) was inspected without opening its
configuration or sessions. Its installed `hermes_cli/session_export_md.py` has
SHA-256 `750953cd48cd8cf7435a1c7427f5ff3e1c5d10fda9519cc7a4d3889e7d1b2ffa`.
The checked-in `hermes_fixture_probe.py` ran against that exact source as UID1000:
four synthetic messages across two compression segments retained exchanges,
tool-call data and lineage; native digest verification passed, tampering was
refused, output was 0600, and the temporary directory was removed. No SessionDB
was opened. This establishes an existing renderer to evaluate, not completed
real-session capture, live lineage recovery or secret-filtering acceptance.
The renderer embeds export time, so source-identity/content deduplication should
precede repeated rendering. Inspection also found no installed Linear-specific
gateway adapter filename; its generic API/webhook code is not proof of an enabled
or suitably authorized incoming Jarvis route.

Test actual installed desktop/managed sessions, uncommitted worker teardown,
resume/compaction/compression, worktree/project switching, secret filtering,
source corruption and storage limits, Mac behavior and Hermes coverage. A real
session pilot requires the separate authorization called for by v0.3. The
operator subsequently authorized this chat only, and the bounded pilot below
was executed. That authorization does not cover other real sessions. Do not infer these results
from synthetic Linux fixtures. SpecStory remains the first candidate to validate,
not a deployed or finally selected collector. No custom recorder is authorized
merely because either candidate has a coverage gap.

Release sources: [SpecStory 2.17.0](https://github.com/specstoryai/getspecstory/releases/tag/v2.17.0),
[Entire 0.13.1](https://github.com/entireio/cli/releases/tag/v0.13.1).

## Prepared single-chat pilot

`capture_pilot.py` is prepared and smoke-tested on synthetic input using both
pinned binaries. It requires an explicit authorization reference and exact session
UUID, refuses a different session or an unsafe source file, uses a fresh private
HOME/Git repository, and retains exact command output privately. No provider
credentials are supplied. Only counts/digests appear in console results.

The smoke test exposed SpecStory's working-directory discovery filter: an explicit
session ID did not find a transcript with another `session_meta.cwd`. The runner
therefore retains the exact source snapshot separately and relocates only that
metadata field in the collector copy. Neither collector operates in the real
checkout. The corrected synthetic smoke retained both visible messages, repeated
SpecStory output identically, tracked the Entire session through four hooks and
preserved both copies. This proves the isolated replay mechanics; actual native
working-directory discovery, other branches/machines, real hook delivery and
uncommitted worker cleanup remain distinct acceptance cases.

## Approved chat pilot result

The operator replied **“Approve this chat only.”** The selected latest saved
source had the same approved chat UUID, Codex CLI version **0.159.0**, and source
label `vscode`. Its read-only complete-line snapshot contained 3,693 records,
26,024,426 bytes; SHA-256
`1f597d3d305900f9d5ea1d1ef4e73adeb0e622d221b39b4e3d86fa28527c2152`.
The exact snapshot and collector output remain private outside Git.

| Check | Observed result |
| --- | --- |
| SpecStory 2.17.0 repeated exports | Both exited zero; nonempty output was byte-identical. |
| Source UI user text | All 24 identified messages present. |
| Response-message cross-check | All 83 assistant commentary messages, 19 final answers and 24 user exchanges present by full-text inclusion. |
| Source records omitted from readable export | Three app-navigation context messages and one environment-context message. These remain in the private native snapshot; the readable export is not the entire native record stream. |
| Entire 0.13.1 | Four lifecycle replay hooks exited zero and the session was tracked. No persistent checkpoint ref was produced without a code change/commit in the isolated checkout. |
| Custody | Exact source snapshot retained separately; only `session_meta.cwd` relocated in collector copy, which neither collector changed. Original source opened read-only; appends may continue. |
| Operational effects | No supplied provider credentials, model calls, cloud sync, analytics or real-checkout hook changes. No packet-level audit claimed. |

The native app writes this source with mode 0664. The pilot leaves it unchanged
and treats it as untrusted evidence, not authenticated authority. All newly
retained pilot files live below a new 0700 directory and are 0600. Source symlinks,
wrong session IDs, non-owner files and world-writable source files are refused.

This supports SpecStory for the tested visible-exchange export. Full-text
inclusion does not independently authenticate authors or establish complete
tool/media capture. Keep the response-item-only negative fixture, native-path
discovery, managed-worker cleanup, secret filtering and untested platforms visible
before final production collector selection. The pilot did not install capture
or make native agent messaging operational.
