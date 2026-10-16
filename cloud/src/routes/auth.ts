import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { hmacHex, newId, newToken, nowIso, randomHex, sha256Hex, verifyHmac } from "../lib/crypto.ts";
import { createSession, sessionCookie, clearSessionCookie } from "../lib/auth.ts";
import { checkRateLimit, d1CounterStore, clientIp } from "../lib/ratelimit.ts";

const app = new Hono<{ Bindings: Env }>();

const STATE_TTL_MS = 10 * 60_000;

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

/** Find-or-create user; link same email across providers only when the
 *  provider email is verified (confirmed login with both). */
async function findOrLinkUser(
  db: D1Database,
  provider: "github" | "google",
  providerUserId: string,
  email: string | null,
  emailVerified: boolean,
  displayName: string | null,
): Promise<string> {
  const now = nowIso();
  const existing = await db
    .prepare("SELECT user_id FROM identities WHERE provider = ? AND provider_user_id = ?")
    .bind(provider, providerUserId)
    .first<{ user_id: string }>();
  if (existing) {
    if (email) await db.prepare("UPDATE users SET email = ? WHERE id = ?").bind(email, existing.user_id).run();
    return existing.user_id;
  }
  if (email && emailVerified) {
    const byEmail = await db.prepare("SELECT id FROM users WHERE email = ?").bind(email).first<{ id: string }>();
    if (byEmail) {
      await db
        .prepare("INSERT INTO identities (provider, provider_user_id, user_id) VALUES (?, ?, ?)")
        .bind(provider, providerUserId, byEmail.id)
        .run();
      return byEmail.id;
    }
  }
  const id = newId("usr");
  await db.prepare("INSERT INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)").bind(id, email, displayName, now).run();
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
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: c.env.GITHUB_CLIENT_ID, client_secret: c.env.GITHUB_CLIENT_SECRET, code: q.data.code }),
  });
  if (!tok.ok) return c.json({ error: { code: "oauth_exchange_failed", message: "GitHub code exchange failed." } }, 502);
  const tokJson = (await tok.json()) as { access_token?: string };
  if (!tokJson.access_token) return c.json({ error: { code: "oauth_exchange_failed", message: "GitHub code exchange failed." } }, 502);
  const me = await fetch("https://api.github.com/user", { headers: { Authorization: `Bearer ${tokJson.access_token}`, Accept: "application/json" } });
  const emails = await fetch("https://api.github.com/user/emails", { headers: { Authorization: `Bearer ${tokJson.access_token}`, Accept: "application/json" } });
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

void STATE_TTL_MS;
void randomHex;

export default app;
