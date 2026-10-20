# Independent post-validation contract

The worker's captured validation report and the observed native board remain
separate from an independently executed mechanical check. `post_validation.py`
defines inert plans, isolated service arguments and host-result classification.
It does not execute a service, authenticate caller-supplied data, record a journal
event or gate existing publication. No deployed behavior changes in this slice.

The plan recompiles the captured registration/work item and requires the exact
reviewed request, recipe, timeout, repository, task, branch and baseline. It binds
the review commit, export digest and protected finish receipt digest. This is
repository-independent; it adds no Jarvis-specific command or new execution
identity. Registered recipe arguments containing `$` or `%` are currently refused
by the systemd renderer to avoid variable/specifier expansion. Supporting those
literals requires a separately tested invocation wrapper.

The eventual host must reconstruct a fresh workspace from protected captured
changes, verify its content against the review commit's tree and keep HEAD at the
baseline with proposed changes **unstaged**. A clean checkout of the review commit
would make the current `git diff --check` recipe vacuous. Full-tree comparisons
must include untracked additions, deletions and modes, without trusting the
worker's index or Git configuration. The source preparation path already enforces
scope and rejects special entry changes; staging must preserve those checks.

The renderer reuses `rras-coding-task.service`, UID/GID996 and existing resource
bounds. It supplies no credential, clears inherited environment, uses a private
network namespace, makes the filesystem read-only except the dedicated validation
workspace and private temporary directory, and hides workflow/credential/job
roots. Repository checks run as the engineering worker, never root. These are
proposed properties requiring real host acceptance, not a new isolation claim.

Only host observations tied to the exact plan digest can describe an independent
mechanical check: an exit code, globally verified stopped identity/slot, and the
expected review tree before and after. Missing facts or changed files remain
uncertain, including after exit zero. A completed failed check remains failed;
no classifier result grants a retry, publication, human acceptance or task success.
The classifier itself does not authenticate observations supplied by its caller.

Remaining implementation before this is usable:

1. Protected host custody reader, fresh workspace reconstruction and actual tree
   verification; authenticate/rebuild the plan before using rendered arguments.
2. Root-owned exclusive one-use fence before invocation; fixed-slot acquisition,
   bounded private output, interrupted/timeout handling and stop verification.
   Existing coding launches and checks must remain mutually exclusive. Never
   remove a fence or rerun a check merely to repair missing journal events.
3. Durable root-owned result custody, idempotent observed validation journal
   recording and publication enforcement tied to the exact reviewed tree/commit.
4. Model-free root/UID996/systemd acceptance, dependency packaging and upgrade
   handling that preserve the current journal/configuration; separate deployment.

The current renderer has no production command and must not be called directly
with model-supplied plans or arbitrary workspaces. Fixtures prove the contract and
argument construction only; no production unit, real credential or API is used.
