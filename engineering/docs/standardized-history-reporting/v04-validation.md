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
engine probe passes its admission-refusal case before generation and all Jarvis,
handoff and private-reader cases listed above. The broad legacy repository suite
was also attempted, but its test virtualenv lacks the pinned PyYAML dependency
and host-integration tests rely on installed services/paths unavailable in this
workspace sandbox; those failures are not represented as passing. No production
workflow, migration, service, account, credential or timer was installed.

The operator confirmed that the existing engineering API setup should serve the
native Codex runtime and that coding history resides on server01. This guides
the deployment package; provider authentication and unit permissions still need
model-free host acceptance before any separately authorized paid interaction.
