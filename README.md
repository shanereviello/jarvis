# Jarvis tooling source

Human-controlled source for MCP/Linear tools, the activity ledger, and native RRAS engineering integration. Installed deployments are separate from this checkout.

- `app`, `scripts`, `tests`: existing MCP application, with deployed Linear changes preserved.
- `deploy/mcp/compose.yml`: current MCP/Linear deployment source; build context points at the repository root.
- `deploy/hermes/compose.yaml`: assistant deployment source.
- `activity-ledger`: ledger source, schemas and adapter compatibility tests.
- `engineering`: native task runner, acceptance utilities and operator guides.

These are migration review sources, not cutover-ready commands. Existing service mounts and credentials still use original locations; no production release is selected. Preserve Docker project identities and data volumes during the separately reviewed cutover. Never run migration/cleanup profiles as part of source import.

Secrets, .env, personal auth, databases, execution copies, caches and installed third-party binaries are not source. Coding tasks operate on worker-owned execution copies; merges into this canonical repository and deployment remain human-controlled.
