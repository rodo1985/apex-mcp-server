# Vercel Deployment Notes

This repo deploys as a single Python ASGI app on Vercel. The MCP endpoint is `/mcp`, and the GitHub OAuth callback is `/auth/callback`.

## Required Vercel resources

1. Create a Vercel Blob store in the same Vercel project.
2. Create a Redis database and copy its `REDIS_URL`.
3. Create a GitHub OAuth App.
4. Set the GitHub OAuth callback URL to:

```text
https://<your-stable-production-domain>/auth/callback
```

## Required environment variables

Set these in the Vercel project:

```text
MCP_AUTH_MODE=github
PROFILE_STORAGE_BACKEND=blob
PUBLIC_BASE_URL=https://<your-stable-production-domain>
GITHUB_CLIENT_ID=<github-oauth-client-id>
GITHUB_CLIENT_SECRET=<github-oauth-client-secret>
REDIS_URL=<your-redis-url>
```

Vercel Blob usually injects this automatically when the store belongs to the same project:

```text
BLOB_READ_WRITE_TOKEN=<vercel-blob-token>
```

Optional:

```text
JWT_SIGNING_KEY=<custom-fastmcp-jwt-signing-key>
BLOB_PROFILE_PREFIX=profiles
MCP_SERVER_NAME=APEX FastMCP Profile Pilot
MCP_SERVER_VERSION=0.1.0
```

## Deployment flow

1. Pull the latest project env locally if needed:

```bash
vercel env pull
```

2. Deploy:

```bash
vercel
```

3. Verify the MCP endpoint is live:

```text
https://<your-stable-production-domain>/mcp
```

4. Connect the remote MCP server from your client and test:
   - `whoami`
   - `set_profile`
   - `get_profile`
   - `profile://me`
   - `use_profile`

## Notes

- Use a stable production domain for OAuth. GitHub callback URLs must match exactly.
- Local development defaults to `MCP_AUTH_MODE=none` and `PROFILE_STORAGE_BACKEND=file`.
- On Vercel, the recommended production setup is `MCP_AUTH_MODE=github` and `PROFILE_STORAGE_BACKEND=blob`.

