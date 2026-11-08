# Engineering History Workspace — approved v0.2 completed

Completed November 6, 2026 (America/New_York). The explicit project closeout was
recorded at `2026-11-07T04:32:09.067960Z`, or 11:32 p.m. Eastern on November 6.
The artifact filenames use the UTC date.

**The approved v0.2 implementation, deployment, data adoption, authenticated
browser acceptance and explicit project closeout are complete. No v0.2 work
remains pending.** The original review and approved architecture drafts remain
unchanged.

Open the [completed project](https://jarvis-coding.reviellorobotics.com/#scope=repository%3Ajarvis&project=prj_96d2416636975124bfca948fdbbce4bc)
or its [historical closeout #33](https://jarvis-coding.reviellorobotics.com/#scope=repository%3Ajarvis&project=prj_96d2416636975124bfca948fdbbce4bc&closeout=33).

The exact saved architecture is
[the v0.2 implementation reconciliation](PROJECT-WORKSPACE-AS-BUILT-ARCHITECTURE-20261107.md).
It is saved architecture **version 3**, an as-built reconciliation of approved
v0.2, not a new feature-scope version. Its exact bytes are also in merged
[Jarvis source](https://github.com/shanereviello/jarvis/blob/354a893999b5006bdf3c31175f4e52d8d0306478/engineering/docs/engineering-project-workspace/PROJECT-WORKSPACE-AS-BUILT-ARCHITECTURE-20261107.md).

## Requirements and delivered behavior

| Approved requirement | Final implementation and live record |
| --- | --- |
| One repository/category per project | Stable scope identity, versioned display name/description and optional credential-free Git URL; scope metadata creates no execution admission or access grants. |
| One primary project per assigned work | Explicit assignment/removal/reassignment and design-reference history, scoped validation and concurrency heads; unassigned work remains a view within its scope. |
| Initial non-Git category | Only `jarvis-non-git`; no fake repository/URL/commit; Git baselines explicitly not applicable. |
| Project information | Overview, intended outcome, scope/exclusions, optional owner, independent lifecycle/archive state, revision/source/principal times, explicit architecture identity and starting/current baseline references. |
| Versioned architecture | Exact retained Markdown, predecessor/content digests, change summaries, attribution, governing designation history, saved drafts, diffs/downloads and closeout/work pins. |
| Git-only baselines | Consecutive immutable exact-commit records, source/reason history, original starting selection, current selection and closeout pin. |
| Scope → project → work webpage | Read-only scope details/history, All projects/All work/Unassigned views; project Overview, Work, Architecture, Baselines and History; existing work detail/timeline/documents/evidence. |
| Accurate aggregate/history views | Distinct work counts; reported outcomes separate from project state; exact outcome revision and older-revision labels; last activity, attribution and dated immutable closeout context. |
| Durable preservation and access boundaries | Explicit owner-only schema upgrades, unchanged prior bytes/key, backward-compatible signed snapshots, scoped reads and unchanged authentication/grants/hardening. |
| Adoption and closure | Approved 14-item mapping applied; current effort separately retained; final architecture/baseline/work outcome, browser acceptance and explicit dated closeout recorded. |

## Real project and work records

The current project, **Engineering History Workspace**, is `completed` with one
assigned work item, **Verify expanded web UI codebase**. That item links this
actual Codex conversation and now has a `completed_claim` outcome for its current
scope revision 1. The outcome is an explicit reported completion, separate from
the operator-reported browser acceptance and deployment verification.

The operator-approved retrospective memberships remain:

| Project | Primary work items | Treatment of original history |
| --- | ---: | --- |
| Engineering History Foundation and Dashboard | 12 | Original work bytes retained; retrospective association times/reasons explicit. |
| Managed Coding Workflow Documentation | 2 | Original work bytes retained; retrospective association times/reasons explicit. |

Both retrospective projects remain `planned` with architecture/baselines not
recorded. This honestly records the newly created grouping; it does not assert
that the older work itself is planned or invent an original completed project
lifecycle. Jarvis now has **zero unassigned work items**.

Initial metadata revision 1 is recorded for `jarvis` (display name **Jarvis**,
verified GitHub URL), `robot_ws` (URL not recorded) and `jarvis-non-git` (URL not
applicable). Existing dashboard visibility remains Jarvis plus `jarvis-non-git`;
recording `robot_ws` metadata did not silently expand dashboard grants.

## Architecture and Git baselines

| Saved architecture version | Meaning | SHA-256 |
| --- | --- | --- |
| 1 | Exact original editorial v0.1 draft | `296f1d3ddbb7443a2bc642875ebc203acbb1a56e073e666b5b013bb81bb46890` |
| 2 | Exact approved editorial v0.2 design | `23752a4bcc5591459bd5418513e7917c35ee6405d3bb3dfca19b2b9bb0ed97d4` |
| 3 | Exact committed implementation reconciliation; now governing and pinned at closeout | `3612a5c76aa1b39f3e58decf5b23dc3f041514413ddf889df697e838d8cfb973` |

The original work association remains pinned to architecture **2**, preserving
which approved design this work was intended to follow. Designating the final
as-built version 3 did not rewrite that historical reference. Version 3 retains
the exact version-2 predecessor digest and baseline 4 at save time.

| Git baseline version | Exact commit | Role/history |
| --- | --- | --- |
| 1 | `87fb60b1f13003daf90ad94cbed6d96053d04ec6` | Original starting baseline, retained. |
| 2 | `4e0ef58f9d9b6e4ee66cb7d70207d2de5aaf1c25` | Initial project workspace merge. |
| 3 | `bc11affd471b01ce5e5dbd384c50eabfef0918f5` | Previously deployed tab-navigation repair, recorded retrospectively with its actual recording time. |
| 4 | `354a893999b5006bdf3c31175f4e52d8d0306478` | Final v0.2 merge, selected current and pinned at closeout. |

The two added commits were verified in the actual Jarvis Git object database and
merge ancestry. Baseline provenance remains reported source information rather
than an invented independent release attestation.

Closeout #33 captures project state, membership, exact work/outcome revision,
governing document/version/hash, final Git baseline, scope-metadata boundary and
signed work/project/scope snapshot. Its dated historical view and document pin
were read back successfully. The real pre-intake signed snapshot still returns
the exact earlier project view, including its then-current metadata/designs.
The client spool has **zero pending deliveries**.

## Source, production and evidence

[PR #91](https://github.com/shanereviello/jarvis/pull/91) is merged. Tested source:
`705f69c057a1e2b6e134d61a69519c409928425d`; merge:
`354a893999b5006bdf3c31175f4e52d8d0306478`. Their runtime/contract/configuration
trees match. The dedicated review branch is clean; no default branch was pushed.

| Installed runtime | Manifest SHA-256 |
| --- | --- |
| `/opt/rras-engineering/releases/history-e41711fe4adf` | `5f7f5df3269d21644836a55c82d44ac7f0ecc97ab354d160a46e1bd2b08ab40f` |
| `/opt/rras-engineering/releases/history-web-ea65bd788273` | `d49f6502521643a58417817f9abb05add0b0a7868ade1d5bba3eb4ba9eab5659` |

Both services are active/enabled on those exact runtimes. Independent host reads
verified every installed package member and root custody. SQLite is schema 3.
The operator supplied the successful pinned production-helper result, reporting
preserved work/project bytes, prior schema/signing key, old signed snapshots,
authentication, grants, service identities/hardening/enablement, actual UID-993
scoped and new-snapshot reads, reader-authoring denial, live public-key fetch and
unauthenticated origin denial. The root-private production receipt itself was not
independently reread by this unprivileged agent; that preservation evidence is
attributed to the operator-supplied helper result. Later authorized reads verified
the final application records and immutable snapshot behavior directly.

Protected deployment journal:
`/var/lib/rras-project-workspace-v02-completion-20261107`. The helper reports a
stopped-service pre-upgrade copy SHA-256 of
`047e319d3d9a5b4d02a7f212ed762bd397740ccb356a4aaa237fdf43e47141a3`.
No database restore or Cloudflare configuration change was performed, and no
paid model calls were made by this rollout. Private requests/receipts and raw
operational records remain outside Git.

Validation completed:

- **933** history regression tests passed; the one opt-in browser skip was run
  separately and passed in actual Chromium.
- **4** checks passed against the exact packaged synthetic rehearsal.
- **15** privileged isolated host checks passed, with retained package bytes and
  cleanup independently checked afterward.
- **27** production-helper checks passed, including actual disposable migration,
  complete simulated deployment and failures before/after migration.
- Live authorized reads verified all three exact architecture digests, v2→v3
  comparison, final memberships/counts, original work revision/design pin,
  pre-intake snapshot identity and final historical closeout/document pins.
- The operator explicitly answered **“All checks pass”** for the refreshed live
  authenticated webpage: Jarvis Scope details, all five project tabs,
  architecture version 3 including comparison with 2, and current baseline 4.
  This is operator-reported live acceptance, separate from synthetic tests and
  independently verified API/package reads.

## Retained scope boundaries

Future automatic chat collection, browser authoring, multi-repository projects,
multiple primary projects per work, additional non-Git categories, non-Git
baseline types and broader visual customization remain outside approved v0.2.
This completed effort does not claim to deliver those later features. Retained
private database copies are not a tested backup/restore system.

The earlier release and sudo-handoff reports are historical checkpoints. Their
pending actions are resolved by this completion report; do not rerun their
one-shot rehearsal or upgrade commands.
