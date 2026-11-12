# v0.4 acceptance status — November 11, 2026

This is a working assessment against section 11 of the designated v0.4
architecture. It distinguishes deployed behavior, observed live tests and
fixture-only coverage. It does not designate a new architecture or close the
project. Earlier acceptance snapshots remain retained.

| Scenario | Current evidence and remaining boundary |
| --- | --- |
| Project, architecture and work mapping | This project has retained v0.4 architecture and eight explicit Linear/work mappings. General creation of a history project when an agent drafts architecture remains to be designed and demonstrated. |
| Separate agents; direct mention and delegation | Separate Jarvis and Codex applications and routes exist. Scoped live Codex mention, delegation, follow-up, cancellation, and response were demonstrated under the earlier runtime. Ongoing paid execution is now authorized for the eight mapped issues on the new runtime; its live issue-specific route remains to be demonstrated. |
| Credential and ingress separation | Separate actors, scoped routing and negative signature/authorization tests exist. Fixture coverage does not establish every possible adversarial production path. |
| Direct architecture decision | Exact v0.4 approval and architecture are retained. A disposable history fixture verifies that an imported Linear decision retains its source, is idempotent, and does not designate a draft; designation is a separate project operation. A new operator-to-Codex decision and designation through the live Linear route has not been demonstrated end to end. |
| Hermes-specific outage | A separately authorized read-only Codex request completed while Hermes was stopped, with shared infrastructure running. This did not test direct architecture decision recording during the outage. |
| Shared infrastructure outage, uncertain delivery and restart | Model-free recovery/reconciliation fixtures and a guarded n8n recreation passed. Full server reboot and a live lost-response/restart recovery scenario remain unverified. |
| Jarvis regression | A Jarvis acknowledgement completed after Hermes restart; actual delivery and capture were verified. This does not cover all Jarvis actions and follow-up paths. |
| Handoff in each direction | Both tested native directions reached retained requested, acknowledged and completed states under distinct actors. The exact content of the reverse-handoff reply was not independently verified. A complete multi-hop continuation remains open. |
| Capture and work association | Desktop Codex, selected Linear Codex, and approved future Linear-linked Hermes capture are enabled. A new REV-50 Hermes session was captured with the correct work/architecture pins and its full digest verified. After the v2 runtime deployment, the older capture collector rejected the new policy; the compatible collector release restored delivery. A new REV-50 Codex session was captured with the correct work/architecture pins and workspace, and its single evidence chunk's digest and length were verified. The seven other issue bindings were receipt-verified at installation; their live capture associations have not each been individually tested. Earlier sessions remain unchanged; unknown issues stay unmapped. |
| Bounded paging and retained evidence | The scheduled Hermes collector processed six sessions across two pages in one pass, with no failures or pending delivery. Page/time budgets mean an arbitrary backlog may require additional passes. |
| Multiple work items in one conversation and interactive continuation | Session-level attribution has an explicit limitation. A live REV-50 Linear Codex acceptance session now has an independently read-back, agent-reported `coordinated_by` relation to the separate interactive session that coordinated it. This does not claim native thread resumption or associate every interactive exchange with REV-50. A full cross-work switch and an actual Linear-to-interactive continuation remain to be demonstrated. |
| Loop, replay and cancellation guards | Source and isolated fixture coverage exists; the live cancellation and both individual handoff directions passed. A live agent-echo and uncertain-result recovery exercise is not claimed. |
| Retrospective architectures | Two previously missing Jarvis project documents were saved as explicitly retrospective, unapproved drafts. Historical approval was not invented. |
| Reference interface and Jarvis retrieval | The authenticated dashboard's existing project/reporting and private evidence preview/download paths passed operator checks. A reviewed structured-field snapshot was published and read through the actual Hermes MCP; this does not imply automatic publication of every future record. |
| Closeout | The detailed as-built, final work dispositions, merged source/baseline and complete acceptance evidence still need reconciliation. Source and production releases must be compared explicitly; the feature branch contains post-baseline commits. |

The issue-specific v2 runtime was first installed with execution disabled.
Its previous policy and journal were backed up privately, and the migration
receipt is retained. The operator subsequently authorized paid execution for
the eight mapped issues; the journaled authority transition completed and the
runtime and eight issue-specific sockets are active. The transition script
started no model and verified unauthenticated denial. A paid, read-only REV-50
Linear request completed from its assigned checkout and its captured evidence
was verified in owned history. A second REV-50 session reported creating,
reading, and removing its own temporary file with a clean checkout; transport
recorded completion and owned history recorded its work and workspace. The
other seven production workspaces remain unverified live. No hard per-turn or
spending cap is enforced.

The collector uses a fixed session-creation cutoff for each issue mapping; it
will not silently reassign older captured evidence. A work association describes
the session context and does not prove every message belongs to that work. The
user's desired Linear-first backlog → draft architecture → history-project
onboarding needs an explicit design and acceptance before being represented as
an existing capability.
