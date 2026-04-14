# AGENTS.md

## Project context

- This repository is a small FastMCP proof of concept for a private wellness-profile server.
- The product goal is a simple MCP server baseline that is easy to run locally and easy to deploy on Vercel or a VM.
- The current auth model is:
  - `none` or one shared bearer token locally
  - WorkOS AuthKit OAuth for `claude.ai` production connections
- The current storage model is Postgres with:
  - one singleton `user_profiles` row per caller
  - food products
  - daily targets
  - daily meals and meal items
  - activity entries
  - memory items
- Treat this repo as a hello-world style pilot. Avoid turning it into a larger platform unless the user explicitly asks for that.

## Repository expectations

- Keep this repo small and easy to understand. Prefer straightforward code over clever abstractions.
- Use `uv` for Python workflows. For local setup and checks, prefer:
  - `make setup`
  - `make db-up`
  - `make run`
  - `make run-private MCP_API_TOKEN=...`
  - `make docker-up`
  - `make docker-down`
  - `make test`
  - `make lint`
- When behavior, setup, or configuration changes, update [README.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/README.md) in the same change.
- When deployment behavior changes, also update [docs/vercel-deploy.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-deploy.md).
- Keep the focused Vercel + Supabase deployment checklist current in [docs/vercel-supabase-setup.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-supabase-setup.md) when the remote Postgres setup or env-variable workflow changes.
- Keep the normal release process current in [docs/day-to-day-workflow.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/day-to-day-workflow.md) when the recommended local, preview, or production workflow changes.
- Keep the reusable from-scratch deployment guide current in [docs/remote-mcp-from-scratch-guide.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/remote-mcp-from-scratch-guide.md) when WorkOS, Vercel, or Claude setup steps change.
- Keep function, method, and class docstrings complete and practical.
- Preserve the current product scope:
  - singleton markdown profile and goals documents
  - one small set of numeric user fields
  - food, daily-log, activity, and memory tables
  - Postgres as the only storage backend
  - simple local auth plus production OAuth
- Run `make lint` and `make test` before finishing behavior changes.

## File routing

- Start with [README.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/README.md) for setup and user-facing behavior.
- Use [docs/day-to-day-workflow.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/day-to-day-workflow.md) for the normal development, push, and deploy flow after the infrastructure is already set up.
- Use [docs/vercel-supabase-setup.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-supabase-setup.md) for the concrete Vercel + Supabase production wiring used by this repo.
- Use [docs/remote-mcp-from-scratch-guide.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/remote-mcp-from-scratch-guide.md) for the full manual and agent-assisted deployment flow.
- Use [src/apex_mcp_server/server.py](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/src/apex_mcp_server/server.py) for the MCP surface: tools, resource, and prompt.
- Use [src/apex_mcp_server/auth.py](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/src/apex_mcp_server/auth.py) and [src/apex_mcp_server/config.py](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/src/apex_mcp_server/config.py) for auth and runtime settings.
- Use [src/apex_mcp_server/storage.py](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/src/apex_mcp_server/storage.py) for Postgres persistence behavior.
- Use [tests/](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/tests) to mirror behavior changes with focused tests.
