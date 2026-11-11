# Standardized History Reporting Format and Rules

The operator approved exact editorial **v0.4** on November 7, 2026 and authorized
implementation. The retained architecture bytes still say draft because approval
is a separate historical designation, not an edit to the document.

- [Approved architecture v0.4](../engineering-project-workspace/STANDARDIZED-HISTORY-REPORTING-FORMAT-AND-RULES-ARCHITECTURE-DRAFT-v0.4-20261107.md)
- SHA-256: `4ed76e0a493a5ae45bcc6154cb57fac3f1551644b1e823d5c96b1e2713365329`
- Source baseline: `354a893999b5006bdf3c31175f4e52d8d0306478`
- [Shared agent guidance](shared-agent-guidance.md)
- [Linear work and decision templates](linear-templates.md)
- [Capture evaluation](capture-evaluation.md)
- [Linear integration and remaining installation steps](linear-integration.md)
- [Private evidence byte custody](evidence-custody.md)
- [Selected-session capture and replay](capture-intake.md)
- [Reporting reference UI](reference-ui.md)
- [Passive Linear observation](linear-observation.md)
- [Curated reporting profiles and MCP retrieval](curated-reporting.md)
- [Automatic runtime reporting and selected background capture](runtime-reporting.md)
- [Explicit native handoff transport and acceptance limits](native-handoff.md)
- [Scoped native Jarvis reporting](hermes-runtime.md)
- [Server runtime installation candidate](runtime-host-setup.md)

## Current deployment status — November 11, 2026

The history service, reporting dashboard, selected Linear observer, Jarvis history
reader, and n8n transport workflows are active. The operator verified reporting
and evidence preview/download in an authenticated browser. The approved
structured-field profile and 17 reviewed records were published to Jarvis, and
the three earlier curated entries were preserved. Desktop Codex capture, selected
Linear Codex capture, and future Linear-linked Hermes capture have been enabled
under the operator's stated selections. They are not a claim of complete history.
Future Jarvis sessions on REV-46 through REV-53 now receive their verified
issue/work/architecture context, effective from each mapping's installation;
earlier sessions remain unchanged. A real REV-50 session and its retained bytes
were verified. The collector now drains multiple bounded pages in one pass.

Separately authorized read-only live tests verified direct Codex mention,
delegation, follow-up in the same session, cancellation, repository read, and
Jarvis-to-Codex and Codex-to-Jarvis handoff transport. Both handoffs' requested,
acknowledged, and completed transitions were retained in owned history. A read-only REV-50 request also completed while Hermes was stopped. After
each test the original Codex runtime was restored with execution disabled; it is
not enabled for general coding. A separate REV-50 live test made one uncommitted
regression-test change in a private, remote-free checkout; independent scoped
validation passed all 11 tests. The reverse-handoff reply's exact content has not
been independently checked. See [integration evidence](linear-integration.md).

Actual server reboot, live restart/uncertain-delivery recovery, broader
project onboarding and overall closeout remain open. The selected n8n reader and
handoff jobs now use an operator-approved host-loopback endpoint, avoiding their
previous dependency on n8n’s changing container IP. A guarded n8n recreation
passed with the loopback binding and passive readers intact. Both older Jarvis
projects have explicitly retrospective, unapproved architecture drafts; no
historical agreement was inferred. See [current validation](v04-validation.md).

For the remaining acceptance scenarios and their evidence, see
[v0.4 acceptance status](v04-acceptance-status-20261111.md).

The sections below include earlier implementation notes for provenance; where
an earlier operational state differs, this current status takes precedence.

## Approved v0.4 integration direction

Use existing n8n and verified ingress; preserve Jarvis. Codex has a distinct app,
credential and runtime route with both mention and delegation permissions. n8n
owns OAuth and delivery; the private adapter owns only Codex runtime bindings and
results. The earlier standalone OAuth/inbox code below is retained source-only
for provenance and tests, **superseded for deployment**. It must not be installed
from the old registration instructions.

The exact v0.4 bytes are retained/designated as version 4 through the existing
history service, eight work memberships now pin version 4, and SHRR-03/08 have
explicit revised definitions. REV-46–53 are updated, REV-54 retains the new
operator decision, and Linear has a separate v0.4 reading copy. Historical
versions and original work identities remain. The owner-approved production
store is now schema 5, and the history service uses the matching staged release.
The Codex adapter has write access only to the `jarvis` repository scope.

[Current integration design and runbook](linear-integration.md) describes the
remaining registration, deployment and live acceptance boundaries.

The native Codex app is now registered and its n8n OAuth viewer has been verified
as Codex in Reviello Robotics. A single unpublished identity diagnostic was
created/executed through code, preserving all six previous workflow records.
Four inactive transport workflow files pin the verified actor and current v0.4
work revisions. Actual isolated n8n engine tests cover normal intake, duplicate
handling, initial reply, one dispatch, reconciliation and final reply, and caught
a GraphQL expression defect now corrected in source. The n8n transport
workflows, their PostgreSQL transport migration and the coding runtime are not
deployed. The separate owned-history schema migration is deployed; its current
Linear project and eight issue-to-work mappings have been written and read back
through the scoped history API. The sections below retain earlier source history;
[v0.4 validation](v04-validation.md) gives current evidence and remaining
acceptance.

Private artifact byte custody is now implemented as an explicit schema 4 → 5
upgrade, with scoped immutable chunks and signed historical reads. The combined
evidence/reporting/dashboard/package fixtures passed 115 tests. Selected-source
Codex/Hermes adapters, private redaction, durable export/request replay and bounded
passive jobs are now implemented. The reporting reference UI exposes mapped work,
attempts, checkpoints, handoffs, decisions, capture gaps and exact private exports;
actual Chromium fixtures cover navigation, literal source text, verified Unicode
downloads, corruption clearing and unmapped evidence. The operator applied the
production migration and verified the active service plus distinct Codex/dashboard
scopes; no production artifact bytes have been collected. Collector activation,
production Linear observation and curated-profile installation, native handoff
acceptance and final deployment remain unfinished. Curated profiles
and actual offline MCP search/read with distinct Unix UIDs now pass synthetic
acceptance; this does not publish private production history or enable a tool.

As of November 8, the native coder source has exact retained task contracts,
automatic start/progress/terminal reports, numeric native usage summaries and
scoped checkpoint/handoff tools. Actual offline native MCP callbacks pass across
separate Unix identities. The n8n fixture imports sixteen workflows, including
the bounded existing-Jarvis admission patch and passive handoff-history reader;
it covers both handoff directions, source attribution, echo refusal and preserved
unselected Jarvis behavior. No coding model is invoked. The operator selected
reuse of the existing engineering API setup and confirmed server01 holds coding
history; there is no separate Mac source in this installation target.

Both older projects that lacked retained architectures now have truthful saved
retrospectives. Their original agreements remain unknown and the new drafts are
not designated governing. Existing work, membership, baselines and closeout state
were preserved through the normal scoped history API. SHRR-07 has a recorded
completion claim; the other work items retain their current unfinished status.

The latest branch extends that work with selected native Jarvis lifecycle and
checkpoint import, existing-Jarvis origin/context admission, and credential-free
selected Codex source reads. Its latest isolated n8n probe imports 16 workflows;
the Hermes native reader fixture confirms compression lineage, exact source
selection, reasoning exclusion and unchanged source bytes. Review-only systemd
unit candidates now target the existing `jarvis-net` bridge and the existing
engineering API credential source, giving the native coding service only the
OpenAI key. An exact-commit offline release packager now bundles the pinned
Codex executable/resources and Python imports needed by isolated `-I` services;
its rendered `.pth` binding and candidate systemd paths are tested. The server
Codex runtime candidate remains inactive. Current focused reporting tests pass;
the broad legacy test suite is limited by missing test dependencies and
host-only ACL/service checks in this workspace environment.

## Earlier v0.3 source position (historical; see v0.4 direction above)

This first source slice retains the approved design, a repeatable model-free
capture comparison, private Linear app registration manifests, and an isolated
signed-event inbox/publication foundation for two distinct agents. It is not a
completed v0.3 deployment. No new source is loaded into existing services.

The live private-history service records project
`prj_b728c1f781995591be646f61a049d556`, all eight SHRR work definitions, all three
exact document versions, governing architecture version 3, and the starting Git
baseline. Creation/replay was rehearsed against a disposable database first.
The connected Reviello Robotics workspace/team has been verified. The
[Linear project](https://linear.app/reviello-robotics/project/standardized-history-reporting-format-and-rules-a28a39584792)
contains eight execution issues, **REV-46–REV-53**, matching SHRR-01–SHRR-08.
**REV-54** records the existing architecture agreement with source attribution;
it is a decision record, not a ninth execution item. Linear also has a full
architecture reading copy. Exact bytes remain in owned history.
Creation/readback and UUIDs are retained privately; a progress checkpoint links
the actual objects through the existing history API. Typed owned-history mapping
records are now source-tested but not deployed. These setup writes used the connected
human-authorized MCP identity, not a native Codex app identity.

An existing active Jarvis app actor was discovered and preserved. Codex still
needs its own app registration. A Codex-only registration option and a private,
independent PKCE callback/token-custody implementation are now source-tested.
No app registration, credential replacement, live native messaging, merge,
ingress change or production installation has been performed by this source.

| Plan | Current position |
| --- | --- |
| SHRR-01 | Pinned Linux comparison, installed Hermes renderer fixture, and operator-authorized single-chat pilot executed. SpecStory retained tested visible exchanges; Entire tracked the no-code replay without a persistent checkpoint. Actual native discovery, managed/Mac/rotation coverage and final selection remain. |
| SHRR-02 | Actual Linear project, eight linked execution issues, architecture reading copy and attributed agreement record created/read back. Templates include deviation handling without a routine approval queue. Native-agent review remains part of SHRR-03 acceptance. |
| SHRR-03 | Signed inbox, runtime/handoff bindings, frozen publication, per-app PKCE callback, token-pair custody/renewal/revocation and explicit OAuth-backed publisher exercised on fixtures. Actual Codex registration, existing Jarvis capability verification, runtime delivery/continuation and live acknowledgments remain. |
| SHRR-04 | Strict metadata contract, immutable metadata stream, explicit owner-only v3-to-v4 migration, scoped Unix intake/reads, entity/context checks and signed four-stream views implemented/tested. Private chunk custody/finalization remains; artifact manifests are refused until bytes can be verified. No production upgrade. |
| SHRR-05 | Capture watcher behavior tested on fixtures. Production capture/observation delivery is not enabled. |
| SHRR-06 | Existing project/work UI shows the explicitly recorded project. New reporting/evidence UI and curated reporting publication remain. |
| SHRR-07 | Older project architectures still need truthful retrospective reconciliation. No earlier approval has been invented. |
| SHRR-08 | Focused synthetic acceptance started. Full cross-agent/runtime/privileged/pilot/production acceptance and closeout remain. |

The inbox's SQLite file is a private integration spool, **not another engineering
history authority**. It does not replace the owned history database or mutate it
behind its service API. Final history relationships must be implemented through
reviewed additive contracts and migrations. There is no implicit schema upgrade,
merge, deployment, provider invocation, or automation enabled by this source.

## Validation of this source slice

- 112 focused reporting tests passed: signature/scope denial, distinct agents,
  direct Codex follow-up/elicitation, SQLite replay/custody, handoff attribution,
  bounded HTTP intake, frozen activity publication, PKCE/state/actor validation,
  parallel callback denial, private token-pair custody, renewal/revocation and
  lost-response behavior. No external API calls were made by these tests.
- Typed metadata checks reject approval/launch authority fields, wrong execution
  counting, missing exact predecessors, invalid handoff/session associations,
  malformed manifests, changed observation digests and oversized requests.
- 138 existing history/project/scope/web regressions passed.
- A later combined history/access/Unix/project/scope/web/reporting run passed
  401 tests with one opt-in installed-Chromium test skipped. After CLI/package
  additions, 168 focused metadata/Unix/snapshot/package tests passed. Counts from
  overlapping test commands are not additive. The opt-in Chromium test then
  passed using the previously downloaded workspace browser/libraries. Real cross-UID v4 host acceptance
  remains separate work.
- Both verified capture binaries were exercised on synthetic Linux fixtures.
- The installed Hermes exporter was exercised as UID1000 on synthetic
  dictionaries only; its temporary files were removed. No SessionDB was opened.
- The separately approved pilot read only this chat's selected saved transcript.
  Both collectors ran with isolated HOME/Git, cloud/telemetry disabled and no
  supplied credentials/model calls. No real repository hooks were changed.
- HTTP/thread-pool tests ran outside the execution sandbox after an independent
  minimal thread-pool probe reproduced its timeout inside the sandbox. No real
  API credentials, external messages or model calls were used by those tests.

These checks are source/fixture acceptance. They do not establish live OAuth,
registration, actual runtime handoff, production migration or authenticated
browser/MCP acceptance for the unfinished v0.3 capabilities.
