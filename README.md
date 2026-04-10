# apex-mcp-server

This repo is a small FastMCP pilot server that stores one persona profile per caller and exposes it through MCP tools, a resource, and a prompt. It is designed to be simple enough for a first remote MCP deployment while still covering the basics of Vercel hosting, GitHub OAuth, local file storage, and Vercel Blob storage.

The pilot intentionally keeps the surface area tiny: get a profile, set a profile, inspect the current identity, read the saved profile as a resource, and render a prompt that injects the saved profile into a task.

## Key Features / Scope

- Uses FastMCP with Streamable HTTP at `/mcp`.
- Supports `get_profile`, `set_profile`, and `whoami` MCP tools.
- Exposes `profile://me` as a text/markdown MCP resource.
- Exposes `use_profile(task: str)` as a simple MCP prompt.
- Stores profiles locally as markdown files during local development.
- Stores profiles in private Vercel Blob objects when deployed on Vercel.
- Uses GitHub OAuth via FastMCP's OAuth proxy for the remote authentication proof of concept.
- Does not add databases, admin dashboards, multi-document workflows, or authorization beyond "one profile per authenticated caller."

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

## How To Run

### Local development server

Local development defaults to:

- `MCP_AUTH_MODE=none`
- `PROFILE_STORAGE_BACKEND=file`
- local profile directory: `profiles/`

Start the MCP server locally:

```bash
uv run uvicorn index:app --reload
```

The MCP endpoint will be available at:

```text
http://127.0.0.1:8000/mcp
```

### Tests

```bash
uv run pytest
```

### Lint

```bash
uv run ruff check .
```

## Configuration

### Local defaults

You can run the pilot locally without any auth or cloud storage configuration. In that mode, all profile operations use a single local markdown file:

```text
profiles/anonymous.md
```

### Environment variables

Optional local overrides:

```text
MCP_AUTH_MODE=none|github
PROFILE_STORAGE_BACKEND=file|blob
PROFILES_DIR=profiles
BLOB_PROFILE_PREFIX=profiles
PUBLIC_BASE_URL=https://your-stable-domain.example
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
REDIS_URL=redis://...
BLOB_READ_WRITE_TOKEN=...
JWT_SIGNING_KEY=...
MCP_SERVER_NAME=APEX FastMCP Profile Pilot
MCP_SERVER_VERSION=0.1.0
```

### Production Vercel setup

For the remote OAuth pilot on Vercel, use:

```text
MCP_AUTH_MODE=github
PROFILE_STORAGE_BACKEND=blob
PUBLIC_BASE_URL=https://<your-stable-production-domain>
GITHUB_CLIENT_ID=<github-oauth-client-id>
GITHUB_CLIENT_SECRET=<github-oauth-client-secret>
REDIS_URL=<your-redis-url>
```

If the Blob store is attached to the same Vercel project, `BLOB_READ_WRITE_TOKEN` is usually injected automatically.

Important OAuth note:

- The MCP endpoint is `/mcp`.
- The GitHub OAuth callback is `/auth/callback`.
- Set your GitHub OAuth App callback URL to `https://<your-stable-production-domain>/auth/callback`.

## Project Structure

```text
.
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
│   ├── test_identity.py
│   ├── test_server.py
│   └── test_storage.py
├── index.py
└── pyproject.toml
```

## Contributing / Development Notes

- Keep the pilot simple. This repo is meant to be a "hello world" for remote MCP, not a production profile system.
- Add docstrings to every new function, method, and class.
- Prefer straightforward control flow over abstraction-heavy patterns.
- If you change behavior, update tests and the README in the same change.
- If you change deployment or auth behavior, also update `docs/vercel-deploy.md`.
