# Scoped native Jarvis reporting

The source plugin adds only `engineering_checkpoint` and `engineering_handoff`
in the `engineering_reporting` toolset. It does not add repository, terminal,
filesystem, execution, approval or private archive tools. Existing Linear actions
remain on their current transport and app identity. The plugin wrapper loads a
reviewed, read-only release and a bounded root-controlled configuration.

The inspected native task-local API context supplies the actual Hermes run and
`linear:<organization>:<session>` alias. Agent arguments cannot supply those
identities, select work or change scope. Process environment variables are not
accepted as a substitute for a bound context. The context implementation is
pinned; incompatible native source refuses the adapter until reviewed.

The bounded existing-Jarvis workflow patch retains an immutable link between an
admitted delivery and the actual returned Hermes run. A private n8n lookup resolves
that exact run to its retained issue/work/architecture binding and incoming
handoff chain. Late passive delivery can resolve a completed run; it never starts
or resumes it. Unrelated runs do not resolve through the selected endpoint.

Tool reports are redacted before entering a private immutable queue. Their IDs
include the actual run, operation and stable key. Passive delivery resolves the
retained context and submits either a typed checkpoint to n8n or a prepared Jarvis
handoff to the existing native transport. Missing context or acknowledgments
leave the original request pending. Retries do not launch another assistant run.
The native account holds no Linear OAuth credential or owned-history grant.

The additional SQL tables retain engineering admissions, run bindings and
checkpoint transport records. Prior Jarvis rows and credentials remain intact.
The checkpoint function checks the actual run/session, fixed agent attribution and
retained work/design pins. Changed replay is refused. A 10,000-record checkpoint
transport limit stops intake while preserving existing records. The implementation
uses PostgreSQL's built-in SHA-256 and needs no new pgcrypto extension.

Sixteen inactive workflow definitions pass actual isolated n8n 2.28.3/PostgreSQL 18
acceptance. The fixture exercises exact run lookup, refusal of another session,
scoped checkpoint admission, both handoff directions, agent-echo refusal and
preserved unselected Jarvis behavior. Its Hermes HTTP endpoint is synthetic.
Separate installed-native tests cover context bindings and read-only capture;
registration/source tests cover the two narrow tool schemas and passive replay.
These checks use no real credentials, real session exports or model turns.

The passive owned-history lifecycle/checkpoint importer, selected capture
installation, native plugin installation/toolset acceptance and privileged host
packaging remain build work. No plugin, workflow, migration, grant, timer or
service has been activated by these sources.
