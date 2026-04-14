# Vercel + Supabase Setup Guide

This guide documents the simplest manual path to run this MCP server on Vercel
with Supabase Postgres as the remote database.

It is written as a reusable checklist for future MCP servers as well, so it
uses placeholders instead of real project URLs.

## What this setup gives you

- Vercel hosts the FastMCP app layer
- Supabase hosts the Postgres database
- WorkOS AuthKit handles Claude-compatible OAuth
- Claude connects to the public `/mcp` endpoint

## Architecture at a glance

Use this baseline:

- local:
  - Postgres in Docker Compose
  - app on the host with `uv`, or app + db together in Docker Compose
- remote:
  - Vercel for the app
  - Supabase for Postgres
  - WorkOS AuthKit for OAuth

## 1. Prerequisites

Before you start, make sure you have:

- a Vercel project linked to the repo
- a Supabase project
- a WorkOS project with AuthKit enabled
- a stable public Vercel domain, for example:
  - `https://your-app.vercel.app`

## 2. Prepare Supabase

This repo uses a small wellness schema with these tables:

- `user_profiles`
- `food_products`
- `daily_targets`
- `daily_meals`
- `meal_items`
- `activity_entries`
- `memory_items`

You can let the app create the table automatically on first successful
connection, because the server bootstraps the additive schema at startup. If
you prefer to create it manually first, use the checked-in SQL file in
[`docker/postgres/init/001_schema.sql`](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docker/postgres/init/001_schema.sql)
in the Supabase SQL editor.

## 3. Get the Supabase connection string

For Vercel, the recommended starting point for this repo is the Supabase
`Transaction pooler` connection string from the **Connect** dialog in the
Supabase dashboard.

Why this is the best fit here:

- Vercel runs the app in a serverless environment
- Supabase recommends the transaction pooler for serverless workloads
- this repo disables asyncpg statement caching so the driver stays compatible
  with transaction poolers

Manual steps:

1. Open your Supabase project
2. Click **Connect**
3. In the connect dialog, open the tab or section that shows the database
   connection methods
4. Select **Transaction pooler**
5. Copy the full connection string
6. Replace the `[YOUR-PASSWORD]` placeholder with your real database password

It should look roughly like this:

```text
postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres
```

Use the exact string shown by Supabase instead of constructing it manually.

### Where to find the database password

The database password is the password you set when you created the Supabase
project.

If you do not have it anymore, Supabase says to reset it from the project
dashboard:

1. Open your Supabase project
2. Go to **Database**
3. Open **Settings**
4. Reset the database password
5. Go back to **Connect**
6. Copy the **Transaction pooler** connection string again
7. Replace `[YOUR-PASSWORD]` with the new password

### Important password note

If your Supabase password contains special characters, percent-encode them
before putting them into the connection string. For example, `p=word` becomes
`p%3Dword`.

## 4. Prepare WorkOS AuthKit

In WorkOS:

1. Enable AuthKit for your project
2. In the MCP/Auth configuration:
   - enable `Dynamic Client Registration (DCR)`
   - enable `Client ID Metadata Document (CIMD)`
3. Add the MCP resource indicator:

```text
https://your-app.vercel.app/mcp
```

4. Add both Claude callback URLs:

```text
https://claude.ai/api/mcp/auth_callback
https://claude.com/api/mcp/auth_callback
```

5. Copy your AuthKit domain:

```text
https://your-project.authkit.app
```

That AuthKit URL becomes `WORKOS_AUTHKIT_DOMAIN`.

## 5. Set Vercel environment variables

In Vercel project settings, add these production environment variables:

```text
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-app.vercel.app
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
```

Optional:

```text
MCP_SERVER_NAME=APEX FastMCP Profile Pilot
MCP_SERVER_VERSION=0.1.0
```

Important notes:

- `MCP_PUBLIC_BASE_URL` is the base URL only
- do not append `/mcp` to `MCP_PUBLIC_BASE_URL`
- `DATABASE_URL` should not go in the repo; keep it only in Vercel

## 6. Make the Claude-facing endpoint public

For `claude.ai`, the production `/mcp` route must be publicly reachable.

Do not leave Vercel Deployment Protection in front of the production MCP
endpoint. Otherwise Claude reaches Vercel’s auth wall instead of your server’s
OAuth flow.

## 7. Deploy to Vercel

From the repo root:

```bash
vercel deploy . --prod
```

After deploy, your MCP endpoint should be:

```text
https://your-app.vercel.app/mcp
```

## 8. Connect in Claude

In `claude.ai`:

1. Add a custom connector
2. Use:

```text
https://your-app.vercel.app/mcp
```

3. Leave OAuth Client ID and OAuth Client Secret empty when DCR is enabled
4. Click **Add**
5. Click **Connect**
6. Complete the WorkOS sign-in flow

## 9. Verify the full round trip

After Claude connects successfully, test these MCP actions:

- `whoami`
- `set_profile`
- `get_profile`
- `set_diet_preferences`
- `get_diet_preferences`
- `set_user_data`
- `get_user_data`
- `add_product`
- `set_daily_target`
- `add_meal`
- `add_meal_item`
- `add_activity`
- `add_memory_item`
- `get_daily_summary`
- `profile://me`
- `use_profile`

If `whoami` works but writes fail, check the `DATABASE_URL` first. With this
Postgres baseline, write failures usually mean the remote DB connection string
is missing or incorrect.

## 10. Troubleshooting checklist

### Claude cannot connect at all

Check:

- the connector URL ends with `/mcp`
- Vercel Deployment Protection is disabled for the production route
- WorkOS DCR and CIMD are both enabled
- the MCP resource indicator matches the final `/mcp` URL

### OAuth starts but login fails

Check:

- `WORKOS_AUTHKIT_DOMAIN` is correct
- both Claude callback URLs are present in WorkOS
- `MCP_PUBLIC_BASE_URL` matches the deployed public base URL exactly

### Reads work but writes fail

Check:

- `DATABASE_URL` is present in Vercel production
- the Supabase password in the connection string is correct
- the connection string came from the Supabase **Transaction pooler** section

## 11. Why this is a good baseline

This setup keeps the project small while staying ready for future MCP servers:

- one app
- one Postgres database
- one OAuth provider
- one deployment target

That keeps local and remote development aligned without introducing a larger
platform too early.
