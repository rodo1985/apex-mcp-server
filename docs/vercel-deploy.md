# Vercel Deployment Notes

This document is the manual guide for deploying this MCP server to Vercel and testing it remotely.

This repo deploys as a single Python ASGI app on Vercel. The MCP endpoint is:

```text
/mcp
```

The repo includes:

- `api/index.py` as the Vercel Python Function entrypoint
- `vercel.json` rewrite for `/mcp`

## Current project status

This repo is already linked to the Vercel project `apex-mcp-server` in the team `rodo1985-1166s-projects`.

Current stable production aliases:

- `https://apex-mcp-server.vercel.app`
- `https://apex-mcp-server-rodo1985-1166s-projects.vercel.app`

Current MCP endpoint:

```text
https://apex-mcp-server-rodo1985-1166s-projects.vercel.app/mcp
```

## Smallest private deployment

The smallest useful private setup on Vercel is:

```text
MCP_API_TOKEN=<your-shared-token>
```

That enables bearer-token auth without OAuth, Redis, or any extra auth provider.

## Important Vercel protection note

This project currently has Vercel Authentication enabled in front of the deployment.

That means there are two separate layers a remote MCP client may need to pass:

1. Vercel Deployment Protection
2. Your MCP server bearer token via `Authorization: Bearer <MCP_API_TOKEN>`

For Claude, Codex, MCP Inspector, or other direct MCP clients, the simplest option is usually:

- keep `MCP_API_TOKEN` enabled
- disable Vercel Authentication for the production deployment

Vercel's docs also support an automation bypass if you want to keep Deployment Protection enabled. In that case, clients must also send:

```text
x-vercel-protection-bypass: <your-vercel-bypass-secret>
```

Relevant Vercel docs:

- [Vercel Authentication](https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication)
- [Protection Bypass for Automation](https://vercel.com/docs/security/deployment-protection/methods-to-bypass-deployment-protection/protection-bypass-automation)

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

```bash
vercel link --scope rodo1985-1166s-projects
```

2. Set the required environment variables in Vercel.

```bash
vercel env add MCP_API_TOKEN production --scope rodo1985-1166s-projects
```

3. Deploy to production:

```bash
vercel deploy . --prod --scope rodo1985-1166s-projects
```

4. Verify the MCP endpoint is live:

```text
https://<your-stable-production-domain>/mcp
```

5. Verify the deployed app itself:

If the project is protected by Vercel Authentication, `vercel curl` is the easiest verification path because it can generate a temporary protection bypass automatically:

```bash
vercel curl /mcp \
  --deployment apex-mcp-server-rodo1985-1166s-projects.vercel.app \
  --scope rodo1985-1166s-projects \
  -- \
  --request POST \
  --header "content-type: application/json" \
  --header "accept: application/json, text/event-stream" \
  --header "authorization: Bearer $MCP_API_TOKEN" \
  --data '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"vercel-curl","version":"0.1.0"}}}'
```

6. Connect your MCP client with the same bearer token and test:

- `whoami`
- `set_profile`
- `get_profile`
- `profile://me`
- `use_profile`

## Manual remote testing checklist

Use this checklist when you want to make the Vercel deployment reachable by external MCP clients:

1. Confirm `MCP_API_TOKEN` is set in Vercel Production.
2. Deploy production.
3. Choose one Vercel protection mode:
   - Recommended for this PoC: disable Vercel Authentication for production
   - Alternative: keep it enabled and generate a Protection Bypass for Automation secret
4. Configure the client:
   - always send `Authorization: Bearer <MCP_API_TOKEN>`
   - if Deployment Protection remains enabled, also send `x-vercel-protection-bypass: <secret>`
5. Call `whoami` first to confirm the remote connection is correct.

## Notes

- The same bearer token flow works locally and on Vercel.
- Without Blob, Vercel storage is not durable.
- This private bearer-token setup is a good fit for Claude and Codex style private MCP usage.
- If you later need ChatGPT-style published OAuth flows, add a real OAuth provider as a separate follow-up step instead of complicating this pilot now.
