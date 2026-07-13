# n8n + MCP Integration

This branch is now MCP-first.

The old FastAPI endpoint layer is gone. Jarvis now exposes reusable Python services through an MCP server so you can keep adding tools without rebuilding the stack around one-off HTTP routes.

## Architecture

The codebase is now split by responsibility:

```text
app/
  core/
    config.py
  resources/
    engineering_db_schema.py
  prompts/
    engineering_db_query_planner.py
  services/
    engineering_db.py
    notes.py
  schemas/
    engineering_db.py
    notes.py
  tools/
    retrieve_engineering_db_schema_context.py
    engineering_db_lookup.py
    read_note.py
  servers/
    mcp/
      registry.py
      server.py
      smoke_test.py
```

## Mental model

Think of the stack in four layers:

1. `services/`
   This is the real business logic. It talks to Postgres and the vault.
2. `resources/`, `prompts/`, and `tools/`
   This is the MCP surface. It decides what the AI can read, what workflow hints it can use, and what actions it can call.
3. `servers/mcp/registry.py`
   This is the wiring file. It registers everything with the MCP server.
4. `servers/mcp/server.py`
   This starts the actual MCP server process.

If you remember only one thing, make it this:

- `services` do the work
- `tools/resources/prompts` expose that work to the model
- `registry` plugs them together
- `server` runs it

Why this shape:

- `core/`: shared runtime configuration
- `resources/`: read-only MCP schema context for the model
- `prompts/`: reusable MCP planning workflows
- `services/`: reusable domain logic such as database and vault access
- `schemas/`: consistent result objects shared by services and tools
- `tools/`: MCP-facing tool registrations
- `servers/mcp/`: server startup and tool registry wiring

This keeps the protocol layer thin and makes future growth easier. Adding a new tool should mostly mean:

1. add or expand a service
2. add a schema if needed
3. add a tool wrapper
4. register the tool in `app/servers/mcp/registry.py`

## Folder-by-folder

- [app/core/config.py](/Users/shanereviello/jarvis/app/core/config.py:1)
  Loads environment variables like DB credentials, vault root, and MCP host/port settings.

- [app/services/engineering_db.py](/Users/shanereviello/jarvis/app/services/engineering_db.py:1)
  Owns engineering DB work:
  - introspect schema
  - rank relevant tables for a query
  - run scoped DB lookups

- [app/services/notes.py](/Users/shanereviello/jarvis/app/services/notes.py:1)
  Owns note-file access under `JARVIS_VAULT_ROOT`.

- [app/schemas/engineering_db.py](/Users/shanereviello/jarvis/app/schemas/engineering_db.py:1)
  Defines the Python result shapes for schema info, lookup matches, and engineering DB records.

- [app/schemas/notes.py](/Users/shanereviello/jarvis/app/schemas/notes.py:1)
  Defines the note-read result shape.

- [app/resources/engineering_db_schema.py](/Users/shanereviello/jarvis/app/resources/engineering_db_schema.py:1)
  Exposes engineering DB schema data as read-only MCP resources.

- [app/prompts/engineering_db_query_planner.py](/Users/shanereviello/jarvis/app/prompts/engineering_db_query_planner.py:1)
  Exposes a reusable MCP prompt that nudges the model to narrow the DB schema first.

- [app/tools/retrieve_engineering_db_schema_context.py](/Users/shanereviello/jarvis/app/tools/retrieve_engineering_db_schema_context.py:1)
  Tool wrapper for engineering DB table-selection guidance.

- [app/tools/engineering_db_lookup.py](/Users/shanereviello/jarvis/app/tools/engineering_db_lookup.py:1)
  Tool wrapper for structured engineering DB retrieval.

- [app/tools/read_note.py](/Users/shanereviello/jarvis/app/tools/read_note.py:1)
  Tool wrapper for reading the final note file.

- [app/servers/mcp/registry.py](/Users/shanereviello/jarvis/app/servers/mcp/registry.py:1)
  Registers all resources, prompts, and tools onto one MCP server.

- [app/servers/mcp/server.py](/Users/shanereviello/jarvis/app/servers/mcp/server.py:1)
  Creates and runs the `FastMCP` server.

- [app/servers/mcp/smoke_test.py](/Users/shanereviello/jarvis/app/servers/mcp/smoke_test.py:1)
  Local inspection helper for listing and invoking MCP primitives.

## Current MCP capabilities

- Resources:
  - `engineering-db://schema/catalog`
  - `engineering-db://schema/relationships`
  - `engineering-db://schema/table/{table_name}`
- Prompt:
  - `engineering-db-query-planner`
- Tools:
  - `retrieve-engineering-db-schema-context`
  - `engineering-db-lookup`
- `read-note`: read a note file from the configured vault root

## Request Flow

When a user asks something like:

`What does the note for XT60 connector say?`

the intended flow is:

1. The MCP client connects to [app/servers/mcp/server.py](/Users/shanereviello/jarvis/app/servers/mcp/server.py:1).
2. The server exposes what is registered in [app/servers/mcp/registry.py](/Users/shanereviello/jarvis/app/servers/mcp/registry.py:1).
3. The model narrows the database space first:
   - read `engineering-db://schema/catalog`, or
   - call `retrieve-engineering-db-schema-context`
4. The model then calls `engineering-db-lookup` with likely tables.
5. The DB result may include a `notes_path`.
6. If the user needs the actual note contents, the model calls `read-note`.
7. `read-note` loads the file from the vault and returns the text.
8. The model answers using the note content.

So the practical chain is:

`user question -> DB schema narrowing -> engineering DB lookup -> note path -> note read -> final answer`

## Environment

This repo includes:

- [Dockerfile](/Users/shanereviello/jarvis/Dockerfile)
- [docker-compose.yml](/Users/shanereviello/jarvis/docker-compose.yml)
- [.env.docker.example](/Users/shanereviello/jarvis/.env.docker.example)

Important environment values:

- `JARVIS_VAULT_ROOT`: absolute path to the mounted note vault
- `DB_*`: PostgreSQL connection settings
- `DB_SCHEMA`: defaults to `public`
- `MCP_TRANSPORT`: defaults to `streamable-http`
- `MCP_HOST`: defaults to `0.0.0.0`
- `MCP_PORT`: defaults to `8000`
- `MCP_STREAMABLE_HTTP_PATH`: defaults to `/mcp`

`read-note` is restricted to files under `JARVIS_VAULT_ROOT`. Paths outside that root are rejected.

## Docker setup

### First-time setup

1. Copy `.env.docker.example` to `.env.docker`
2. Set the real database password
3. Verify `JARVIS_VAULT_ROOT`
4. Make sure the host path `/mnt/nas/engineering_vault` exists on the Pi
5. Make sure the Docker volume `n8n_data` already exists

### Start the stack

```bash
docker compose up -d --build
```

### Stop the stack

```bash
docker compose down
```

### If you already started n8n with `docker run`

```bash
docker stop n8n
docker rm n8n
```

## Runtime model

The MCP container is now named `jarvis-mcp`.

Docker is the source of truth for this runtime. The old host venv is not the primary execution path for this branch.

Inside Docker Compose, the server is reachable at:

`http://jarvis-mcp:8000/mcp`

From the Pi host or another machine on your LAN, it is usually:

`http://192.168.0.200:8001/mcp`

The exact endpoint path is controlled by `MCP_STREAMABLE_HTTP_PATH`.

## Docker verification

List the registered MCP tools inside the running MCP container:

```bash
docker compose exec jarvis-mcp python -m app.servers.mcp.smoke_test --list-tools
```

List resources and resource templates:

```bash
docker compose exec jarvis-mcp python -m app.servers.mcp.smoke_test --list-resources
```

List prompts:

```bash
docker compose exec jarvis-mcp python -m app.servers.mcp.smoke_test --list-prompts
```

Read the schema catalog resource:

```bash
docker compose exec jarvis-mcp python -m app.servers.mcp.smoke_test --read-resource engineering-db://schema/catalog
```

Render the planning prompt:

```bash
docker compose exec jarvis-mcp python -m app.servers.mcp.smoke_test --prompt engineering-db-query-planner --args-json '{"user_query":"find 18awg silicone wire"}'
```

Call `retrieve-engineering-db-schema-context` directly:

```bash
docker compose exec jarvis-mcp python -m app.servers.mcp.smoke_test --tool retrieve-engineering-db-schema-context --args-json '{"query":"find 18awg silicone wire"}'
```

Call `engineering-db-lookup` directly without starting Docker:

```bash
docker compose exec jarvis-mcp python -m app.servers.mcp.smoke_test --tool engineering-db-lookup --args-json '{"query":"find 18awg silicone wire","candidate_tables":["wires","cables"]}'
```

Call `read-note` directly:

```bash
docker compose exec jarvis-mcp python -m app.servers.mcp.smoke_test --tool read-note --args-json '{"notes_path":"components/compute/RPI4B.md"}'
```

View container logs:

```bash
docker compose logs jarvis-mcp
docker compose logs n8n
```

## Optional host-only verification

If you intentionally want to test outside Docker, activate the environment you trust first and then run:

```bash
python -m app.servers.mcp.smoke_test --list-tools
```

This is optional developer convenience only. It is not the main runtime path for this branch.

## n8n integration direction

n8n should now consume Jarvis through an MCP client flow instead of raw REST `HTTP Request` nodes aimed at custom `/tools/...` endpoints.

That means the conceptual workflow changes from:

1. call hand-written HTTP endpoint
2. parse custom JSON response
3. call another endpoint

to a schema-aware MCP RAG flow:

1. connect to the Jarvis MCP server
2. inspect schema resources or render the planning prompt
3. invoke `retrieve-engineering-db-schema-context`
4. invoke `engineering-db-lookup` with narrowed tables
5. optionally invoke `read-note`
6. format the final answer in n8n

This keeps Jarvis focused on reusable capabilities while n8n stays responsible for orchestration, approvals, scheduling, and branching.

## How to add the next tool

Example expansion path:

1. create or extend a module in `app/services/`
2. define a stable return shape in `app/schemas/`
3. decide whether it should surface as a resource, prompt, tool, or some combination
4. register it in [app/servers/mcp/registry.py](/Users/shanereviello/jarvis/app/servers/mcp/registry.py:1)
5. verify it with [app/servers/mcp/smoke_test.py](/Users/shanereviello/jarvis/app/servers/mcp/smoke_test.py:1)

That pattern is the main reason for the restructure. It gives you a place for each concern now, and it keeps future tables, schema helpers, and tool groups from turning into one large file later.
