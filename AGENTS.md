# AGENTS.md

## Project context

- This repository is a small FastMCP proof of concept for a private persona-profile server.
- The product goal is a simple MCP server that is easy to run locally and easy to deploy on Vercel.
- The current auth model is one shared bearer token, not per-user OAuth.
- The current storage model is:
  - local file storage for development by default
  - optional Vercel Blob storage for deployed persistence
- Treat this repo as a hello-world style pilot. Avoid turning it into a larger platform unless the user explicitly asks for that.

## Repository expectations

- Keep this repo small and easy to understand. Prefer straightforward code over clever abstractions.
- Use `uv` for Python workflows. For local setup and checks, prefer:
  - `make setup`
  - `make run`
  - `make run-private MCP_API_TOKEN=...`
  - `make test`
  - `make lint`
- When behavior, setup, or configuration changes, update [README.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/README.md) in the same change.
- When deployment behavior changes, also update [docs/vercel-deploy.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-deploy.md).
- Keep the reusable from-scratch deployment guide current in [docs/remote-mcp-from-scratch-guide.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/remote-mcp-from-scratch-guide.md) when WorkOS, Vercel, or Claude setup steps change.
- Keep function, method, and class docstrings complete and practical.
- Preserve the current product scope:
  - one profile document
  - simple bearer-token auth
  - local file storage by default
  - optional Vercel Blob storage
- Run `make lint` and `make test` before finishing behavior changes.

## File routing

- Start with [README.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/README.md) for setup and user-facing behavior.
- Use [docs/remote-mcp-from-scratch-guide.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/remote-mcp-from-scratch-guide.md) for the full manual and agent-assisted deployment flow.
- Use [src/apex_mcp_server/server.py](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/src/apex_mcp_server/server.py) for the MCP surface: tools, resource, and prompt.
- Use [src/apex_mcp_server/auth.py](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/src/apex_mcp_server/auth.py) and [src/apex_mcp_server/config.py](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/src/apex_mcp_server/config.py) for auth and runtime settings.
- Use [src/apex_mcp_server/storage.py](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/src/apex_mcp_server/storage.py) for profile persistence behavior.
- Use [tests/](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/tests) to mirror behavior changes with focused tests.
