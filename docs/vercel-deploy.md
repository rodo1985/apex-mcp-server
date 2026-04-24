# Vercel Deployment Notes

This document is the manual guide for deploying this MCP server to Vercel and testing it remotely.

If you specifically want the concrete Vercel + Supabase production path used by
this repo, see [docs/vercel-supabase-setup.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-supabase-setup.md).

This repo deploys as a single Python ASGI app on Vercel. The MCP endpoint is:

```text
/mcp
```

The repo includes:

- `api/index.py` as the Vercel Python Function entrypoint
- `vercel.json` rewrite for `/mcp`

## Production URL shape

Use placeholders like these when adapting the guide to another project:

```text
Base URL: https://your-app.vercel.app
MCP URL:  https://your-app.vercel.app/mcp
```

## Storage model

This baseline uses Postgres in every environment. Vercel only hosts the app layer.

That means production needs:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
```

The Postgres provider can be any managed or self-hosted service that exposes a
normal connection string. This repo does not depend on a provider-specific SDK.

The current schema includes:

- `user_profiles`
- `food_products`
- `daily_targets`
- `daily_metrics`
- `daily_meals`
- `meal_items`
- `activity_entries`
- `memory_items`

Product rows include an internal `usage_count` that starts at `0` and
increments when a product-backed meal item is added successfully.

The app can create additive schema changes on first successful connection when
the database role has DDL permission. If not, apply the new SQL block from
`docker/postgres/init/001_schema.sql` manually before deployment.

If you use Supabase, get the connection string from:

1. project dashboard
2. **Connect**
3. **Transaction pooler**
4. copy the connection string
5. replace `[YOUR-PASSWORD]` with the database password

If you do not have the password anymore, reset it from **Database → Settings**
in the Supabase project first.

For existing databases, the app bootstrap can add the current usage-count
column automatically. You can also apply it manually in Supabase before deploy:

```sql
ALTER TABLE food_products
ADD COLUMN IF NOT EXISTS usage_count INTEGER NOT NULL DEFAULT 0;
```

## Local bearer-token mode

The repo still supports the existing bearer-token mode for local development and developer-facing clients.

Minimal local auth:

```text
MCP_API_TOKEN=<your-shared-token>
```

That enables bearer-token auth without OAuth, Redis, or any extra auth provider.

## Recommended Claude.ai production deployment

For `claude.ai`, the recommended production setup is OAuth mode with WorkOS AuthKit:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
```

## Important Vercel protection note

For Claude.ai, Anthropic's cloud must be able to reach the MCP endpoint directly.

For the OAuth production deployment, do not put Vercel Deployment Protection in front of the Claude-facing `/mcp` endpoint. Let OAuth happen at the MCP server layer.

Bearer-token mode can still be used locally or in direct developer tooling, but it should not be the primary production path for Claude.ai.

Relevant Vercel docs:

- [Vercel Authentication](https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication)
- [Protection Bypass for Automation](https://vercel.com/docs/security/deployment-protection/methods-to-bypass-deployment-protection/protection-bypass-automation)

## Claude callback URLs to allowlist

If your OAuth provider uses callback allowlists, allow both:

```text
https://claude.ai/api/mcp/auth_callback
https://claude.com/api/mcp/auth_callback
```

## Recommended environment variables

Production:

```text
DATABASE_URL=postgresql://user:password@host:5432/database
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
```

Optional:

```text
MCP_SERVER_NAME=APEX FastMCP Profile Pilot
MCP_SERVER_VERSION=0.1.0
```

## Where to store secrets

For deployed environments, put secrets in the Vercel project settings:

- Vercel Dashboard → Project → Settings → Environment Variables

For local development, keep secrets local only. Two simple options are:

1. Copy `.env.example` to `.env.local`
2. Use `vercel env pull` to copy Vercel env vars into a local env file that stays out of git

Do not commit bearer tokens or database passwords into the repo.

## Deployment flow

1. Link the repo to the Vercel project if needed.

```bash
vercel link
```

2. Set the required environment variables in Vercel.

```bash
vercel env add DATABASE_URL production
vercel env add MCP_AUTH_MODE production
vercel env add MCP_PUBLIC_BASE_URL production
vercel env add WORKOS_AUTHKIT_DOMAIN production
```

3. Deploy to production:

```bash
vercel deploy . --prod
```

4. Verify the MCP endpoint is live:

```text
https://<your-stable-production-domain>/mcp
```

5. Add the connector in Claude using the production `/mcp` URL and complete the OAuth flow.

6. Verify the connector can call:

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
- `memory_items(operation="add", ...)`
- `get_daily_summary`
- `profile://me`
- `use_profile`

## Manual remote testing checklist

Use this checklist when you want to make the Vercel deployment reachable by Claude.ai:

1. Confirm `DATABASE_URL` is set in Vercel Production.
2. Confirm `MCP_AUTH_MODE=oauth` is set in Vercel Production.
3. Confirm `MCP_PUBLIC_BASE_URL` matches the final public production URL.
4. Confirm `WORKOS_AUTHKIT_DOMAIN` is set correctly.
5. Confirm Vercel Deployment Protection is not blocking the production `/mcp` route.
6. Deploy production.
7. Add the connector in `claude.ai`.
8. Complete the OAuth flow.
9. Call `whoami` first to confirm the remote identity is correct.
10. Verify at least one document write, one tabular write, one daily metric
    write, and one collection write round-trip successfully.

If you change the published MCP tool surface or authentication behavior, remove and re-add the Claude connector or reconnect it so Claude refreshes its tokens and tool schema.

## Local development checklist

Use this checklist when you want to keep local testing simple:

1. Start the database:
   - `make db-up`
2. For open local mode:
   - `make run`
3. For bearer-token local mode:
   - `make run-private MCP_API_TOKEN=dev-secret-token`
4. Test with MCP Inspector or another direct MCP client using:
   - `Authorization: Bearer <MCP_API_TOKEN>`

## Notes

- The same repo now supports both local bearer-token auth and production OAuth mode.
- Postgres is the only persistence layer in this baseline.
- OAuth mode is the recommended path for Claude.ai.
- Bearer-token mode remains useful for local development and direct developer tooling.
