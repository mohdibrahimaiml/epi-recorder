import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { hmacHex, newApiKey, newId, newToken, nowIso, randomHex, sha256Hex, verifyHmac } from "../lib/crypto.ts";
import { createSession, sessionCookie, clearSessionCookie, membershipRole, userFromRequest } from "../lib/auth.ts";
import { checkRateLimit, d1CounterStore, clientIp } from "../lib/ratelimit.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";

const app = new Hono<{ Bindings: Env }>();

const STATE_TTL_MS = 10 * 60_000;

/** GitHub rejects api.github.com requests without a User-Agent (403).
 *  Cloudflare Workers do not add one automatically, so every GitHub
 *  fetch must carry it explicitly (token exchange included). */
export const GITHUB_USER_AGENT = "epi-cloud";

function githubHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
    "User-Agent": GITHUB_USER_AGENT,
  };
}

function stateCookie(name: string, value: string, maxAgeSec: number): string {
  return `${name}=${value}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${maxAgeSec}`;
}

function parseCookies(header: string | null | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  if (!header) return out;
  for (const part of header.split(";")) {
    const i = part.indexOf("=");
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

async function loginLimited(db: D1Database, req: Request): Promise<Response | null> {
  const r = await checkRateLimit(d1CounterStore(db), `login:${clientIp(req)}`, 10, 60);
  if (!r.ok) return Response.json({ error: { code: "rate_limited", message: "Too many logins. Retry soon." } }, { status: 429 });
  return null;
}

/** Find-or-create user; link same email across providers only when BOTH
 *  the stored email and the new provider email are verified.
 *  Never falls back to an unverified GitHub email for linking (prevents
 *  pre-registration takeover: attacker registers victim email unverified,
 *  victim later signs in verified and must get a separate account). */
export async function findOrLinkUser(
  db: D1Database,
  provider: "github" | "google",
  providerUserId: string,
  email: string | null,
  emailVerified: boolean,
  displayName: string | null,
): Promise<string> {
  const now = nowIso();
  const normalizedEmail = email?.trim().toLowerCase() || null;
  const existing = await db
    .prepare("SELECT user_id FROM identities WHERE provider = ? AND provider_user_id = ?")
    .bind(provider, providerUserId)
    .first<{ user_id: string }>();
  if (existing) {
    if (normalizedEmail) {
      if (emailVerified) {
        await db.prepare("UPDATE users SET email = ?, email_verified = 1 WHERE id = ?").bind(normalizedEmail, existing.user_id).run();
      } else {
        const current = await db.prepare("SELECT email FROM users WHERE id = ?").bind(existing.user_id).first<{ email: string | null }>();
        if (!current?.email) {
          await db.prepare("UPDATE users SET email = ? WHERE id = ?").bind(normalizedEmail, existing.user_id).run();
        }
        // Never overwrite a verified email with an unverified one.
      }
    }
    return existing.user_id;
  }
  if (normalizedEmail && emailVerified) {
    const byEmail = await db.prepare("SELECT id, email_verified FROM users WHERE email = ?").bind(normalizedEmail).first<{ id: string; email_verified: number | null }>();
    if (byEmail && Number(byEmail.email_verified) === 1) {
      await db
        .prepare("INSERT INTO identities (provider, provider_user_id, user_id) VALUES (?, ?, ?)")
        .bind(provider, providerUserId, byEmail.id)
        .run();
      return byEmail.id;
    }
    // Stored account unverified (or missing flag): do NOT link. Fall through
    // to create a separate verified account with the same email string.
  }
  const id = newId("usr");
  await db.prepare("INSERT INTO users (id, email, display_name, email_verified, created_at) VALUES (?, ?, ?, ?, ?)").bind(id, normalizedEmail, displayName, emailVerified && normalizedEmail ? 1 : 0, now).run();
  await db.prepare("INSERT INTO identities (provider, provider_user_id, user_id) VALUES (?, ?, ?)").bind(provider, providerUserId, id).run();
  return id;
}

// GitHub: state param. Google: state + PKCE (S256).
app.get("/github", async (c) => {
  const limited = await loginLimited(c.env.DB, c.req.raw);
  if (limited) return limited;
  if (!c.env.GITHUB_CLIENT_ID) return c.json({ error: { code: "oauth_not_configured", message: "GitHub login is not configured yet." } }, 503);
  const state = newToken();
  const sig = await hmacHex(c.env.SESSION_KEY ?? "unconfigured", state);
  const url = new URL("https://github.com/login/oauth/authorize");
  url.searchParams.set("client_id", c.env.GITHUB_CLIENT_ID);
  url.searchParams.set("state", `${state}.${sig}`);
  url.searchParams.set("scope", "read:user user:email");
  return new Response(null, {
    status: 302,
    headers: { Location: url.toString(), "Set-Cookie": stateCookie("epi_oauth_state", state, 600) },
  });
});

app.get("/github/callback", async (c) => {
  const limited = await loginLimited(c.env.DB, c.req.raw);
  if (limited) return limited;
  const q = z.object({ code: z.string().min(1), state: z.string().min(1) }).safeParse({
    code: c.req.query("code"),
    state: c.req.query("state"),
  });
  if (!q.success) return c.json({ error: { code: "bad_request", message: "Missing code/state." } }, 400);
  const cookies = parseCookies(c.req.header("Cookie"));
  const [state, sig] = q.data.state.split(".");
  if (!state || !sig || cookies["epi_oauth_state"] !== state) {
    return c.json({ error: { code: "bad_state", message: "OAuth state mismatch. Retry login." } }, 400);
  }
  if (!(await verifyHmac(`sha256=${sig}`, c.env.SESSION_KEY ?? "unconfigured", state))) {
    return c.json({ error: { code: "bad_state", message: "OAuth state mismatch. Retry login." } }, 400);
  }
  const tok = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", "User-Agent": GITHUB_USER_AGENT },
    body: JSON.stringify({ client_id: c.env.GITHUB_CLIENT_ID, client_secret: c.env.GITHUB_CLIENT_SECRET, code: q.data.code }),
  });
  if (!tok.ok) return c.json({ error: { code: "oauth_exchange_failed", message: "GitHub code exchange failed." } }, 502);
  const tokJson = (await tok.json()) as { access_token?: string };
  if (!tokJson.access_token) return c.json({ error: { code: "oauth_exchange_failed", message: "GitHub code exchange failed." } }, 502);
  const me = await fetch("https://api.github.com/user", { headers: githubHeaders(tokJson.access_token) });
  const emails = await fetch("https://api.github.com/user/emails", { headers: githubHeaders(tokJson.access_token) });
  if (!me.ok || !emails.ok) {
    console.error(`oauth github profile failed: user=${me.status} emails=${emails.status}`);
    return c.json({ error: { code: "oauth_profile_failed", message: `GitHub profile fetch failed (user ${me.status}, emails ${emails.status}).` } }, 502);
  }
  const profile = (await me.json()) as { id: number; login?: string; name?: string };
  const list = (await emails.json()) as Array<{ email: string; verified: boolean; primary: boolean }>;
  const primary = list.find((e) => e.primary) ?? list.find((e) => e.verified) ?? list[0];
  const userId = await findOrLinkUser(c.env.DB, "github", String(profile.id), primary?.email ?? null, primary?.verified ?? false, profile.name ?? profile.login ?? null);
  const sess = await createSession(c.env.DB, userId);
  return new Response(null, {
    status: 302,
    headers: { Location: c.env.APP_ORIGIN + "/", "Set-Cookie": sessionCookie(sess.raw, c.env.APP_ORIGIN) },
  });
});

function b64url(buf: Uint8Array): string {
  return btoa(String.fromCharCode(...buf)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

app.get("/google", async (c) => {
  const limited = await loginLimited(c.env.DB, c.req.raw);
  if (limited) return limited;
  if (!c.env.GOOGLE_CLIENT_ID) return c.json({ error: { code: "oauth_not_configured", message: "Google login is not configured yet." } }, 503);
  const state = newToken();
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge = b64url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))));
  const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  url.searchParams.set("client_id", c.env.GOOGLE_CLIENT_ID);
  url.searchParams.set("redirect_uri", `${c.env.APP_ORIGIN}/auth/google/callback`);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "openid email profile");
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  const headers = new Headers({ Location: url.toString() });
  headers.append("Set-Cookie", stateCookie("epi_oauth_state", state, 600));
  headers.append("Set-Cookie", stateCookie("epi_oauth_verifier", verifier, 600));
  return new Response(null, { status: 302, headers });
});

app.get("/google/callback", async (c) => {
  const limited = await loginLimited(c.env.DB, c.req.raw);
  if (limited) return limited;
  const q = z.object({ code: z.string().min(1), state: z.string().min(1) }).safeParse({
    code: c.req.query("code"),
    state: c.req.query("state"),
  });
  if (!q.success) return c.json({ error: { code: "bad_request", message: "Missing code/state." } }, 400);
  const cookies = parseCookies(c.req.header("Cookie"));
  if (!cookies["epi_oauth_state"] || cookies["epi_oauth_state"] !== q.data.state || !cookies["epi_oauth_verifier"]) {
    return c.json({ error: { code: "bad_state", message: "OAuth state mismatch. Retry login." } }, 400);
  }
  const tok = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: c.env.GOOGLE_CLIENT_ID ?? "",
      client_secret: c.env.GOOGLE_CLIENT_SECRET ?? "",
      code: q.data.code,
      grant_type: "authorization_code",
      redirect_uri: `${c.env.APP_ORIGIN}/auth/google/callback`,
      code_verifier: cookies["epi_oauth_verifier"],
    }),
  });
  if (!tok.ok) return c.json({ error: { code: "oauth_exchange_failed", message: "Google code exchange failed." } }, 502);
  const tokJson = (await tok.json()) as { access_token?: string };
  if (!tokJson.access_token) return c.json({ error: { code: "oauth_exchange_failed", message: "Google code exchange failed." } }, 502);
  const me = await fetch("https://openidconnect.googleapis.com/v1/userinfo", {
    headers: { Authorization: `Bearer ${tokJson.access_token}` },
  });
  if (!me.ok) {
    console.error(`oauth google profile failed: userinfo=${me.status}`);
    return c.json({ error: { code: "oauth_profile_failed", message: `Google profile fetch failed (userinfo ${me.status}).` } }, 502);
  }
  const profile = (await me.json()) as { sub: string; email?: string; email_verified?: boolean; name?: string };
  const userId = await findOrLinkUser(c.env.DB, "google", profile.sub, profile.email ?? null, profile.email_verified === true, profile.name ?? null);
  const sess = await createSession(c.env.DB, userId);
  return new Response(null, {
    status: 302,
    headers: { Location: c.env.APP_ORIGIN + "/", "Set-Cookie": sessionCookie(sess.raw, c.env.APP_ORIGIN) },
  });
});

app.post("/logout", async (c) => {
  const cookies = parseCookies(c.req.header("Cookie"));
  const raw = cookies["epi_session"];
  if (raw) await c.env.DB.prepare("DELETE FROM sessions WHERE id_hash = ?").bind(await sha256Hex(raw)).run();
  return new Response(null, { status: 204, headers: { "Set-Cookie": clearSessionCookie() } });
});

// Device-code flow for `epi cloud login` (no flags).
// CLI polls; browser authorizes with a session cookie. Key is push-only.
const DEVICE_TTL_MS = 10 * 60_000;

app.post("/device/start", async (c) => {
  const limited = await loginLimited(c.env.DB, c.req.raw);
  if (limited) return limited;
  const code = newToken();
  const now = Date.now();
  await c.env.DB.prepare(
    "INSERT INTO device_codes (code, status, created_at, expires_at) VALUES (?, 'pending', ?, ?)",
  )
    .bind(code, new Date(now).toISOString(), new Date(now + DEVICE_TTL_MS).toISOString())
    .run();
  return c.json(
    { device_code: code, verification_url: `${c.env.APP_ORIGIN}/auth/device?code=${code}`, expires_at: new Date(now + DEVICE_TTL_MS).toISOString() },
    201,
  );
});

app.get("/device/:code/status", async (c) => {
  const limited = await loginLimited(c.env.DB, c.req.raw);
  if (limited) return limited;
  const row = await c.env.DB.prepare("SELECT status, org_id, api_key_raw, expires_at FROM device_codes WHERE code = ?")
    .bind(c.req.param("code"))
    .first<{ status: string; org_id: string | null; api_key_raw: string | null; expires_at: string }>();
  if (!row) return c.json({ error: { code: "not_found", message: "Unknown device code." } }, 404);
  if (row.expires_at <= nowIso()) return c.json({ status: "expired" });
  if (row.status !== "authorized") return c.json({ status: "pending" });
  return c.json({ status: "authorized", org_id: row.org_id, api_key: row.api_key_raw, url: c.env.APP_ORIGIN });
});

// Browser page: "Authorize this computer". Plain HTML, no tracking.
app.get("/device", async (c) => {
  const code = c.req.query("code") ?? "";
  const esc = (s: string) =>
    s.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!);
  const user = await userFromRequest(c.env.DB, c.req.raw).catch(() => null);
  if (!user) {
    return c.html(
      `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow">` +
        `<meta name="viewport" content="width=device-width,initial-scale=1"><title>Authorize this computer — EPI Cloud</title></head>` +
        `<body style="font-family:system-ui,sans-serif;max-width:36rem;margin:4rem auto;padding:0 1rem;line-height:1.6">` +
        `<h1>Authorize this computer</h1><p>Sign in first, then authorize.</p>` +
        `<p><a href="/auth/github">Sign in with GitHub</a></p>` +
        `<p style="color:#666;font-size:.85rem">Device code: <code>${esc(code.slice(0, 12))}…</code></p>` +
        `</body></html>`,
    );
  }
  return c.html(
    `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow">` +
      `<meta name="viewport" content="width=device-width,initial-scale=1"><title>Authorize this computer — EPI Cloud</title>` +
      `<style>body{font-family:system-ui,sans-serif;max-width:36rem;margin:4rem auto;padding:0 1rem;line-height:1.6}` +
      `button{font:inherit;padding:.5rem 1.2rem;cursor:pointer}select,input{font:inherit;padding:.4rem;width:100%;margin:.4rem 0}` +
      `code{background:#f0f0f0;padding:.1rem .3rem}</style></head>` +
      `<body><h1>Authorize this computer</h1>` +
      `<p>This gives your terminal a <strong>push-only</strong> key (<code>epik_…</code>). It can push selected runs, nothing else. Revoke anytime.</p>` +
      `<label>Workspace (org)<select id="org"></select></label>` +
      `<p><button id="go" type="button">Authorize this computer</button></p>` +
      `<p id="msg" role="status"></p>` +
      `<p><a href="/">Back to setup</a></p>` +
      `<script>var CODE=${JSON.stringify(code)};` +
      `fetch("/v1/orgs",{credentials:"same-origin"}).then(function(r){return r.json()}).then(function(j){` +
      `var s=document.getElementById("org");(j.orgs||[]).forEach(function(o){var el=document.createElement("option");el.value=o.id;el.textContent=o.name+" ("+o.id+")";s.appendChild(el)});` +
      `if(!s.options.length){document.getElementById("msg").textContent="No workspace yet — create one below on the front page first."}});` +
      `document.getElementById("go").onclick=function(){var o=document.getElementById("org").value;var m=document.getElementById("msg");m.textContent="Authorizing…";` +
      `fetch("/auth/device/authorize",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({device_code:CODE,org_id:o})})` +
      `.then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j}})}).then(function(x){m.textContent=x.ok?"Authorized — return to your terminal.":"Failed: "+((x.j&&x.j.error&&x.j.error.message)||"unknown")})` +
      `.catch(function(){m.textContent="Failed."})}};</script>` +
      `</body></html>`,
  );
});

app.post("/device/authorize", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const body = z.object({ device_code: z.string().min(10).max(256), org_id: z.string().min(1).max(128) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "device_code and org_id required." } }, 400);
  const dev = await c.env.DB.prepare("SELECT status, expires_at FROM device_codes WHERE code = ?")
    .bind(body.data.device_code)
    .first<{ status: string; expires_at: string }>();
  if (!dev) return c.json({ error: { code: "not_found", message: "Unknown device code." } }, 404);
  if (dev.expires_at <= nowIso()) return c.json({ error: { code: "expired", message: "Device code expired. Run `epi cloud login` again." } }, 410);
  const role = await membershipRole(c.env.DB, body.data.org_id, user.id);
  if (role !== "owner" && role !== "member") return c.json({ error: { code: "forbidden", message: "Owners or members only." } }, 403);
  const key = newApiKey();
  const id = newId("key");
  await c.env.DB.prepare(
    "INSERT INTO api_keys (id, org_id, prefix, key_hash, scopes, created_by, created_at, last_used_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
  )
    .bind(id, body.data.org_id, key.prefix, await sha256Hex(key.raw), "push", user.id, nowIso())
    .run();
  await c.env.DB.prepare("UPDATE device_codes SET status = 'authorized', org_id = ?, api_key_id = ?, api_key_raw = ?, authorized_at = ? WHERE code = ?")
    .bind(body.data.org_id, id, key.raw, nowIso(), body.data.device_code)
    .run();
  await auditLog(d1AuditDb(c.env.DB), { orgId: body.data.org_id, actor: `user:${user.id}`, action: "api_key.create", detail: `${id} scopes=push via device` });
  return c.json({ ok: true });
});

void STATE_TTL_MS;
void randomHex;

export default app;
