# n8n Integration

This repo now exposes a tool-oriented FastAPI surface so n8n can orchestrate Jarvis without owning the Python implementation details.

This branch is intentionally n8n-first:

- no Python `agent.py`
- no local CLI chat loop
- no FastAPI full-agent endpoint
- only tool endpoints for n8n to call

## Docker setup

This repo includes:

- [Dockerfile](/Users/shanereviello/jarvis/Dockerfile)
- [docker-compose.yml](/Users/shanereviello/jarvis/docker-compose.yml)
- [.env.docker.example](/Users/shanereviello/jarvis/.env.docker.example)

### Why a separate Docker env file

Your existing local `.env` uses `DB_HOST=localhost`, which works only when Python runs on the same machine as the database.

For this setup, your PostgreSQL database lives on your server at:

`192.168.0.231`

So the containerized API should use:

`DB_HOST=192.168.0.231`

not `localhost`.

### First-time setup

1. Copy `.env.docker.example` to `.env.docker`
2. Set the real database password and verify `PROJECT_PATH`
3. Make sure the host path `/mnt/nas/engineering_vault` exists on the Pi
4. Make sure the Docker volume `n8n_data` already exists

### Start the stack

```bash
docker compose up -d --build
```

### Stop the stack

```bash
docker compose down
```

### If you already started n8n with `docker run`

Stop and remove that standalone container first so the compose-managed `n8n` container can reuse the same name and port:

```bash
docker stop n8n
docker rm n8n
```

### Verify the API after startup

Health check:

```bash
curl http://localhost:8000/ping
```

List available tools:

```bash
curl http://localhost:8000/tools
```

Search components:

```bash
curl -X POST http://localhost:8000/tools/search-components \
  -H "Content-Type: application/json" \
  -d '{"query":"raspberry pi"}'
```

Read a note:

```bash
curl -X POST http://localhost:8000/tools/read-note \
  -H "Content-Type: application/json" \
  -d '{"notes_path":"components/compute/rpi5.md"}'
```

View container logs if something looks off:

```bash
docker compose logs jarvis-api
docker compose logs n8n
```

## Endpoints

### Health check

`GET /ping`

Example response:

```json
{
  "answer": "Jarvis n8n tool API is reachable.",
  "n8n_ready": true
}
```

### Tool discovery

`GET /tools`

Example response:

```json
{
  "tools": [
    {
      "name": "search-components",
      "method": "POST",
      "path": "/tools/search-components",
      "body": {
        "query": "raspberry pi"
      }
    },
    {
      "name": "read-note",
      "method": "POST",
      "path": "/tools/read-note",
      "body": {
        "notes_path": "notes/example.md"
      }
    }
  ]
}
```

### Search components

`POST /tools/search-components`

Request body:

```json
{
  "query": "raspberry pi"
}
```

Success response:

```json
{
  "ok": true,
  "query": "raspberry pi",
  "count": 1,
  "results": [
    {
      "component_name": "Raspberry Pi 5",
      "notes_path": "components/compute/rpi5.md",
      "match_score": 0.913
    }
  ]
}
```

### Read note

`POST /tools/read-note`

Request body:

```json
{
  "notes_path": "components/compute/rpi5.md"
}
```

Success response:

```json
{
  "ok": true,
  "notes_path": "components/compute/rpi5.md",
  "content": "..."
}
```

## Recommended n8n setup

### n8n orchestrates the tool API directly

Use:

1. `Webhook` or `Chat Trigger`
2. `HTTP Request` to `/tools/search-components`
3. Optional branch:
   if the first result includes `notes_path`, call `/tools/read-note`
4. `Set` or `Code` node to format the final answer

This is the intended shape for this branch.

## Example HTTP Request node config

Base URL inside Docker Compose will usually be:

`http://jarvis-api:8000`

Search components:

- Method: `POST`
- URL: `http://jarvis-api:8000/tools/search-components`
- Send Body: `true`
- Body Content Type: `JSON`
- Body:

```json
{
  "query": "={{ $json.query }}"
}
```

Read note:

- Method: `POST`
- URL: `http://jarvis-api:8000/tools/read-note`
- Send Body: `true`
- Body Content Type: `JSON`
- Body:

```json
{
  "notes_path": "={{ $json.results[0].notes_path }}"
}
```

## Long-term architecture

- `n8n`: orchestration, triggers, approvals, scheduling, branching
- `FastAPI`: custom tools, database access, file access, local Python logic
- Python code here stays focused on tool implementation only
