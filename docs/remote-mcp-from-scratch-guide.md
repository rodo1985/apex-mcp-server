# Remote MCP Server Guide: WorkOS + Vercel + Claude

This guide documents the full flow we used to take this MCP server from local development to a working `claude.ai` custom connector.

It is designed to be reusable for future MCP servers. It avoids project-specific secrets and uses placeholders so you can follow the same process in another repo.

## What this guide covers

This guide covers:

- local MCP development
- optional local bearer-token testing
- WorkOS AuthKit setup for MCP
- Vercel production configuration
- connecting the deployed MCP server to `claude.ai`
- what can be done manually versus what an agent can do for you

This guide does not cover:

- ChatGPT connector setup
- custom AuthKit domains
- WorkOS Standalone Connect
- multi-user product design beyond one profile per authenticated subject

## Architecture used in this repo

This repo supports three auth modes:

- `MCP_AUTH_MODE=none`
- `MCP_AUTH_MODE=bearer`
- `MCP_AUTH_MODE=oauth`

Recommended usage:

- local experiments: `none`
- local secure testing: `bearer`
- Claude production connector: `oauth`

In production, the OAuth provider is WorkOS AuthKit and the app is deployed on Vercel.

## Phase 1: Build and test locally

### 1. Set up the repo

```bash
uv venv
uv sync
```

Or use the repo `Makefile`:

```bash
make setup
```

### 2. Test the server locally without auth

```bash
make run
```

Expected MCP endpoint:

```text
http://127.0.0.1:8000/mcp
```

### 3. Test the server locally with bearer-token auth

```bash
make run-private MCP_API_TOKEN=dev-secret-token
```

Use this local header when testing with MCP Inspector or other direct clients:

```text
Authorization: Bearer dev-secret-token
```

### 4. Verify the local test suite

```bash
make lint
make test
```

## Phase 2: Configure WorkOS AuthKit for MCP

This is the part that must be done in the WorkOS dashboard. An agent can guide you, but these dashboard settings are usually the most reliable way to complete the setup.

### 1. Create a WorkOS account and project

If you do not already have a WorkOS account:

1. Create the account.
2. Create a project.
3. Choose the environment you want to configure.

Recommendation:

- use `Staging` first for testing
- later repeat the same setup in `Production`

### 2. Enable AuthKit

Open the AuthKit section of your WorkOS project and complete the minimum setup.

What you need to obtain from this step:

- your AuthKit domain

It will look like:

```text
https://your-project.authkit.app
```

This becomes:

```text
WORKOS_AUTHKIT_DOMAIN
```

### 3. Open the MCP configuration in WorkOS

In WorkOS, open the MCP/AuthKit configuration page documented here:

- [WorkOS MCP guide](https://workos.com/docs/authkit/mcp)

### 4. Enable both MCP auth switches

In the `MCP Auth` section:

- enable `Dynamic Client Registration (DCR)`
- enable `Client ID Metadata Document (CIMD)`

Why:

- WorkOS recommends `CIMD`
- WorkOS recommends keeping `DCR` enabled for compatibility
- Claude supports `DCR`

### 5. Configure the MCP resource indicator

In `MCP resource indicators`, add your full MCP endpoint:

```text
https://your-app.vercel.app/mcp
```

Important:

- use the full `/mcp` URL
- do not use only the base domain here

### 6. Leave External Sign-in URI empty

For this repo:

- do not configure `External Sign-in URI`

Reason:

- this repo uses AuthKit as the hosted sign-in experience
- it is not using Standalone Connect

### 7. Add Claude callback URLs in WorkOS Redirects

Add both of these redirect URIs:

```text
https://claude.ai/api/mcp/auth_callback
https://claude.com/api/mcp/auth_callback
```

If WorkOS asks for a default redirect URI, use:

```text
https://claude.ai/api/mcp/auth_callback
```

## Phase 3: Configure Vercel production

### 1. Deploy the app to Vercel

This repo expects a public production deployment on Vercel.

Your final production URLs should look like:

```text
Base URL: https://your-app.vercel.app
MCP URL:  https://your-app.vercel.app/mcp
```

### Manual Vercel upload steps

If this is a brand new Vercel project or you want to upload the app manually:

1. Install the Vercel CLI if needed:

```bash
npm i -g vercel
```

2. Log in:

```bash
vercel login
```

3. From the repo root, link or create the project:

```bash
vercel link
```

4. When prompted:
   - choose your Vercel account or team
   - create a new project or connect to an existing one
   - keep the repo root as the project root

5. Do a first deploy:

```bash
vercel deploy
```

6. After the preview deploy succeeds, add the production env vars, then deploy production:

```bash
vercel deploy --prod
```

Because this repo already includes `vercel.json` and the Python entrypoint, you do not need extra build configuration beyond linking the project and setting the right environment variables.

### 2. Add production environment variables

In Vercel Project Settings → Environment Variables, add:

```text
MCP_AUTH_MODE=oauth
MCP_PUBLIC_BASE_URL=https://your-app.vercel.app
WORKOS_AUTHKIT_DOMAIN=https://your-project.authkit.app
```

Optional persistence:

```text
PROFILE_STORAGE_BACKEND=blob
```

Important:

- `MCP_PUBLIC_BASE_URL` is the base URL only
- do not include `/mcp` in `MCP_PUBLIC_BASE_URL`
- `WORKOS_AUTHKIT_DOMAIN` is your AuthKit domain, not your app URL

### 3. Make the MCP endpoint public

This is critical.

For `claude.ai`, the production `/mcp` route must be reachable from Anthropic’s cloud.

That means:

- do not leave Vercel Authentication or Deployment Protection in front of the Claude-facing production endpoint

If Vercel protection is enabled, Claude will hit Vercel’s auth wall before it can discover your MCP OAuth metadata.

### 4. Redeploy production

After setting the environment variables and making the route public, redeploy production.

## Phase 4: Connect the server in Claude

In `claude.ai`:

1. Add a new custom connector
2. Name it however you want
3. Use the full MCP URL:

```text
https://your-app.vercel.app/mcp
```

4. Leave `OAuth Client ID` empty
5. Leave `OAuth Client Secret` empty

Because WorkOS is configured with `CIMD` and `DCR`, Claude should discover the OAuth flow automatically.

### Expected Claude flow

1. Claude accepts the connector URL
2. Claude shows the connector as not yet connected
3. You click `Connect`
4. Claude redirects through WorkOS AuthKit
5. You sign in and approve access
6. Claude returns connected

## Phase 5: Validate the connector

After connecting, test the MCP server in Claude:

1. `whoami`
2. `set_profile`
3. `get_profile`

Expected results:

- `whoami` returns an authenticated identity
- `set_profile` writes the profile
- `get_profile` returns the stored profile

If Blob is enabled, the data should survive redeployments and cold starts.

## Manual path vs agent-assisted path

### Manual path

Use the dashboard and CLI directly:

- WorkOS dashboard for AuthKit and MCP settings
- Vercel dashboard for env vars and deployment protection
- Claude UI for the connector

This is the most reliable path the first time.

### Agent-assisted path with Codex or Claude Code

An agent can help with:

- verifying the repo auth mode implementation
- setting Vercel environment variables
- triggering Vercel deployments
- linking or verifying the Vercel project when the CLI or Vercel MCP plugin is authenticated
- checking whether `/mcp` and OAuth metadata endpoints are public
- writing and updating setup docs

An agent usually cannot fully replace the WorkOS dashboard steps unless you explicitly authenticate and expose the right CLI tooling, and even then the WorkOS AI installer is not the right tool for this MCP repo.

### Important note about the WorkOS AI installer

Do not use:

```bash
npx workos@latest install
```

for this repo.

Why:

- it is designed to integrate AuthKit into regular web apps
- it installs SDKs, writes routes, edits env files, and changes project code
- this repo already has its own FastMCP OAuth integration

So for this MCP server:

- WorkOS dashboard: yes
- Vercel MCP / Vercel CLI: yes
- WorkOS AI installer: no

## Common failure modes

### Claude says the connector exists but won’t connect

Usually this means the URL was accepted, but the OAuth flow cannot complete.

Check:

- the connector URL ends with `/mcp`
- Vercel protection is disabled for the production endpoint
- WorkOS redirect URIs are correct
- MCP resource indicator exactly matches the deployed `/mcp` URL

### Claude sees a Vercel authentication wall

This means Vercel is still blocking the route before the app responds.

Fix:

- remove Vercel Authentication / Deployment Protection from the production endpoint

### WorkOS redirect error

Check:

- `https://claude.ai/api/mcp/auth_callback`
- `https://claude.com/api/mcp/auth_callback`

Both should be configured in WorkOS.

### App starts locally but production fails

Check:

- `MCP_AUTH_MODE=oauth`
- `MCP_PUBLIC_BASE_URL` is set
- `WORKOS_AUTHKIT_DOMAIN` is set
- `MCP_PUBLIC_BASE_URL` does not contain `/mcp`

### OAuth works but profile data does not persist

You are probably still using ephemeral Vercel file storage.

If you want persistence, enable:

```text
PROFILE_STORAGE_BACKEND=blob
```

## Reusable checklist for future MCP servers

1. Build and test locally
2. Keep a local bearer-token mode if useful
3. Create WorkOS project
4. Enable AuthKit
5. Copy AuthKit domain
6. Enable `CIMD`
7. Enable `DCR`
8. Add MCP resource indicator with full `/mcp` URL
9. Add Claude redirect URIs
10. Set Vercel env vars
11. Disable Vercel protection for the production MCP endpoint
12. Deploy production
13. Add connector in Claude with the full `/mcp` URL
14. Test `whoami`, `set_profile`, `get_profile`

## Related docs in this repo

- [docs/workos-vercel-authkit-setup.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/workos-vercel-authkit-setup.md)
- [docs/vercel-deploy.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/vercel-deploy.md)
- [docs/claude-oauth-plan.md](/Users/REDONSX1/Documents/code/01%20personal/apex-mcp-server/docs/claude-oauth-plan.md)
