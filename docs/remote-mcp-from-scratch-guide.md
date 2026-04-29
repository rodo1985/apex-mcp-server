# Remote MCP From Scratch Guide

This is the reusable, end-to-end guide for building and deploying a small private MCP server like this one. It is written to be generic enough to reuse on future projects.

The baseline described here is:

- FastMCP server
- Postgres as the only persistence layer
- Docker Compose for local development
- Vercel for the app deployment
- WorkOS AuthKit for Claude-compatible OAuth
- Claude custom connector for remote use

## 1. Build a small MCP surface first

Start with the smallest useful server shape:

- one or two tools that prove read and write behavior
- one resource
- one prompt
- one debugging tool such as `whoami`

Keep the first useful data model small but practical. A good starter shape is:

- one or more markdown profile or goals fields
- a few numeric fields for simple tabular data
- one or two small collection tables that prove CRUD and summaries

That is enough to prove:

- auth
- persistence
- tool calls
- resource reads
- prompt rendering

## 2. Use one storage model everywhere

For a reusable baseline, keep storage simple and consistent:

- local: Postgres in Docker Compose
- remote: Postgres through `DATABASE_URL`

Do not split early into:

- local files for text
- database for tabular data

Small markdown content can live in Postgres `TEXT` columns just fine. Save
object storage for true file assets later.

## 3. Recommended local architecture

Use two local workflows:

### Fast iteration

- Postgres in Docker
- MCP server on the host with `uv`

Typical commands:

```bash
make db-up
make run
```

Or bearer-token local mode:

```bash
make run-private MCP_API_TOKEN=dev-secret-token
```

### Full container parity

- app container
- Postgres container

Typical commands:

```bash
make docker-up
make docker-down
```

## 4. Local environment file

Commit an example env file such as `.env.example`, then copy it locally:

```bash
cp .env.example .env.local
```

Recommended local defaults:

```text
POSTGRES_DB=apex_mcp_server
POSTGRES_USER=apex
POSTGRES_PASSWORD=apex
POSTGRES_PORT=54329
DATABASE_URL=postgresql://apex:apex@127.0.0.1:54329/apex_mcp_server
MCP_AUTH_MODE=none
MCP_API_TOKEN=
```

Keep production-only values out of git.

## 5. Docker baseline

For a small Python MCP server, keep the Docker image straightforward:

- base image: `python:3.12-slim`
- install `uv`
- copy the app files
- `uv sync --frozen`
- run `uvicorn index:app --host 0.0.0.0 --port 8000`

For Docker Compose, use:

- `postgres:16-alpine` for the database
- a named volume for Postgres data
- one checked-in SQL init script for the baseline schema

## 6. Manual Vercel upload flow

This is the manual path to upload the MCP server to Vercel from scratch.

### Log in to Vercel

```bash
vercel login
```

### Link or create the project

From the repo root:

```bash
vercel link
```

If Vercel asks:

- create a new project if this is the first deployment
- choose the current directory
- keep the project as a Python app with the existing repo files

### First preview deploy

```bash
vercel deploy .
```

This is useful to confirm the project wiring before production.

### Production deploy

```bash
vercel deploy . --prod
```

Your public MCP endpoint should then be:

```text
https://your-app.vercel.app/mcp
```

## 7. Remote Postgres on Vercel

Vercel only hosts the app layer in this baseline. The database stays external.

So the minimum remote storage variable is:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
```

This keeps the app provider-agnostic. You can point it to:

- Supabase Postgres
- Neon Postgres
- a VM-hosted Postgres instance
- any standard remote Postgres service

For a baseline like this repo, keep the schema small and explicit:

- one singleton user/profile table
- a few user-scoped collection tables
- computed summaries in code instead of precomputed rollup tables

### Supabase note

If you use Supabase with Vercel, start with the **Transaction pooler**
connection string from the **Connect** dialog in the Supabase dashboard.

If the connection string contains `[YOUR-PASSWORD]`, replace it with the
database password you set when the project was created. If you no longer have
that password, reset it from **Database → Settings**, then copy the connection
string again.

## 8. WorkOS AuthKit setup

Use the WorkOS dashboard, not the WorkOS AI installer, for this repo.

Important WorkOS steps:

1. Create a WorkOS account and project.
2. Enable AuthKit for the project.
3. In the MCP/Auth configuration:
   - enable `Dynamic Client Registration (DCR)`
   - enable `Client ID Metadata Document (CIMD)`
4. Add the MCP resource indicator:

```text
https://your-app.vercel.app/mcp
```

5. Add Claude callback URLs:

```text
https://claude.ai/api/mcp/auth_callback
https://claude.com/api/mcp/auth_callback
```

6. Copy the AuthKit domain:

```text
https://your-project.authkit.app
```

That value becomes:

```text
WORKOS_AUTHKIT_DOMAIN
```

## 9. Vercel production environment variables

For Claude-facing production, set:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-app.vercel.app
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
```

Important:

- `MCP_PUBLIC_BASE_URL` is the base URL only
- do not include `/mcp` in `MCP_PUBLIC_BASE_URL`
- `WORKOS_AUTHKIT_DOMAIN` is your AuthKit domain, not your app URL
- add `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and
  `STRAVA_REFRESH_TOKEN` only if this deployment should sync Strava activities

## 10. Vercel protection setting

For `claude.ai`, the production `/mcp` route must be publicly reachable.

Do not leave Vercel Deployment Protection in front of the Claude-facing `/mcp` endpoint. Otherwise Claude hits Vercel’s auth wall instead of your MCP server’s OAuth flow.

## 11. Add the Claude connector

In `claude.ai`:

1. Add a custom connector
2. Use the full MCP URL:

```text
https://your-app.vercel.app/mcp
```

3. Leave OAuth Client ID and OAuth Client Secret empty when DCR is enabled
4. Click `Add`
5. Click `Connect`
6. Complete the WorkOS sign-in flow

After connection, test:

- `whoami`
- `profile_documents(operation="set", document="profile", ...)`
- `profile_documents(operation="get", document="profile")`
- `profile_documents(operation="set", document="diet_preferences", ...)`
- `user_data(operation="set", ...)`
- `user_data(operation="get")`
- `products(operation="add", ...)`
- `daily_targets(operation="set", ...)`
- `daily_metrics(operation="set", metric_type="weight", ...)`
- `meals(operation="add", ...)`
- `meal_items(operation="add", ...)`
- `activities(operation="add", ...)`
- `sync_external_service(service="strava", day="today")`
- `memory_items(operation="add", ...)`
- `get_daily_summary`

## 12. What Codex or Claude Code can automate

These tools are good at:

- scaffolding the server code
- creating Docker and Compose files
- updating README and docs
- setting Vercel environment variables
- deploying to Vercel
- validating the remote MCP endpoint

These tools should not replace:

- the WorkOS dashboard setup
- the manual Claude connector approval flow

For this repo specifically, avoid using the WorkOS AI installer. It is designed to wire AuthKit into regular app frameworks and is not the right fit for this FastMCP server layout.

## 13. Suggested baseline to reuse

For future small MCP servers, this is a strong default baseline:

- FastMCP server
- one Postgres database
- Docker Compose for local DB and optional local app container
- local `none` or `bearer` auth
- WorkOS OAuth for `claude.ai`
- Vercel for the app layer only

That gives you:

- one data model
- one storage story
- one deployment story
- one auth story for hosted Claude use

without turning the repo into a larger platform too early.
