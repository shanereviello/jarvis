# Operator review-document intake commands

`engineering/tools/rras_history/review_document_cli.py` provides repository-independent
`inspect`, `prepare`, `status`, `apply` and `resume` commands for the existing exact
private review-document receiver. This is source tooling, not a globally installed
command or an automatic lifecycle hook. Run it with the validated Python environment
and its pinned schema dependencies. A source merge does not install it.

## Prepare and review

The root producer establishes original capture custody and transfers a private
packet to the selected operator. The client does not read root state or accept an
execution approval token. Keep packet/state directories private and out of Git.

```sh
python engineering/tools/rras_history/review_document_cli.py inspect --packet /absolute/private/packet.json
python engineering/tools/rras_history/review_document_cli.py prepare --state /absolute/private/intake --packet /absolute/private/packet.json --packet-sha256 REVIEWED_PACKET_SHA256 --socket /run/rras-engineering-history/service.sock --service-uid 995
python engineering/tools/rras_history/review_document_cli.py status --state /absolute/private/intake
```

Inspect validates the packet, regenerates exact Markdown/manifest and reports its
identity and digests without disclosing the full narrative. Review the Markdown
through the private producer handoff before approving intake. Prepare freezes the
packet, reviewed hash, endpoint, authenticated service UID and caller UID in new
private state. It makes no service request. Status validates the frozen input and
reports whether receipt/completion files were saved; these flags are local state,
not a fresh service readback or proof of task success.

The exact current engineering work revision must already exist. Explicit work
creation/revision stays with the existing history client and its durable spool.
This receiver never silently creates work. A `work.create` receipt describes the
work-body digest and source provenance; it must not be passed to the imported
checkpoint/document receipt checker. The document remains imported even when the
engineering work proposal was agent-reported.

## Approve one document and recover

```sh
python engineering/tools/rras_history/review_document_cli.py apply --state /absolute/private/intake --packet-sha256 REVIEWED_PACKET_SHA256 --approve-private-document
```

Apply requires the exact frozen packet digest and an explicit approval flag before
contacting the service. The service independently enforces repository permissions;
this client adds no grants. The receiver checks the current work head, acquires its
exclusive lock, submits only the frozen document, validates the authenticated
receipt and reads back exact stored Markdown/manifest before recording completion.

If interrupted, preserve the entire private state. Inspect status and diagnose the
failure before an explicit resume:

```sh
python engineering/tools/rras_history/review_document_cli.py resume --state /absolute/private/intake --packet-sha256 REVIEWED_PACKET_SHA256 --approve-private-document
```

A lost response after commit reuses the same frozen idempotency key and receives
the original receipt. A saved receipt avoids resubmission; readback can then finish.
Completed delivery rechecks the work head and stored document without a new
submission. A changed work head requires review; resume cannot revise it. Prepare
refuses an existing state directory, including incomplete setup; preserve it for
diagnosis rather than deleting it or automatically replaying the import.

No command calls a provider, starts a worker, merges Git, deploys, changes service
configuration or promotes imported content into observed/human authority. Trusted
root export orchestration, production installation, automatic managed triggers,
interactive session hooks, curated Jarvis narrative access and a GUI remain separate.
