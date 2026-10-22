# Reusable operator control

`operator_control.py` connects repository admission candidates to the existing
protected review, one-use approval and fixed-slot launcher. The protected command is installed as `/usr/local/sbin/rras-workflow`; installation is not permission to execute a task. No paid execution is necessary to test control boundaries. Existing preparation stdio remains preparation-only.

## Authority and live configuration

An administrator deliberately installs/selects one root-owned configuration per
repository. All its ancestors must be root-owned, free of symlinks and not writable
by group/others. Its required fields are:

- `schema_version`: integer1.
- `registration`: the full reviewed shared-contract repository registration.
- `hermes_project`: a bounded project slug, used in the isolated native worker home.
- `profile`: absolute path to the protected reviewed engineering profile.
- `codex_config`: absolute path to the protected reviewed base Codex configuration.
- Optional `journal`: absolute protected initialized journal directory. Required by
  the installed managed workflow packaging; omission retains the
  earlier source-only compatibility interface. See [managed recording](managed-journal-and-reader.md).

The protected configuration, not an actor/provenance field or a candidate-supplied
policy, establishes live admission. Paths/recipes are operator-reviewed configuration;
registration recipes must never run as root. The launcher continues to run the
validation argv under UID996. The translator currently supports SHA-1 Git repositories
and exact file scopes; broader formats/scopes need explicit support.

Capture reconstructs the candidate against this live registration and project and
requires byte-equivalent deterministic translation. It checks clean canonical Git,
exact named baseline, safe file paths and assigned review-branch prefix. It captures
the work, registration/configuration digests, session hashes and fixed control-code/
schema hashes into a root-private review. It does not claim the candidate came from
Hermes: `proposal_source` is `operator_admission_candidate`. Claimed actors remain
passive provenance, not authenticated identities. The OS root invocation is the
operator trust boundary; there is no remote or chat approval endpoint.

Editing a mutable candidate after capture cannot alter the protected review.
Changing live configuration (including registration, project, session selection or
formatting), session bytes, control code/schema or the selected baseline invalidates
that review. Approval repeats these checks; the underlying launcher repeats admission
checks after slot inspection and immediately before exclusive consumption. The exact
snapshot is cloned, regardless of which branch is checked out in canonical Git.
Configuration updates and canonical Git administration should be serialized with
operator actions; this is not a distributed lock over human Git/configuration writes.

## Commands

Use `--help` in the checkout to inspect arguments. Privileged operations deliberately
refuse this user-writable source checkout. The commands below describe the protected installed interface; do not copy source into root paths or run a paid launch as a source acceptance shortcut. See the [runbook](workflow-operator-runbook.md) for the full lifecycle and [closeout](workflow-phase-closeout.md) for actual host evidence.

1. `prepare --registration FILE --work-item FILE --hermes-project SLUG --state PROPOSALS`
   is the unprivileged [admission preparation](repository-admission.md) interface.
   Its result is a candidate ID, with no execution/publication authority.
2. `capture --config FILE --proposals PROPOSALS --candidate-id SHA256 --state CONTROL --review-branch codex/SLUG`
   creates an immutable root-private review and returns its digest. CONTROL must
   already exist with root-owned protected ancestors and mode0700.
3. `review --config FILE --state CONTROL --review-id SHA256` shows the private bounded
   request/objective/validation argv, baseline, branch and identity hashes. Review the
   actual deliverables and validation limits; this view is not deliverable acceptance.
4. `approve --config FILE --state CONTROL --review-id SHA256 --approve-one-execution`
   records an explicit root-operator approval and returns a one-use authorization ID.
   It never authorizes publication, merge or deployment.
5. `launch --config FILE --state CONTROL --authorization-id UUID32 --jobs JOBS --workers WORKERS --credential FILE`
   is the only service/model-capable command. It retains the existing protected
   job/credential checks, dedicated UID996, global `rras-coding-task.service` slot,
   busy-UID exclusion, exact worker clone, systemd credential delivery and no-retry
   consumption. Credentials are delivered by systemd; the operator interface never
   reads their bytes. Actual invocation requires its own task/spending approval.
6. `evidence --state CONTROL --authorization-id UUID32` reads a bounded operator
   summary even after configuration revocation. It reports approved-not-consumed,
   consumed-outcome-unknown, launch-recorded or service-returned, plus available exit/
   host-stop facts. It verifies record associations and refuses inconsistent chains.
   It omits private logs, credential/session contents and job/work paths.

Evidence states do not establish a model call, verified task success, human acceptance,
publication or release. An ambiguous client failure retains consumption/launch records
and exclusion. Do not retry or delete fences. Cancellation and recovery mutation
remain deferred. A direct older launcher invocation still checks the admission binding
when present; legacy Hermes receipt reviews retain their existing contract.

## Validation and remaining work

Source tests use real disposable Git repositories and protected-record shapes with
explicit fixture-only ownership adapters, fake account/service-manager responses and
harmless credential files. No production worker, provider request or recipe is run.
They prove deterministic admission-to-clone plumbing and refusal ordering, not actual
root/UID996/systemd isolation. Repeat changed boundaries with isolated model-free host
fixtures before installing or exposing this interface.

The [journal foundation](workflow-journal.md) and [managed adapter/reader](managed-journal-and-reader.md)
now provide source storage, explicit interactive imports, control-event recording,
receipt reconciliation and projection-only MCP reads. Those storage, mount and host boundaries have been installed and accepted for the current release; future upgrades retain separate review/installation gates. This command's evidence readback is
not a universal task journal or proof of native success. Native finish/custody and publication/PR receipts are now installed and exercised. Cancellation/recovery mutation, GUI/autopilot and ledger activation remain separately tracked on the [roadmap](workflow-roadmap.md).
