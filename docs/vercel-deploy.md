# Vercel Deployment Notes

This repo deploys as a single Python ASGI app on Vercel. The MCP endpoint is:

```text
/mcp
```

The repo includes:

- `api/index.py` as the Vercel Python Function entrypoint
- `vercel.json` rewrite for `/mcp`

## Smallest private deployment

The smallest useful private setup on Vercel is:

```text
MCP_API_TOKEN=<your-shared-token>
```

That enables bearer-token auth without OAuth, Redis, or any extra auth provider.

## Optional durable storage

If you want profile changes to persist across redeployments and cold starts, add a Vercel Blob store to the same project and set:

```text
PROFILE_STORAGE_BACKEND=blob
```

Vercel Blob usually injects this automatically when the store belongs to the same project:

```text
VERCEL_BLOB_READ_WRITE_TOKEN=<vercel-blob-token>
```

You can also provide `BLOB_READ_WRITE_TOKEN` manually if you prefer.

If Blob is not configured, the server still works, but it uses ephemeral file storage inside the serverless runtime.

## Recommended environment variables

Production:

```text
MCP_API_TOKEN=<your-shared-token>
PROFILE_STORAGE_BACKEND=file|blob
```

Optional:

```text
BLOB_PROFILE_PREFIX=profiles
MCP_SERVER_NAME=APEX FastMCP Profile Pilot
MCP_SERVER_VERSION=0.1.0
```

## Where to store secrets

For deployed environments, put secrets in the Vercel project settings:

- Vercel Dashboard → Project → Settings → Environment Variables

For local development, keep secrets local only. Two simple options are:

1. Export them in your shell before running `uvicorn`
2. Use `vercel env pull` to copy Vercel env vars into a local env file that stays out of git

Do not commit bearer tokens into the repo.

## Deployment flow

1. Link the repo to the Vercel project if needed.

2. Set the required environment variables in Vercel.

3. Deploy:

```bash
vercel
```

4. Verify the MCP endpoint is live:

```text
https://<your-stable-production-domain>/mcp
```

5. Connect your MCP client with the same bearer token and test:

- `whoami`
- `set_profile`
- `get_profile`
- `profile://me`
- `use_profile`

## Notes

- The same bearer token flow works locally and on Vercel.
- Without Blob, Vercel storage is not durable.
- This private bearer-token setup is a good fit for Claude and Codex style private MCP usage.
- If you later need ChatGPT-style published OAuth flows, add a real OAuth provider as a separate follow-up step instead of complicating this pilot now.
