# Vercel Deployment Notes

This document is the manual guide for deploying this MCP server to Vercel and testing it remotely.

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
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
PROFILE_STORAGE_BACKEND=file|blob
```

Optional durable storage:

```text
VERCEL_BLOB_READ_WRITE_TOKEN=<vercel-blob-token>
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
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-public-domain
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
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
vercel link
```

2. Set the required environment variables in Vercel.

```bash
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
- `set_profile`
- `get_profile`
- `profile://me`
- `use_profile`

## Manual remote testing checklist

Use this checklist when you want to make the Vercel deployment reachable by Claude.ai:

1. Confirm `MCP_AUTH_MODE=oauth` is set in Vercel Production.
2. Confirm `MCP_PUBLIC_BASE_URL` matches the final public production URL.
3. Confirm `WORKOS_AUTHKIT_DOMAIN` is set correctly.
4. Confirm Vercel Deployment Protection is not blocking the production `/mcp` route.
5. Deploy production.
6. Add the connector in `claude.ai`.
7. Complete the OAuth flow.
8. Call `whoami` first to confirm the remote identity is correct.
9. Verify `set_profile` and `get_profile` round-trip successfully.

## Local development checklist

Use this checklist when you want to keep local testing simple:

1. For open local mode:
   - `make run`
2. For bearer-token local mode:
   - `make run-private MCP_API_TOKEN=dev-secret-token`
3. Test with MCP Inspector or another direct MCP client using:
   - `Authorization: Bearer <MCP_API_TOKEN>`

## Notes

- The same repo now supports both local bearer-token auth and production OAuth mode.
- Without Blob, Vercel storage is not durable.
- OAuth mode is the recommended path for Claude.ai.
- Bearer-token mode remains useful for local development and direct developer tooling.
