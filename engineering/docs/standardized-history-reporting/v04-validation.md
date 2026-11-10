# v0.4 source validation — November 7, 2026

The exact human-approved architecture is retained as owned version 4, with all
8 existing work IDs preserved and REV-46–53 updated. REV-54 retains the direct
operator decision as an attributed transcription, not a native app message.
No new architecture agreement is inferred from source tests or Linear state.

This source slice adds inactive n8n workflows, app-scoped transport SQL, a dedicated
Codex signature-verification Worker, and a private Codex App Server adapter. Jarvis
configuration remains unchanged. Old standalone OAuth source is superseded for
installation. Neither source publication nor these results establish deployment.

## Evidence

- Combined history/reporting regression: **865 passed, 1 skipped**. The skipped
  case is the existing opt-in browser acceptance; this slice changes no web UI.
  A legacy Starlette/httpx deprecation warning remains.
- Final focused runtime/registration/n8n tests: **29 passed**, covering actual
  local HTTP, private journal restart, frozen dispatch replay, closed/competing
  adapters, wrong app/issue/design/authority refusal, cancellation, and fixed
  workspace ownership across distinct issues. No real models are called.
- The isolated transport probe executes JavaScript in an existing n8n 2.28.3
  image and SQL in a fresh PostgreSQL 18 container. Both have no network or
  production mounts. Actual admission/follow-up/stop cases, 9 refusal cases,
  generated Code compilation, OAuth actor refusal, Worker HMAC/unchanged body
  forwarding, SQL receipt replay/conflict and prepared workflow queries pass.
  A real database uniqueness check prevents simultaneous runtime dispatches.
  Fixture data/container are discarded; installed images are never pulled.
- The installed Codex 0.159.0 binary generated public protocol schemas without
  starting a model. Initialization, start/resume, turn/start and turn/interrupt
  parameter shapes validate against them. See the companion compatibility JSON.
  Native runtime behavior still needs separately authorized acceptance.
- Exact approved Markdown digest is preserved. Four intentional two-space
  Markdown line breaks are retained; whitespace checks exclude only that
  end-of-line convention and pass for the remaining source.

The broad run preceded final isolated ownership/HTTP safeguards; focused tests
and the transport probe were rerun for those changes. Counts overlap and are not
summed. No new runtime, workflow, credential, migration, tunnel or production
service was installed or activated by this validation.

## Remaining

The distinct Codex app and credentials now exist, and its actual n8n OAuth viewer
and organization have been verified. Isolated n8n import and normal-path engine
execution now pass as described below. Credential renewal, runtime recovery/permissions, native
bidirectional handoffs, release packaging and separately authorized deployment/
real interaction checks remain. Artifact byte intake, automatic capture and
observation, reporting UI/curated retrieval and historical architecture closeout
remain unfinished SHRR work. Do not mark the project or SHRR-03 complete.

## Existing-installation correction

The operator's Cloudflare screenshots showed an existing Jarvis-only tunnel path
and Access service-token secret names. The initial undeployed Codex Worker omitted
the Access headers. Source now forwards both required service headers and refuses
missing Access credentials. The updated isolated probe passes those assertions
as well as the previous HMAC/SQL checks. The actual Access policy and tunnel path
are not tested by that synthetic probe. A separate step-by-step guide now makes
Worker creation, path routing, Access protection, OAuth and activation explicit.
No running Worker, tunnel route, Access policy or n8n setting was changed.

## Operator setup and client-ID correction

The operator subsequently reported saving the dedicated Codex app, OAuth and
bridge credentials, Access application/token, tunnel route and Worker. The
chosen public endpoint is the existing workers.dev hostname, with no custom
domain required. A read-only GET returned the expected Worker 404 refusal.
This verifies reachability only; signed production forwarding remains untested.
Read-only credential metadata confirms the separate OAuth2 and Header Auth
entries; secret values and token grants were not read.

The operator-supplied public OAuth Client ID has 32 hexadecimal characters.
Corrected the renderer to retain that format exactly rather than requiring an
actor UUID. Organization and actor IDs still require canonical UUIDs. The
focused n8n suite passes **20 tests**, and the disposable transport probe passes
with a synthetic 32-character client ID, including exact incoming comparison,
wrong-client refusal, Worker signing/forwarding and PostgreSQL replay checks.
No live workflow, SQL migration, OAuth grant or runtime was activated by these
checks. Subsequent identity binding and runtime credential preparation are
described below.

## Verified native identity and n8n engine acceptance

Created only the unpublished, manually triggered Codex Identity Check workflow
using the installed n8n CLI, then executed its read-only viewer query using the
saved Codex OAuth credential. The actual actor is Codex in Reviello Robotics;
its identity matches the independently connected Linear user record. Credential
values were not exported. Hashes of all six pre-existing workflow records were
unchanged across import. The separate runtime Header Auth reference is also
present. This diagnostic is not activation of the transport or coding runtime.

The source-retained opt-in probe is:

```bash
python engineering/tools/rras_reporting/probe_n8n_engine.py --isolated-containers
```

It starts disposable n8n 2.28.3 and PostgreSQL 18 containers in one network
namespace without outside connectivity or production mounts. It creates only a
synthetic fixture owner and credentials, imports all four workflows through the
fixture editor API, and publishes only its fixture webhook. Actual engine tests
pass header denial, committed receipt before response, duplicate receipt, initial
activity, exactly one runtime dispatch, completion reconciliation and final
activity. A restricted fixture transport role executes the source SQL function
and workflow queries; a Jarvis sentinel remains unchanged and unreadable by that
role. Containers, credentials and database are discarded afterward.

This test exposed an **invalid expression** in the generated GraphQL HTTP body,
missed by the earlier Code-node compilation and SQL-only probe. The actor query
is now literal JSON. The mutation body is constructed in Code and serialized from
a field, keeping GraphQL closing braces out of expression templates. The actual
engine test and **21 focused n8n tests** pass after correction.

The fixture manually triggers the scheduled workflows, redirects Linear/runtime
HTTP nodes to synthetic local endpoints, and enables fixture-only execution
retention for diagnostics. Thus production schedule timing, retention settings,
token renewal, live AgentActivity publication, cancellation, uncertain delivery,
handoffs, the actual App Server and host permissions still need their respective
acceptance. Isolated startup required temporary writable n8n cache/state paths;
concurrent CLI/server startup exceeded the initial fixture resource envelope, so
the reproducible probe uses one server process and a bounded Node heap.

Private staged workflow files now pin the verified actor, actual credential
references and all eight current work revisions under governing version 4. Their
runtime address is explicitly provisional, PostgreSQL credential grants remain
unverified in production, and none of these four workflows has been imported or
activated there. No production SQL migration or runtime installation occurred.

## Runtime recovery and expanded engine cases

The focused runtime/n8n suites pass **47 tests**. A restarted adapter can recover
a terminal result by reading only its exact retained native thread/turn pair,
checking the workspace, and retaining a digest of the observed stored turn. Wrong
or duplicate turns, missing IDs/history, active turns and malformed context remain
uncertain. No read-only reconciliation starts or resumes a model turn. The
`thread/read` request validates against the installed 0.159.0 schema; see the
[official App Server reference](https://learn.chatgpt.com/docs/app-server).

The expanded actual n8n engine probe also passes uncertainty followed by a final
result, serialized follow-up, matching-turn cancellation, a single cancellation
result, lost publication without automatic resend and refusal of a wrong OAuth
actor. It found another engine-specific condition: an empty PostgreSQL result can
arrive as an empty item. Explicit queue guards now prevent empty dispatch/reply
processing. Uncertainty uses a thought activity and a separately frozen state
key, allowing a later confirmed terminal result to be delivered without rewriting
or resending an earlier activity. A stop request does not duplicate its target
turn's cancellation result. These are synthetic engine/runtime results, not live
Linear cancellation, native handoff or paid execution acceptance.

## Selected native capture and admission behavior — November 8

The current branch adds a project-scoped, passive Hermes history reader and the
existing-Jarvis admission/context/checkpoint workflows. The renderer produces
inactive n8n definitions; the disposable engine probe imports and exercises
them against synthetic PostgreSQL rows. The latest probe covers 16 workflow
definitions, both explicit handoff directions, exact native session/run binding,
source quiescence, echo refusal, checkpoint intake, a read-only private-history
projection and preservation of an unselected Jarvis request. It reports
`production_mounts=false`, `real_credentials=false` and `paid_model_calls=0`.

The native Hermes acceptance runs the installed reader against a synthetic
database. It confirms exact Linear-alias selection, compression lineage, rotated
native session identity, reasoning exclusion, source-byte preservation and zero
real exports or model calls. The passive importer writes only through the owned
history API queue, preserving each retained work/architecture pin and marking
admission, bridge run status and agent checkpoints as distinct evidence. It
does not infer that a run executed from admission alone, nor that assistant
completion accepted engineering work.

Native Codex source collection now reads only a registered JSONL file through a
separate credential-free App Server socket. The read is limited to one file
under the configured native root, rejects symlinks and overlarge files, and
passes the bytes through the pinned normalizer in a private temporary directory.
The native account is not given the adapter's history spool or bridge token.
Before SpecStory rendering, explicit system/developer/analysis/reasoning records
and known private instruction/reasoning fields are excluded. This remains
selected-file capture; it does not claim complete tool/media history or cover
other sessions.

The new focused reporting suite passes **28 tests**. The isolated current n8n
engine probe passes all **16 workflow imports** and its admission-refusal case
before generation, plus the Jarvis, handoff and private-reader cases listed
above. The broader legacy repository suite was attempted; its test virtualenv
lacks the pinned PyYAML dependency, and host-integration tests require installed
services/paths not available in this workspace. Those failures are not
represented as passing. No production workflow, migration, service, account,
credential or timer was installed.

The operator confirmed that the existing engineering API setup should serve the
native Codex runtime and that coding history resides on server01. This guides
the deployment package; provider authentication and unit permissions still need
model-free host acceptance before any separately authorized paid interaction.

## Server runtime package candidate — November 8

The host now has a review-only systemd candidate for the adapter, separate
credentialed coding App Server, credential-free registered-source App Server,
and passive Codex/Hermes capture timers. The adapter binds to the existing n8n
Docker bridge gateway `172.19.0.1:8766` and is limited to that bridge subnet. The
only provider secret goes through a root-only extraction helper from the
operator-approved existing `.env` variable into systemd `LoadCredential`; the
secret value was never read or printed. The Jarvis service identity is not
reused. No service users, credentials, paths, sockets, ACLs, or units were
created or changed.

The 40 focused reporting/runtime/host-candidate tests pass. `systemd-analyze
verify` on systemd 249 accepts the unit syntax and the `Accept=yes` template
relationship; expected missing-executable errors remain because the candidate
release is not installed. A broader run in the workspace sandbox passed 207
tests before its first named-UID ACL case failed under the sandbox UID mapping;
the same temporary-directory ACL test passes with the host UID mapping, and the
two tests that needed the pinned PyYAML package pass separately (**6 passed**).
No production host acceptance or activation has occurred.

## Operator-reported Codex runtime staging — November 8

The operator subsequently installed the immutable Codex runtime release at
`/opt/rras-engineering/releases/standardized-history-9e7954c07fdb`; the reported
manifest SHA-256 is
`1e8f48a1b7e22afe2e637d0a26cba7077ce58b0dfacf9384e5ce77479bfd01cf`. The
offline Python import check succeeded. The installed Codex executable reports
version `0.159.0` and matches the packaged SHA-256
`d2752c52353401f7f6efbfcea68796f4f7a3d3e4769f5d1da53fa49d4856b72f`.

The operator installed the immutable runtime release and reported creation of
the separate `rras-codex-adapter` (UID 992) and `rras-codex-native` (UID 991)
identities, plus installation/loading of candidate unit files. The existing
engineering API key was prepared at
`/etc/rras-engineering/codex-runtime/openai-api-key` (root-owned, mode 0400);
the parent config directory is root-owned by the adapter group, mode 0750. The
credential helper reported zero model starts and API calls and did not print
the secret. Candidate Codex sockets/timers remained inactive and disabled; no
Codex service or timer was started.

## Operator-reported schema-v5 history upgrade — November 8

The operator approved one root-private, same-server snapshot for the v3 → v4
history upgrade. The final quiescent snapshot was schema 3, passed SQLite
`quick_check`, and had SHA-256
`085e488b29a3cf42481f40d77dabd08820ac798175bcef250aa5b04cba4452cd`. The
owner-only reporting migration matched fingerprint
`a8f9e145bc5c9d7c4c0fc04f8e9be8983ea2a5a9956b034b638e45374605d331` and added
the reporting metadata stream while preserving 154 legacy records. The
subsequent schema-v4 evidence plan matched
`38ea9a4f930be8aee14083e4a06c90e2e640d1797c419f5951159cca69b55b65`.

After separate operator approval, the stopped schema-v4 store was snapshotted
to `/root/rras-engineering-history-migration-20261108-v5/history.sqlite3`.
That snapshot is root-private, schema 4, passed `quick_check`, and has SHA-256
`ba8f480bebb827673eebea9822c7d50ba02933f806ee039d83d5483fbb7d49f9`. The
explicit v4 → v5 migration succeeded. The operator verified schema 5, SQLite
`quick_check`, the immutable evidence tables/triggers, and service-owned mode
0700 evidence directories. No evidence chunks or capture records were seeded.

The history unit now uses the verified `standardized-history-9e7954c07fdb`
release through a systemd drop-in; the existing unit hardening remains in
place. The operator added only the `rras-codex-adapter` UID 992 grant for
`private_read=["jarvis"]` and `write=["jarvis"]`. Existing operator UID 1000
and dashboard UID 993 grants remain unchanged. The service is active. Read-only
`workspace_scopes` calls confirmed Codex sees only `jarvis`, while the
dashboard retains `jarvis` and `jarvis-non-git`; the live socket ACL retains
both existing readers and includes the adapter. No model starts or provider
API calls occurred. Codex runtime sockets and timers remain inactive; no
selected session capture has been enabled.

## Operator-reported Linear/work mapping acceptance — November 8

The operator used the scoped reporting API as `rras-codex-adapter` to append
one Linear project mapping and eight execution mappings. Each request pins the
governing architecture document
`doc_046e9a960b67530c8d00cff938cbf6f5`, version 4, SHA-256
`4ed76e0a493a5ae45bcc6154cb57fac3f1551644b1e823d5c96b1e2713365329`, plus
the current work revision and project-assignment digests. All nine submissions
returned `inserted: true`. A subsequent scoped read returned exactly nine
mapping records and verified the issue/plan/work relationships and digests.

| Reporting sequence | Linear item | Plan | Work ID |
|---:|---|---|---|
| 1 | P-REV-16 | — | — |
| 2 | REV-46 | SHRR-01 | `wrk_28f080952751501eac0180baeab700f8` |
| 3 | REV-47 | SHRR-02 | `wrk_c4889e15c1c55bab9ac8a5e0cdcf4f3f` |
| 4 | REV-48 | SHRR-03 | `wrk_14ff1467bda65b4e9f44580d422d307a` |
| 5 | REV-49 | SHRR-04 | `wrk_a144e049739e5b489ba3dfb3fe787b90` |
| 6 | REV-50 | SHRR-05 | `wrk_4cdac1cbb3a65fe4bc716b00d4004b99` |
| 7 | REV-51 | SHRR-06 | `wrk_d967fd95401b5c68ac7b3ace7354fbaa` |
| 8 | REV-52 | SHRR-07 | `wrk_a75752070f3b59949cf71c401d15ddef` |
| 9 | REV-53 | SHRR-08 | `wrk_c4f72ca05fe159c6b3ee4a98a35c14d2` |

These records add private, immutable history relationships; they did not change
Linear issues or existing work records. Codex runtime sockets/timers remain
inactive. No session capture, model call or artifact export was started.

## Production reporting and browser check — November 9

The new n8n workflows were activated after the CLI-imported webhook registration
IDs were fixed and independently tested. All nine protected routes rejected
unauthenticated requests, and the two scoped history readers and selected Linear
reader responded successfully. The existing Jarvis workflow's unrelated
versions were preserved. The first collector timer pass exposed lock contention;
the collectors were changed to serialize and the simultaneous service test and
later scheduled passes succeeded. A Linear document exceeded the original 64 KiB
observation limit; its redacted full snapshot is now retained as chunked evidence
with a bounded observation referencing it. A subsequent production poll completed
with no pending deliveries.

The reporting dashboard release `history-web-34e127b311a2` was activated without
restarting the history service or changing its configuration or policy. The
operator confirmed that the project Overview and History tabs, Linear mappings,
reporting records, and the large-document evidence preview worked in the
authenticated browser. This does not establish the separate live Codex agent,
curated-publication, automatic session-capture, or project-closeout acceptance.
No coding model was started in these checks.

## Curated publication and bridge boot persistence — November 9

The operator approved the reviewed project-specific structured-field profile and
its initial 17 records. The installed catalog reader reported successful actual
Hermes MCP search and exact entry read; all three pre-existing curated entries
remained visible. The approved profile excludes transcript bytes and raw Linear
snapshots. This verifies the initial publication, not automatic publication of
future checkpoints or a complete archive.

The runtime bridge and its two sockets were active but disabled at boot. A
root-installed systemd drop-in now orders the bridge after Docker and enables
it together with the sockets. The existing process remained running and an
unauthenticated bridge request was denied. The coding execution policy remains
false; the capture timer remains disabled. Boot enablement is verified through
systemd state, not a full server reboot test. Actual native mention, delegation,
follow-up, cancellation and two-way handoff remain separate live acceptance work.

## n8n no-retention execution records — November 9

The deployment idle check treated soft-deleted `running` rows as active and
refused to restart n8n. A selected authenticated reader returned HTTP 200, yet
its corresponding execution row remained marked running with `deletedAt` set.
An isolated n8n 2.28.3 fixture using the same no-retention reader settings
reproduced that combination. Existing workflows retain their privacy settings;
the corrected idle check excludes soft-deleted rows while still blocking on
non-deleted active executions and nonterminal Hermes runs. A separate reader
endpoint initially returned 404; after the operator-approved backup and n8n
restart, protected endpoints and selected readers passed their checks. This
does not establish that every individual old execution succeeded, and no old
records were manually deleted.
