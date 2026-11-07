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

Test actual installed desktop/managed sessions, uncommitted worker teardown,
resume/compaction/compression, worktree/project switching, secret filtering,
source corruption and storage limits, Mac behavior and Hermes coverage. A real
session pilot needs its separate reviewed selection. Do not infer these results
from synthetic Linux fixtures. SpecStory remains the first candidate to validate,
not a deployed or finally selected collector. No custom recorder is authorized
merely because either candidate has a coverage gap.

Release sources: [SpecStory 2.17.0](https://github.com/specstoryai/getspecstory/releases/tag/v2.17.0),
[Entire 0.13.1](https://github.com/entireio/cli/releases/tag/v0.13.1).
