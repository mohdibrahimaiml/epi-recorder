# ChatGPT plugin: connect + acceptance test

The EPI mechanism is implemented and tested (`epi_mcp/`, 17 tests).
This page covers the remaining deployment and the one test that can
only run inside ChatGPT.

## Zero-config model

Normal users install the app and say "seal this run" — no URLs, no
tokens, no key names. This works because:

- The chat host authenticates the user; the server verifies the
  credential and binds the call to that identity. Two modes:
  **OAuth code flow** (`/.well-known/oauth-authorization-server`,
  dynamic registration, PKCE S256, refresh tokens) for chat hosts
  like ChatGPT that offer OAuth-or-nothing — the approver gets a
  stable pseudonymous subject, seals bind to it via auto-created
  per-subject keys. **Static `EPI_MCP_TOKEN`** for single-operator
  setups. Raw identity values are never stored, only hashes.
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

OAuth honesty note: our approval binds a *pseudonymous per-approval
subject* (control of the approving session, nothing more). It is not
a verified human identity.

Set `EPI_OAUTH_SECRET` (random, 32+ characters). It signs OAuth tokens
and seeds each caller's signing key, so:

- registered clients and refresh tokens are signed tokens and survive
  restarts and a sleeping free-tier host (no database needed);
- authorization codes live 10 minutes in memory, so a restart in the
  middle of an approval forces one re-approval;
- a caller's signer stays the same across restarts, so
  `epi keys trust <file>.epi` pinning lasts. Without the secret the
  signing key lives on the host's disk and changes whenever that disk
  is reset.

The public connector is open by design: anyone can connect and seal in two
clicks, and a seal is a pseudonymous signature, not a verified identity. Sealed
files are capped per caller (50 files / 200 MB) and server-wide (1 GB) while they
wait for download, and deleted 24 h after sealing, so an open server cannot be
filled up. Running a private server for a team? Set the optional
`EPI_APPROVE_PASSPHRASE` and the approve page will ask for it. Leave it unset for
a public server.

### Optional: name the person who sealed it

Claude and ChatGPT never tell this server who the user is, so by default a seal
carries a pseudonym. To put a verified person in the file, configure an OpenID
Connect provider (Google, Microsoft Entra, Okta, Auth0, Keycloak):

| Variable | Value |
|---|---|
| `EPI_IDP_ISSUER` | e.g. `https://accounts.google.com` |
| `EPI_IDP_CLIENT_ID` / `EPI_IDP_CLIENT_SECRET` | from the provider's OAuth app |
| `EPI_IDP_NAME` | button label, e.g. `Google` |

Register `<EPI_MCP_PUBLIC_URL>/oauth/idp/callback` as the redirect URI. The approve
page then keeps its one-click button and adds "Sign in and approve". A signed-in
person gets the same signing key every time they reconnect, and the sealed file's
`environment.json` records the provider and (if they leave the box ticked) their
email. The viewer and `epi verify` show it only when the file's integrity and
signature check out.

What it proves: the sealing server saw that person sign in with that provider. What
it does not: who typed the conversation, or anything Claude or ChatGPT produced.
Anyone relying on it should pin the sealing server's signer (`epi keys trust`).

Treat the secret like a root key: whoever holds it can mint tokens and
sign as any caller. Rotating it invalidates all tokens and changes every
signer. Nothing is revocable before expiry except by rotating it. Do not
rely on `EPI_MCP_TOKEN` alone in production.
OIDC (`EPI_OIDC_*`) remains available for issuers with real user
identity when that integration arrives.
