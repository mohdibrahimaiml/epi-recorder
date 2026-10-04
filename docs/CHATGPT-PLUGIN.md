# ChatGPT plugin: connect + acceptance test

The EPI mechanism is implemented and tested (`epi_mcp/`, 17 tests).
This page covers the remaining deployment and the one test that can
only run inside ChatGPT.

## Zero-config model

Normal users install the app and say "seal this run" — no URLs, no
tokens, no key names. This works because:

- The chat host authenticates the user; the server verifies the
  credential (OIDC via `EPI_OIDC_*`, static `EPI_MCP_TOKEN` for
  single-operator setups) and binds the call to that identity.
- The first seal auto-creates a per-caller key (`user-<id>`); raw
  identity values are never stored, only hashes.
- Anonymous callers may verify and export, but sealing refuses
  without an identity — a seal is always attributable to someone.

## 1. Deploy the public endpoint

`render.yaml` already declares the `epi-mcp` service. In the Render
dashboard:

1. New → Web Service → this repo (deploys `epi-mcp` alongside `epi-verify`).
2. Set `EPI_MCP_TOKEN` to a long random secret.
3. Set `EPI_MCP_PUBLIC_URL` to the service URL, e.g.
   `https://epi-mcp.onrender.com` (no trailing slash).
4. Deploy. The MCP endpoint is `<url>/mcp`.

Rules: never deploy without `EPI_MCP_TOKEN` (the server refuses a public
bind without it). Tunnels are for dev only, never for distribution.

## 2. Connect in ChatGPT

1. Settings → Security and login → Developer mode.
2. Plugins → `+` → enter `https://<your-host>/mcp`.
3. New chat → select the EPI plugin.

## 3. Acceptance test (the only unproven step)

> Seal this agent run into an EPI evidence artifact.

Then:

1. Obtain the returned `.epi` — via the `download_url` first; the base64
   bytes are the fallback.
2. Run locally: `epi verify <file>.epi`
3. Expected: `Integrity: VALID`, `Signature: VALID`, `scope:
   caller-provided`, identity LOW until the key is pinned.

Interpretation:

| Result | Meaning |
|--------|---------|
| VALID / VALID file in hand | Ship it |
| Bytes returned, no downloadable file | Report back — hosted-link flow needs work |
| Connection / tool error | Paste the exact error — transport, auth, or deploy config |
