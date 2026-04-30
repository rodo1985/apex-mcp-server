# Day-to-Day Workflow

This guide is the practical operating path for this repo after the one-time
infrastructure setup is done.

Use it for normal development and releases. It assumes these pieces already
exist:

- Vercel project linked
- Supabase project configured
- WorkOS AuthKit configured
- Vercel production environment variables already set

If those are not in place yet, use
[docs/vercel-supabase-setup.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-supabase-setup.md)
first.

## Workflow overview

The recommended baseline is:

1. develop locally
2. run lint and tests locally
3. push code
4. deploy to Vercel
5. validate the remote MCP endpoint only when behavior changed

Most updates should not require touching:

- Supabase project settings
- WorkOS dashboard settings
- Vercel production env vars

Those are infrastructure steps, not daily development steps.

## 1. Normal local development

Start the local Postgres database:

```bash
make db-up
```

Run the MCP server without auth:

```bash
make run
```

Or run it with bearer-token auth for direct client testing:

```bash
make run-private MCP_API_TOKEN=dev-secret-token
```

If you want the full local container flow instead:

```bash
make docker-up
make docker-down
```

## 2. Before every push

Run the repo checks:

```bash
make lint
make test
```

This should be the standard rule before pushing behavior changes.

## 3. Recommended Git flow

Use a short feature branch, work locally, then push:

```bash
git checkout -b codex/your-change
git push -u origin codex/your-change
```

If your Vercel project is connected to GitHub with auto-deploys enabled, a push
can create a preview deployment automatically.

If you prefer manual control, push first and deploy separately.

## 4. Preview deploys vs production deploys

### Preview deploy

Use a preview deploy when:

- the change affects setup or UI around deployment
- you want to sanity-check the Vercel build first
- you are testing branch work before merging

Manual preview deploy:

```bash
vercel deploy .
```

### Production deploy

Use a production deploy when:

- tests already pass locally
- the change is ready for Claude-facing use
- the change should update the stable `/mcp` connector endpoint

Manual production deploy:

```bash
vercel deploy . --prod
```

## 5. What usually stays unchanged

For normal code-only releases, you should not need to change:

- `DATABASE_URL`
- `MCP_AUTH_MODE`
- `MCP_PUBLIC_BASE_URL`
- `WORKOS_AUTHKIT_DOMAIN`
- `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and `STRAVA_REFRESH_TOKEN`
- Supabase table structure, unless you are making a schema change

That means most updates are just:

```bash
make lint
make test
git push
vercel deploy . --prod
```

## 6. When you do need manual infra work

Touch infrastructure only when one of these changes:

- the database schema
- the Supabase project
- the database password
- the Vercel production domain
- the WorkOS AuthKit project/domain
- the Strava app credentials or refresh token
- the Claude-facing OAuth behavior

Examples:

- If the Supabase password changes, update `DATABASE_URL` in Vercel.
- If the domain changes, update `MCP_PUBLIC_BASE_URL` and the WorkOS MCP
  resource indicator.
- If the schema changes, apply the new SQL to Supabase and keep local Docker
  schema init in sync.
- If you manually regenerate Strava OAuth tokens, update `STRAVA_REFRESH_TOKEN`
  in Vercel and redeploy. Normal Strava token rotation is saved in Postgres by
  the sync tool after the first successful sync.

## 7. Recommended validation after deploy

Use the smallest validation that matches the change.

### For code-only backend changes

Check:

- deployment is ready on Vercel
- `/mcp` responds
- OAuth metadata endpoints respond

### For storage changes

Also verify:

- `profile_documents(operation="set", document="profile", ...)`
- `profile_documents(operation="get", document="profile")`
- `profile_documents(operation="set", document="diet_preferences", ...)`
- `user_data(operation="set", ...)`
- `user_data(operation="get")`
- `daily_metrics(operation="set", metric_type="weight", ...)`
- `daily_metrics(operation="list", metric_type="weight")`
- one collection write such as `products(operation="add", ...)`,
  `meals(operation="add", ...)`, or `memory_items(operation="add", ...)`
- `get_daily_summary`

### For auth changes

Also verify:

- Claude can reconnect
- `whoami` returns the expected subject/login

## 8. Good default for this repo

For this project, the simplest sustainable operating model is:

- local development with Docker Postgres
- manual production deploy when needed
- no repeated dashboard work unless infrastructure changes

That keeps the repo simple without over-automating too early.
