# apex-mcp-server

This repo is a small FastMCP baseline for a private persona-profile server. It exposes a tiny MCP surface with profile tools, simple tabular user-data tools, one resource, one prompt, and one auth-debugging tool.

The goal is to keep the proof of concept easy to understand and easy to reuse for future MCP servers. The server runs against one Postgres database in every environment, with Docker Compose for local development and a generic `DATABASE_URL` for Vercel, VMs, or other remote deployments.

## Key Features / Scope

- Uses FastMCP with Streamable HTTP at `/mcp`.
- Supports `get_profile`, `set_profile`, `get_user_data`, `set_user_data`, and `whoami` MCP tools.
- Exposes `profile://me` as a `text/markdown` MCP resource.
- Exposes `use_profile(task: str)` as a simple MCP prompt.
- Stores one Postgres row per caller with:
  - `profile_markdown`
  - `weight_kg`
  - `height_cm`
  - `ftp_watts`
- Supports three auth modes:
  - `none` for quick local experiments
  - `bearer` for protected local or direct-client use
  - `oauth` for `claude.ai` production connections through WorkOS AuthKit
- Supports two local workflows:
  - Postgres in Docker + app on the host with `uv`
  - app and Postgres together in Docker Compose
- Does not include an ORM, Alembic migrations, multi-user admin workflows, or local OAuth login flows.

## Setup

### 1. Install `uv`

Choose the installation method you prefer from the official uv docs. A common macOS setup is:

```bash
brew install uv
```

### 2. Create the virtual environment

```bash
uv venv
```

### 3. Sync dependencies

```bash
uv sync
```

### 4. Create a local env file

Copy the example file and keep your local values there:

```bash
cp .env.example .env.local
```

### 5. Optional: use the Makefile helpers

If you prefer short local commands, this repo also includes a small `Makefile`:

```bash
make help
```

## How To Run

### Fastest local workflow: Postgres in Docker, app on the host

Start the local database:

```bash
make db-up
```

Then run the MCP server on the host without auth:

```bash
make run
```

Or run it with bearer-token auth:

```bash
make run-private MCP_API_TOKEN=dev-secret-token
```

The MCP endpoint will be available at:

```text
http://127.0.0.1:8000/mcp
```

### Full Docker Compose workflow

Build and start the app and database together:

```bash
make docker-up
```

Stop the stack when you are done:

```bash
make docker-down
```

### Direct `uv` commands

If you prefer raw commands instead of `make`, export a database URL first, then run `uvicorn`:

```bash
export DATABASE_URL=postgresql://apex:apex@127.0.0.1:54329/apex_mcp_server
uv run uvicorn index:app --reload
```

### Tests

```bash
make test
```

Or:

```bash
uv run pytest
```

`make test` starts the local Postgres container automatically when Docker is available. If Docker is not running, the in-process tests still run and the Postgres integration tests are skipped.

### Lint

```bash
make lint
```

Or:

```bash
uv run ruff check .
```

## Configuration

### Required database setting

This baseline always uses Postgres, so `DATABASE_URL` is required:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
```

### Local defaults

The committed `.env.example` uses these defaults for Docker Compose:

```text
POSTGRES_DB=apex_mcp_server
POSTGRES_USER=apex
POSTGRES_PASSWORD=apex
POSTGRES_PORT=54329
DATABASE_URL=postgresql://apex:apex@127.0.0.1:54329/apex_mcp_server
MCP_AUTH_MODE=none
```

### Environment variables

Primary runtime variables:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
MCP_AUTH_MODE=none|bearer|oauth
MCP_API_TOKEN=your-shared-token
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
MCP_SERVER_NAME=APEX FastMCP Profile Pilot
MCP_SERVER_VERSION=0.1.0
```

### Vercel production setup

For a Claude-facing OAuth deployment, set at least:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
```

For the full manual Vercel deployment and remote testing guide, see [docs/vercel-deploy.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-deploy.md).
For the reusable end-to-end guide you can apply to future MCP servers, including manual Vercel upload, WorkOS setup, and Claude connector setup, see [docs/remote-mcp-from-scratch-guide.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/remote-mcp-from-scratch-guide.md).

### Client connection notes

For local bearer-token mode, any MCP client that can send a bearer token can use this server.

Codex example:

```toml
[mcp_servers.apex_profile]
url = "https://your-server.vercel.app/mcp"
bearer_token_env_var = "MCP_API_TOKEN"
```

Generic HTTP requirement:

```text
Authorization: Bearer <your-shared-token>
```

For `claude.ai` production use, prefer the OAuth setup documented in [docs/vercel-deploy.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-deploy.md) instead of bearer-token auth.

### MCP Inspector setup

If you connect with MCP Inspector in bearer-token mode, use a custom header instead of the OAuth form.

1. Set the MCP server URL to your `/mcp` endpoint.
2. Open `Authentication`.
3. Under `Custom Headers`, add:
   - Header Name: `Authorization`
   - Header Value: `Bearer <your-shared-token>`
4. Leave the `OAuth 2.0 Flow` fields empty.

Example for a local token such as `AAA`:

```text
Authorization: Bearer AAA
```

## Project Structure

```text
.
├── api/
│   └── index.py
├── docker/
│   └── postgres/
│       └── init/
│           └── 001_schema.sql
├── docs/
│   ├── claude-oauth-plan.md
│   ├── remote-mcp-from-scratch-guide.md
│   └── vercel-deploy.md
├── src/
│   └── apex_mcp_server/
│       ├── asgi.py
│       ├── auth.py
│       ├── config.py
│       ├── identity.py
│       ├── models.py
│       ├── server.py
│       └── storage.py
├── tests/
│   ├── test_auth.py
│   ├── test_config.py
│   ├── test_identity.py
│   ├── test_server.py
│   └── test_storage.py
├── .env.example
├── compose.yaml
├── Dockerfile
├── index.py
├── Makefile
├── pyproject.toml
└── vercel.json
```

## Contributing / Development Notes

- Keep the baseline simple. This repo is meant to be a small MCP starter, not a full platform.
- Add docstrings to every new function, method, and class.
- Prefer straightforward control flow over abstraction-heavy patterns.
- If you change behavior, update tests and the README in the same change.
- If you change deployment behavior, also update [docs/vercel-deploy.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-deploy.md).
- If you change the manual setup flow for WorkOS, Vercel, or Claude, also update [docs/remote-mcp-from-scratch-guide.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/remote-mcp-from-scratch-guide.md).
