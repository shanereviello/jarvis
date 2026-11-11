# v0.4 acceptance status — November 11, 2026

This is a working assessment against section 11 of the designated v0.4
architecture. It distinguishes deployed behavior, observed live tests and
fixture-only coverage. It does not designate a new architecture or close the
project. Earlier acceptance snapshots remain retained.

| Scenario | Current evidence and remaining boundary |
| --- | --- |
| Project, architecture and work mapping | This project has retained v0.4 architecture and eight explicit Linear/work mappings. General creation of a history project when an agent drafts architecture remains to be designed and demonstrated. |
| Separate agents; direct mention and delegation | Separate Jarvis and Codex applications and routes exist. Scoped live Codex mention, delegation, follow-up, cancellation, and response were demonstrated; general Codex execution is currently disabled outside explicitly prepared tests. |
| Credential and ingress separation | Separate actors, scoped routing and negative signature/authorization tests exist. Fixture coverage does not establish every possible adversarial production path. |
| Direct architecture decision | Exact v0.4 approval and architecture are retained. A new operator-to-Codex decision and designation through the live Linear route has not been demonstrated end to end. |
| Hermes-specific outage | A separately authorized read-only Codex request completed while Hermes was stopped, with shared infrastructure running. This did not test direct architecture decision recording during the outage. |
| Shared infrastructure outage, uncertain delivery and restart | Model-free recovery/reconciliation fixtures and a guarded n8n recreation passed. Full server reboot and a live lost-response/restart recovery scenario remain unverified. |
| Jarvis regression | A Jarvis acknowledgement completed after Hermes restart; actual delivery and capture were verified. This does not cover all Jarvis actions and follow-up paths. |
| Handoff in each direction | Both tested native directions reached retained requested, acknowledged and completed states under distinct actors. The exact content of the reverse-handoff reply was not independently verified. A complete multi-hop continuation remains open. |
| Capture and work association | Desktop Codex, selected Linear Codex, and approved future Linear-linked Hermes capture are enabled. A new REV-50 Hermes session was captured with the correct work/architecture pins and its full digest verified. The seven other issue bindings were receipt-verified at installation; their live capture associations have not each been individually tested. Earlier sessions remain unchanged; unknown issues stay unmapped. |
| Bounded paging and retained evidence | The scheduled Hermes collector processed six sessions across two pages in one pass, with no failures or pending delivery. Page/time budgets mean an arbitrary backlog may require additional passes. |
| Multiple work items in one conversation and interactive continuation | Session-level attribution has an explicit limitation. A full cross-work switch and a Linear-to-existing-desktop or explicitly linked continuation remain to be demonstrated. |
| Loop, replay and cancellation guards | Source and isolated fixture coverage exists; the live cancellation and both individual handoff directions passed. A live agent-echo and uncertain-result recovery exercise is not claimed. |
| Retrospective architectures | Two previously missing Jarvis project documents were saved as explicitly retrospective, unapproved drafts. Historical approval was not invented. |
| Reference interface and Jarvis retrieval | The authenticated dashboard's existing project/reporting and private evidence preview/download paths passed operator checks. A reviewed structured-field snapshot was published and read through the actual Hermes MCP; this does not imply automatic publication of every future record. |
| Closeout | The detailed as-built, final work dispositions, merged source/baseline and complete acceptance evidence still need reconciliation. Source and production releases must be compared explicitly; the feature branch contains post-baseline commits. |

The collector uses a fixed session-creation cutoff for each issue mapping; it
will not silently reassign older captured evidence. A work association describes
the session context and does not prove every message belongs to that work. The
user's desired Linear-first backlog → draft architecture → history-project
onboarding needs an explicit design and acceptance before being represented as
an existing capability.
