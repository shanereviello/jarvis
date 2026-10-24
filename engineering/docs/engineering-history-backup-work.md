# Engineering history backup work in progress

PR48 actual hardened-unit acceptance passed and source was merged. Production
history remains uninstalled. The operator selected an existing public encryption
key; its public bytes/type and independently verified fingerprint remain needed.
Never request or install its private key on the server.

The initial snapshot primitive uses SQLite's online backup API through a read-only
source connection. It retains documents, receipts and outbox in one database
snapshot, refuses overwrites and unsafe private paths, bounds size/time, checks
SQLite integrity/schema and writes a digest manifest. Failed private staging stays
available for inspection. Plaintext staging is explicitly not an encrypted backup
and cannot satisfy the production gate.

Still required before production retention:

- Package the snapshot with pinned grants, schema, templates and runtime metadata;
  state the consistency boundary between database and deployment configuration.
- Select encryption adapter compatible with the supplied public key; verify exact
  recipient fingerprint, encrypt without private keys and refuse plaintext output.
- Verify tamper/wrong-recipient/truncation refusal and isolated decryption/restore
  with operator-held private key, exact document/receipt checks and no action route.
- Decide local/off-host custody, retention and recovery expectations explicitly.
- Obtain separate inactive installation and live activation decisions.

This work does not back up the root operational journal, offer production restore,
create a listener, capture Codex conversations automatically or authorize execution.
