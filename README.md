# apex-mcp-server

This repo is a small FastMCP pilot server for a single protected persona profile. It exposes a tiny MCP surface on Vercel: two tools, one resource, one prompt, and one debugging tool.

The goal is to keep the proof of concept easy to understand and easy to deploy. The server can run open for quick local experiments, or in private mode with one shared bearer token for Claude, Codex, or any MCP client that can send `Authorization: Bearer <token>`.

## Key Features / Scope

- Uses FastMCP with Streamable HTTP at `/mcp`.
- Supports `get_profile`, `set_profile`, and `whoami` MCP tools.
- Exposes `profile://me` as a `text/markdown` MCP resource.
- Exposes `use_profile(task: str)` as a simple MCP prompt.
- Supports a shared bearer token with `MCP_API_TOKEN`.
- Supports WorkOS AuthKit OAuth for `claude.ai` production connections.
- Supports local bearer-token mode and production OAuth mode side-by-side.
- Stores profiles locally as markdown files by default.
- Stores profiles in private Vercel Blob objects when Blob is configured.
- Does not implement Redis-backed sessions, multi-profile workflows, or local OAuth login flows.

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

### 4. Optional: use the Makefile helpers

If you prefer short local commands, this repo also includes a small `Makefile`:

```bash
make help
```

## How To Run

### Local development without auth

This is the fastest way to try the server:

```bash
uv run uvicorn index:app --reload
```

Or with the Makefile:

```bash
make run
```

The MCP endpoint will be available at:

```text
http://127.0.0.1:8000/mcp
```

In this mode, the profile is stored in:

```text
profiles/anonymous.md
```

### Local development with bearer-token auth

If you want local behavior to match the private deployed setup, start the server with a token:

```bash
MCP_API_TOKEN=dev-secret-token uv run uvicorn index:app --reload
```

Or with the Makefile:

```bash
make run-private MCP_API_TOKEN=dev-secret-token
```

Because `MCP_API_TOKEN` is present, the server automatically switches to bearer-token mode. In that mode, authenticated requests share one protected profile stored in:

```text
profiles/private-profile.md
```

### Tests

```bash
uv run pytest
```

Or:

```bash
make test
```

### Lint

```bash
uv run ruff check .
```

Or:

```bash
make lint
```

## Configuration

### Local defaults

If you do not set any auth variables:

- `MCP_AUTH_MODE=none`
- `PROFILE_STORAGE_BACKEND=file`
- local profile path: `profiles/anonymous.md`

If you set `MCP_API_TOKEN`, the server automatically switches to:

- `MCP_AUTH_MODE=bearer`
- local protected profile path: `profiles/private-profile.md`

### Environment variables

Optional overrides:

```text
MCP_AUTH_MODE=none|bearer|oauth
MCP_API_TOKEN=your-shared-token
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
PROFILE_STORAGE_BACKEND=file|blob
PROFILES_DIR=profiles
BLOB_PROFILE_PREFIX=profiles
BLOB_READ_WRITE_TOKEN=...
VERCEL_BLOB_READ_WRITE_TOKEN=...
MCP_SERVER_NAME=APEX FastMCP Profile Pilot
MCP_SERVER_VERSION=0.1.0
```

### Vercel production setup

For a Claude-facing OAuth deployment, set at least:

```text
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
```

Optional durable storage:

```text
PROFILE_STORAGE_BACKEND=blob
```

If the Blob store is attached to the same Vercel project, Vercel usually injects:

```text
VERCEL_BLOB_READ_WRITE_TOKEN=<vercel-blob-token>
```

Without Blob, the deployed server falls back to ephemeral file storage inside the serverless runtime. That is fine for a very small demo, but it is not durable across cold starts or redeployments.

For the full manual Vercel deployment and remote testing guide, see [docs/vercel-deploy.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-deploy.md).
For the reusable end-to-end guide you can apply to future MCP servers, including the manual Vercel upload path and WorkOS/Claude setup, see [docs/remote-mcp-from-scratch-guide.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/remote-mcp-from-scratch-guide.md).

### Client connection notes

For local development, any MCP client that can send a bearer token can use this server.

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

If you connect with MCP Inspector, use a custom header instead of the OAuth form.

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
├── docs/
│   └── vercel-deploy.md
├── profiles/
│   └── .gitkeep
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
├── index.py
├── pyproject.toml
├── uv.lock
└── vercel.json
```

## Contributing / Development Notes

- Keep the pilot simple. This repo is meant to be a private MCP hello-world, not a full product.
- Add docstrings to every new function, method, and class.
- Prefer straightforward control flow over abstraction-heavy patterns.
- If you change behavior, update tests and the README in the same change.
- If you change deployment behavior, also update `docs/vercel-deploy.md`.
- OAuth planning for future `claude.ai` support lives in [docs/claude-oauth-plan.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/claude-oauth-plan.md).
