# Claude.ai OAuth Migration Plan

This document describes the second step for this repository: keep bearer-token auth for local development, and add an OAuth-compatible production mode for connecting the Vercel deployment to `claude.ai`, including iPhone use.

Treat it as background design context. The current repo has since expanded the
MCP surface and Postgres schema beyond the exact scope described here, but the
WorkOS/Vercel OAuth guidance is still relevant.

## Why this second step exists

The current bearer-token setup is a good local and developer-client solution:

- local development
- MCP Inspector
- Codex
- Claude Code

It is not the best fit for hosted `claude.ai` connectors, because those connectors are configured in Claude's cloud and are designed around remote MCP OAuth flows.

## Current repo state

Today the repo supports:

- `MCP_AUTH_MODE=none` for fast local experiments
- `MCP_AUTH_MODE=bearer` for a private shared-token flow
- Vercel deployment at `/mcp`
- Postgres as the shared persistence layer
- Docker Compose for local database setup

This should stay true after the OAuth migration. Bearer-token auth is still useful for local testing and should not be removed.

## OAuth options

### Option 1: WorkOS AuthKit with FastMCP `AuthKitProvider`

This is the recommended path.

Why:

- it is a better fit for Claude remote MCP auth
- FastMCP documents it as a first-class integration
- it avoids adding the FastMCP OAuth proxy layer
- it avoids the Redis-style production storage requirement that usually comes with the proxy path

Use this when you want the smallest production-ready OAuth setup for `claude.ai`.

### Option 2: Another DCR-capable provider with FastMCP `RemoteAuthProvider`

Examples include modern OIDC providers that support Dynamic Client Registration.

This is also a good architecture, but it is slightly less direct for this repo than the documented AuthKit integration.

### Option 3: Traditional provider plus FastMCP `OAuthProxy`

Examples:

- GitHub OAuth
- Google OAuth
- Auth0 regular OAuth apps

This is valid, and Claude now supports manual client ID and client secret input for non-DCR servers. However, on the server side this path is still more complex for this repo because FastMCP's proxy path is designed for persistent production storage and is not the smallest Vercel setup.

## Recommended approach

For this repository, the simplest path is:

1. Keep bearer-token auth for local development.
2. Add a new production OAuth mode.
3. Use WorkOS AuthKit for the production OAuth mode.
4. Make the production `/mcp` endpoint publicly reachable to Claude.
5. Keep the Postgres `DATABASE_URL` model unchanged while switching auth modes.

## Proposed auth modes

After the migration, the server should support three modes:

- `MCP_AUTH_MODE=none`
- `MCP_AUTH_MODE=bearer`
- `MCP_AUTH_MODE=oauth`

Expected usage:

- local development:
  - `none` or `bearer`
- Vercel production for Claude:
  - `oauth`

## Important Vercel note

For `claude.ai`, Anthropic's cloud must be able to reach the MCP endpoint directly.

That means Vercel Deployment Protection should not sit in front of the Claude-facing production `/mcp` route unless you are certain the connector can satisfy that protection layer. For this repository, the safer design is:

- OAuth at the MCP server layer
- no extra Vercel auth gate in front of the production Claude-facing endpoint

## Claude requirements to design for

The production OAuth mode should be compatible with the current Claude connector behavior:

- Claude supports OAuth for remote MCP servers
- Claude supports Dynamic Client Registration
- Claude supports token expiry and refresh
- Claude's current callback URL is:
  - `https://claude.ai/api/mcp/auth_callback`
- Claude may also use:
  - `https://claude.com/api/mcp/auth_callback`

If the provider uses callback allowlists, allow both URLs.

## Suggested code changes

### 1. Extend settings

Update `src/apex_mcp_server/config.py` to support:

- `MCP_AUTH_MODE=oauth`
- AuthKit-specific environment variables
- validation rules for OAuth mode only

Keep bearer-token validation untouched for local use.

### 2. Extend auth provider wiring

Update `src/apex_mcp_server/auth.py` so:

- `none` returns `None`
- `bearer` returns the current static verifier
- `oauth` returns the AuthKit-backed provider

Keep the current bearer-token verifier exactly as the local-development path.

### 3. Keep MCP surface unchanged

Do not change the tools, resource, or prompt shape unless required:

- `get_profile`
- `set_profile`
- `whoami`
- `profile://me`
- `use_profile(task)`

The OAuth work should change authentication, not the product behavior.

### 4. Update identity resolution carefully

Update `src/apex_mcp_server/identity.py` to accept the authenticated subject from the OAuth provider and continue generating a stable storage key.

Preserve the current simple storage contract:

- one profile per authenticated subject

### 5. Keep ASGI/Vercel shape simple

The current `FastMCP.http_app(...)` pattern in `src/apex_mcp_server/asgi.py` should remain the deployment shape unless the OAuth provider requires a small additional route.

## Suggested environment variables

These names can be refined during implementation, but the split should look roughly like this:

### Local development

```text
MCP_AUTH_MODE=none|bearer
MCP_API_TOKEN=<shared-local-token>
```

### Vercel production for Claude

```text
MCP_AUTH_MODE=oauth
DATABASE_URL=postgresql://user:password@host:5432/database
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=...
```

## Suggested implementation order

1. Add OAuth settings and provider wiring.
2. Add tests for config validation and auth-mode selection.
3. Add tests for identity handling under OAuth claims.
4. Keep bearer-token tests passing.
5. Update Vercel deployment notes.
6. Deploy to a public production endpoint.
7. Add the connector in `claude.ai`.
8. Test from desktop Claude first, then iPhone.

## Manual test plan

### Local

Confirm existing behavior still works:

- `make run`
- `make run-private MCP_API_TOKEN=...`
- `make test`
- `make lint`

### Remote OAuth

Once deployed:

1. Open the connector setup in `claude.ai`.
2. Enter the production MCP URL.
3. Complete the OAuth flow.
4. Confirm the connector can call:
   - `whoami`
   - `set_profile`
   - `get_profile`
   - `set_user_data`
   - `get_user_data`
5. Confirm reconnect works after token refresh.

## What not to do

- Do not remove bearer-token auth; it is still useful for local development.
- Do not add multiple auth systems for local use unless they are clearly needed.
- Do not expand the MCP surface while doing the auth migration.
- Do not add Redis unless the chosen OAuth path truly requires it.

## Recommended next step

Implement `MCP_AUTH_MODE=oauth` with WorkOS AuthKit while preserving the current `none` and `bearer` modes.

## Sources

- Anthropic: [Build custom connectors via remote MCP servers](https://support.claude.com/en/articles/11503834-build-custom-connectors-via-remote-mcp-servers)
- Anthropic: [Get started with custom connectors using remote MCP](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- FastMCP: [Remote OAuth](https://gofastmcp.com/servers/auth/remote-oauth)
- FastMCP: [OAuth Proxy](https://gofastmcp.com/servers/auth/oauth-proxy)
- FastMCP: [AuthKit integration](https://gofastmcp.com/integrations/authkit)
- OpenAI Codex docs: [AGENTS Guidance](https://developers.openai.com/codex/concepts/customization#agents-guidance)
