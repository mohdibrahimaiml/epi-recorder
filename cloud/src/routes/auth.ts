import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { hmacHex, newApiKey, newId, newToken, nowIso, randomHex, sha256Hex, verifyHmac } from "../lib/crypto.ts";
import { createSession, sessionCookie, clearSessionCookie, membershipRole, userFromRequest } from "../lib/auth.ts";
import { ensureCustomerInbox } from "../lib/customerInbox.ts";
import { checkRateLimit, d1CounterStore, clientIp } from "../lib/ratelimit.ts";
import { auditLog, d1AuditDb } from "../lib/audit.ts";
import { openSecret, sealSecret } from "../lib/secretbox.ts";
import { esc, page } from "../ui.ts";
import { liveInvite } from "./invites.ts";

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

// Polling has its own bucket: the CLI checks every few seconds while it
// waits, and that must never lock out interactive sign-in on the same IP.
async function devicePollLimited(db: D1Database, req: Request): Promise<Response | null> {
  const r = await checkRateLimit(d1CounterStore(db), `devicepoll:${clientIp(req)}`, 60, 60);
  if (!r.ok) {
    return Response.json(
      { error: { code: "rate_limited", message: "Polling too fast. Back off and retry." } },
      { status: 429, headers: { "Retry-After": String(r.retryAfterSec) } },
    );
  }
  return null;
}

/** Safe post-login redirect target: relative paths only (open-redirect safe). */
export function safeNext(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const n = raw.trim();
  if (n.length < 1 || n.length > 200) return null;
  if (!n.startsWith("/") || n.startsWith("//")) return null;
  if (n.includes("\\") || /[\u0000-\u001f\u007f]/.test(n)) return null;
  return n;
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
  const headers = new Headers({ Location: url.toString() });
  headers.append("Set-Cookie", stateCookie("epi_oauth_state", state, 600));
  const next = safeNext(c.req.query("next"));
  if (next) headers.append("Set-Cookie", stateCookie("epi_oauth_next", encodeURIComponent(next), 600));
  return new Response(null, { status: 302, headers });
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
  const dest = safeNext(cookies["epi_oauth_next"] ? decodeURIComponent(cookies["epi_oauth_next"]!) : null) ?? "/";
  const out = new Headers({ Location: c.env.APP_ORIGIN + dest });
  out.append("Set-Cookie", sessionCookie(sess.raw, c.env.APP_ORIGIN));
  out.append("Set-Cookie", stateCookie("epi_oauth_state", "", 0));
  out.append("Set-Cookie", stateCookie("epi_oauth_next", "", 0));
  return new Response(null, { status: 302, headers: out });
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
  const next = safeNext(c.req.query("next"));
  if (next) headers.append("Set-Cookie", stateCookie("epi_oauth_next", encodeURIComponent(next), 600));
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
  const dest = safeNext(cookies["epi_oauth_next"] ? decodeURIComponent(cookies["epi_oauth_next"]!) : null) ?? "/";
  const out = new Headers({ Location: c.env.APP_ORIGIN + dest });
  out.append("Set-Cookie", sessionCookie(sess.raw, c.env.APP_ORIGIN));
  out.append("Set-Cookie", stateCookie("epi_oauth_state", "", 0));
  out.append("Set-Cookie", stateCookie("epi_oauth_verifier", "", 0));
  out.append("Set-Cookie", stateCookie("epi_oauth_next", "", 0));
  return new Response(null, { status: 302, headers: out });
});

app.post("/logout", async (c) => {
  const cookies = parseCookies(c.req.header("Cookie"));
  const raw = cookies["epi_session"];
  if (raw) await c.env.DB.prepare("DELETE FROM sessions WHERE id_hash = ?").bind(await sha256Hex(raw)).run();
  return new Response(null, { status: 204, headers: { "Set-Cookie": clearSessionCookie() } });
});

// Public sign-in probe for the marketing-site nav (epilabs.org): answers
// only whether this request carries a valid session — never identity.
// CORS is granted solely to the exact site origins; any other Origin gets
// the same JSON with no CORS headers, so a foreign page cannot read it.
// The session cookie is SameSite=Lax and epilabs.org is the same site, so
// the browser sends it on this same-site fetch.
const SITE_ORIGINS = ["https://epilabs.org", "https://www.epilabs.org"];

app.get("/session", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw).catch(() => null);
  const headers: Record<string, string> = { "Cache-Control": "no-store", "Content-Type": "application/json" };
  const origin = c.req.header("Origin");
  if (origin && (SITE_ORIGINS as string[]).includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Credentials"] = "true";
    headers["Vary"] = "Origin";
  }
  return new Response(JSON.stringify({ signed_in: !!user }), { status: 200, headers });
});

// Human page behind an invite link. Shows which workspace and role, makes the
// person sign in (coming back here afterwards), and only lets the invited
// email accept. The token stays in the path; it is never put in a cookie.
app.get("/invite/:token", async (c) => {
  const token = c.req.param("token");
  const inv = /^[A-Za-z0-9_-]{16,128}$/.test(token) ? await liveInvite(c.env.DB, token) : null;
  if (!inv) {
    return c.html(page("Invite — EPI Cloud",
      `<span class="tag">Invite</span><h1>This invite can't be used</h1>` +
      `<p class="lede">It may have expired (invites last 7 days), been used already, or been cancelled. Ask the person who invited you for a new link.</p>` +
      `<p><a class="btn btn-sec" href="/">Go to EPI Cloud</a></p>`), 404);
  }
  const org = await c.env.DB.prepare("SELECT name FROM orgs WHERE id = ?").bind(inv.org_id).first<{ name: string }>();
  const orgName = org?.name ?? "a workspace";
  const roleWords: Record<string, string> = {
    owner: "an owner (can manage customers, computers, share links and the team)",
    member: "a member (can see runs and connect computers)",
    viewer: "a viewer (can see runs)",
  };
  const head =
    `<span class="tag">Invite</span><h1>Join ${esc(orgName)} on EPI Cloud</h1>` +
    `<p class="lede">You were invited as ${esc(roleWords[inv.role] ?? inv.role)}. This invite is for <strong>${esc(inv.email)}</strong> and expires ${esc(new Date(inv.expires_at).toUTCString())}.</p>`;
  const user = await userFromRequest(c.env.DB, c.req.raw);
  const next = encodeURIComponent(`/auth/invite/${token}`);
  if (!user) {
    return c.html(page("Invite — EPI Cloud",
      head +
      `<p>Sign in with the account for <strong>${esc(inv.email)}</strong>, then you'll come back here to join.</p>` +
      `<p><a class="btn btn-pri" href="/auth/github?next=${next}">Sign in with GitHub</a></p>` +
      (c.env.GOOGLE_CLIENT_ID ? `<p><a class="btn btn-sec" href="/auth/google?next=${next}">Sign in with Google</a></p>` : ``)));
  }
  const matches = !!user.email && user.email.trim().toLowerCase() === inv.email.trim().toLowerCase();
  if (!matches) {
    return c.html(page("Invite — EPI Cloud",
      head +
      `<p class="warn">You're signed in as <strong>${esc(user.email ?? "an account without an email")}</strong>, but this invite is for <strong>${esc(inv.email)}</strong>. Sign out, then open this link again and sign in with the invited account.</p>` +
      `<p><button type="button" class="btn btn-sec" id="so">Sign out</button></p>`,
      { script: `document.getElementById("so").onclick=function(){fetch("/auth/logout",{method:"POST",credentials:"same-origin"}).then(function(){location.reload();},function(){location.reload();});};` }));
  }
  return c.html(page("Invite — EPI Cloud",
    head +
    `<p><button type="button" class="btn btn-pri" id="go">Join ${esc(orgName)}</button></p><p id="msg" class="small" role="status"></p>`,
    {
      script:
        `var t=${JSON.stringify(token)};document.getElementById("go").onclick=function(){var b=this;b.disabled=true;var m=document.getElementById("msg");m.textContent="Joining\\u2026";` +
        `fetch("/v1/invites/"+encodeURIComponent(t)+"/accept",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:"{}"})` +
        `.then(function(r){return r.json().catch(function(){return {};}).then(function(j){if(r.ok){location.href="/";return;}b.disabled=false;m.textContent=(j&&j.error&&j.error.message)||"Couldn't join \\u2014 try again.";});},function(){b.disabled=false;m.textContent="Couldn't reach EPI Cloud \\u2014 check your connection and try again.";});};`,
    }));
});

// Device-code flow for `epi cloud login` (no flags), RFC 8628 style.
// The CLI keeps the long device secret and shows a short user code
// (e.g. WDJB-MJHT). The user types that code on /auth/device — the secret
// never appears in a URL, so a forwarded link alone authorizes nothing.
// Keys minted here are push-only, sealed at rest, single-retrieval.
// The browser also asks *which customer this computer records
// for*; the witness URL + secret travel back with the key so the user
// never copies a secret.
const DEVICE_TTL_MS = 10 * 60_000;
const DEVICE_POLL_SECONDS = 5;

/** Oldest CLI the cloud still walks through setup. Older CLIs get a loud
 * nudge to `pip install -U epi-recorder` instead of a silent dead end. */
export const MIN_CLI_VERSION = "4.6.1";

const USER_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";

function newUserCode(): string {
  const buf = crypto.getRandomValues(new Uint8Array(8));
  const chars = Array.from(buf, (b) => USER_CODE_ALPHABET[b % USER_CODE_ALPHABET.length]!);
  return `${chars.slice(0, 4).join("")}-${chars.slice(4).join("")}`;
}

/** Normalize typed codes ("wdjb mjht" -> "WDJB-MJHT"), null when malformed. */
export function normalizeUserCode(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const clean = raw.toUpperCase().replace(/[^A-Z2-9]/g, "");
  if (clean.length !== 8) return null;
  if (![...clean].every((ch) => USER_CODE_ALPHABET.includes(ch))) return null;
  return `${clean.slice(0, 4)}-${clean.slice(4)}`;
}

async function purgeExpiredDevices(db: D1Database): Promise<void> {
  try {
    await db.prepare("DELETE FROM device_codes WHERE expires_at <= ?").bind(nowIso()).run();
  } catch {
    // Best effort: expiry is also enforced per-row below.
  }
}

/** Seal a device key for temporary storage (prefix-tagged, back-compatible). */
async function sealDeviceKey(env: Env, raw: string): Promise<string> {
  if (env.INBOX_SECRET_KEY) return `enc:${await sealSecret(env.INBOX_SECRET_KEY, raw)}`;
  return `raw:${raw}`;
}

async function openDeviceKey(env: Env, stored: string): Promise<string> {
  if (storeIsSealed(stored)) {
    if (!env.INBOX_SECRET_KEY) throw new Error("Device key encryption is not configured.");
    return openSecret(env.INBOX_SECRET_KEY, stored.slice("enc:".length));
  }
  return stored.startsWith("raw:") ? stored.slice("raw:".length) : stored;
}

function storeIsSealed(stored: string): boolean {
  return stored.startsWith("enc:");
}

app.post("/device/start", async (c) => {
  const limited = await loginLimited(c.env.DB, c.req.raw);
  if (limited) return limited;
  await purgeExpiredDevices(c.env.DB);
  const nameRaw = z.object({
    device_name: z.string().trim().min(1).max(64).optional(),
    // The key this computer already holds (re-login). Only its hash is kept.
    replaces_key: z.string().startsWith("epik_").max(200).optional(),
  }).safeParse(await c.req.json().catch(() => null));
  const deviceName = nameRaw.success ? (nameRaw.data.device_name ?? null) : null;
  const replacesHash = nameRaw.success && nameRaw.data.replaces_key ? await sha256Hex(nameRaw.data.replaces_key) : null;
  const code = newToken();
  const now = Date.now();
  let userCode = "";
  for (let i = 0; i < 5; i++) {
    const candidate = newUserCode();
    try {
      await c.env.DB.prepare(
        "INSERT INTO device_codes (code, user_code, device_name, status, created_at, expires_at, replaces_key_hash) VALUES (?, ?, ?, 'pending', ?, ?, ?)",
      )
        .bind(code, candidate, deviceName, new Date(now).toISOString(), new Date(now + DEVICE_TTL_MS).toISOString(), replacesHash)
        .run();
      userCode = candidate;
      break;
    } catch {
      // user_code collision: retry with a fresh code.
    }
  }
  if (!userCode) return c.json({ error: { code: "internal", message: "Could not start login. Retry." } }, 500);
  return c.json(
    {
      device_code: code,
      user_code: userCode,
      verification_url: `${c.env.APP_ORIGIN}/auth/device`,
      expires_at: new Date(now + DEVICE_TTL_MS).toISOString(),
      interval: DEVICE_POLL_SECONDS,
      min_cli_version: MIN_CLI_VERSION,
    },
    201,
  );
});

app.get("/device/:code/status", async (c) => {
  const limited = await devicePollLimited(c.env.DB, c.req.raw);
  if (limited) return limited;
  const row = await c.env.DB.prepare("SELECT status, org_id, api_key_raw, customer_label, witness_url, witness_secret_enc, expires_at FROM device_codes WHERE code = ?")
    .bind(c.req.param("code"))
    .first<{ status: string; org_id: string | null; api_key_raw: string | null; customer_label: string | null; witness_url: string | null; witness_secret_enc: string | null; expires_at: string }>();
  if (!row) return c.json({ error: { code: "not_found", message: "Unknown device code." } }, 404);
  if (row.expires_at <= nowIso()) {
    await c.env.DB.prepare("DELETE FROM device_codes WHERE code = ?").bind(c.req.param("code")).run();
    return c.json({ status: "expired" });
  }
  if (row.status !== "authorized") return c.json({ status: "pending" });
  if (!row.api_key_raw) return c.json({ status: "authorized", org_id: row.org_id, api_key: null, customer_label: row.customer_label, witness_url: row.witness_url, witness_secret: null, consumed: true });
  // Single retrieval: hand the key out once, then forget it.
  let raw: string;
  try {
    raw = await openDeviceKey(c.env, row.api_key_raw);
  } catch {
    return c.json({ error: { code: "not_configured", message: "Device login is not configured yet." } }, 503);
  }
  let witnessSecret: string | null = null;
  if (row.witness_secret_enc) {
    try {
      witnessSecret = await openDeviceKey(c.env, row.witness_secret_enc);
    } catch {
      return c.json({ error: { code: "not_configured", message: "Device login is not configured yet." } }, 503);
    }
  }
  await c.env.DB.prepare("UPDATE device_codes SET api_key_raw = NULL, witness_secret_enc = NULL WHERE code = ?").bind(c.req.param("code")).run();
  return c.json({ status: "authorized", org_id: row.org_id, api_key: raw, url: c.env.APP_ORIGIN, customer_label: row.customer_label, witness_url: row.witness_url, witness_secret: witnessSecret });
});

// Browser page: type the short code from your OWN terminal (RFC 8628).
// The long device secret never appears here or in any URL.
app.get("/device", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw).catch(() => null);
  if (!user) {
    return c.html(
      page(
        "Connect this computer — EPI Cloud",
        `<span class="tag">Device login</span>` +
          `<h1>Authorize this computer</h1>` +
          `<p class="lede">Sign in first, then type the short code shown in <strong>your own</strong> terminal. A link alone authorizes nothing.</p>` +
          `<p><a class="btn btn-pri" href="/auth/github?next=/auth/device">Sign in with GitHub</a></p>` +
          (c.env.GOOGLE_CLIENT_ID
            ? `<p><a class="btn btn-sec" href="/auth/google?next=/auth/device">Sign in with Google</a></p>`
            : ``),
      ),
    );
  }
  const script = [
    `var codeEl=document.getElementById("user-code");`,
    `var orgEl=document.getElementById("org");`,
    `var custEl=document.getElementById("cust");`,
    `var msg=document.getElementById("msg");`,
    `var reqEl=document.getElementById("req");`,
    `function setMsg(t,cls){msg.textContent=t;msg.className=cls||"msg";}`,
    `function loadCustomers(){var oid=orgEl.value;var dl=document.getElementById("cust-list");dl.innerHTML="";if(!oid){return;}fetch("/v1/orgs/"+encodeURIComponent(oid)+"/inboxes",{credentials:"same-origin"}).then(function(r){return r.json().catch(function(){return {};});}).then(function(j){var open=(j.inboxes||[]).filter(function(b){return !b.closed_at;});open.forEach(function(b){var o=document.createElement("option");o.value=b.customer_label;dl.appendChild(o);});var hint=document.getElementById("cust-hint");if(open.length===1&&!custEl.value){custEl.value=open[0].customer_label;}if(hint){hint.textContent=open.length?("Your customers: "+open.map(function(b){return b.customer_label;}).join(", ")+". Type one of them, or a new name."):"Type the name of the company this evidence is for, e.g. Acme Bank.";}}).catch(function(){});}`,
    `fetch("/v1/orgs",{credentials:"same-origin"})`,
    `  .then(function(r){return r.json();})`,
    `  .then(function(j){`,
    `    orgEl.innerHTML="";var orgs=j.orgs||[];`,
    `    orgs.forEach(function(o){var el=document.createElement("option");el.value=o.id;el.textContent=o.name;orgEl.appendChild(el);});`,
    `    document.getElementById("org-row").style.display=orgs.length>1?"":"none";`,
    `    var one=document.getElementById("org-one");if(orgs.length===1){one.textContent=orgs[0].name;one.parentNode.style.display="";}`,
    `    orgEl.onchange=loadCustomers;loadCustomers();`,
    `    if(!orgs.length){setMsg("You don\\u2019t have a workspace yet. Create one on the EPI Cloud front page first, then come back.","warn");document.getElementById("go").disabled=true;}`,
    `  });`,
    `function checkCode(){var code=codeEl.value.replace(/[^A-Za-z0-9]/g,"");if(code.length<8){reqEl.textContent="";return;}`,
    `  fetch("/auth/device/lookup",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({user_code:codeEl.value})})`,
    `    .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})`,
    `    .then(function(x){if(x.ok){var when=x.j.requested_at;try{when=new Date(x.j.requested_at).toLocaleTimeString();}catch(e){}reqEl.textContent="\\u2713 Code found \\u2014 a computer asked at "+when+".";reqEl.className="small";}else{reqEl.textContent=(x.j&&x.j.error&&x.j.error.message)||"That code wasn\\u2019t found.";reqEl.className="small mut";}})`,
    `    .catch(function(){});}`,
    `codeEl.oninput=checkCode;`,
    `document.getElementById("go").onclick=function(){`,
    `  var b=this;var cl=custEl.value.trim().replace(/\\s+/g," ");`,
    `  if(!codeEl.value.trim()){setMsg("Type the code from your terminal first.","err");codeEl.focus();return;}`,
    `  if(!cl){setMsg("Type which customer this computer records for (for example Acme Bank).","err");custEl.focus();return;}`,
    `  b.disabled=true;setMsg("Connecting\\u2026");`,
    `  fetch("/auth/device/authorize",{method:"POST",credentials:"same-origin",`,
    `    headers:{"Content-Type":"application/json"},`,
    `    body:JSON.stringify({user_code:codeEl.value,org_id:orgEl.value,customer_label:cl})})`,
    `    .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})`,
    `    .then(function(x){`,
    `      if(x.ok){setMsg("\\u2713 Done \\u2014 go back to your terminal. This computer now records for "+cl+". Next, run: epi demo","ok");}`,
    `      else{b.disabled=false;setMsg((x.j&&x.j.error&&x.j.error.message)||"That didn\\u2019t work \\u2014 check the code and try again.","err");}`,
    `    })`,
    `    .catch(function(){b.disabled=false;setMsg("Couldn\\u2019t reach EPI Cloud \\u2014 check your connection and try again.","err");});`,
    `};`,
  ].join("\n");
  return c.html(
    page(
      "Connect this computer — EPI Cloud",
      `<span class="tag">Connect a computer</span>` +
        `<h1>Connect this computer</h1>` +
        `<p class="lede">You ran <code>epi cloud login</code> in your terminal. Type the code it shows and the customer this computer records for. Nothing secret to copy — the rest goes to your computer automatically.</p>` +
        `<div class="card">` +
        `<label for="user-code">Code from your terminal</label>` +
        `<input id="user-code" autocomplete="one-time-code" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX">` +
        `<p id="req" class="mut small" role="status"></p>` +
        `<p class="small" style="display:none">Workspace: <strong id="org-one"></strong></p>` +
        `<div id="org-row" style="display:none"><label for="org">Workspace</label><select id="org"></select></div>` +
        `<label for="cust">Customer this computer records for</label>` +
        `<input id="cust" list="cust-list" autocomplete="off" autocapitalize="words" spellcheck="false" placeholder="Acme Bank"><datalist id="cust-list"></datalist>` +
        `<p id="cust-hint" class="small mut"></p>` +
        `<p><button id="go" type="button" class="btn btn-pri">Connect this computer</button></p>` +
        `<p id="msg" class="msg" role="status"></p>` +
        `</div>` +
        `<p class="small mut">Only type a code that <strong>your own</strong> terminal shows. Never a code someone sent you — it would connect their computer to your workspace. You can disconnect any computer later under Computers on the dashboard.</p>` +
        `<p><a href="/">Back to the dashboard</a></p>`,
      { script },
    ),
  );
});

// Confirm a typed code belongs to a pending request (signed in only,
// so strangers cannot probe codes). Reveals only the request time.
// RFC 8628 §5.1: throttle verification attempts (10/min per user AND
// per IP) so a signed-in attacker cannot grind through code space.
async function deviceLookupLimited(db: D1Database, req: Request, userId: string): Promise<Response | null> {
  for (const key of [`devlookup-ip:${clientIp(req)}`, `devlookup-user:${userId}`]) {
    const r = await checkRateLimit(d1CounterStore(db), key, 10, 60);
    if (!r.ok) {
      return Response.json(
        { error: { code: "rate_limited", message: "Too many code checks. Wait a minute and retry." } },
        { status: 429, headers: { "Retry-After": String(r.retryAfterSec) } },
      );
    }
  }
  return null;
}

app.post("/device/lookup", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const throttled = await deviceLookupLimited(c.env.DB, c.req.raw, user.id);
  if (throttled) return throttled;
  const body = z.object({ user_code: z.string().min(4).max(32) }).safeParse(await c.req.json().catch(() => null));
  if (!body.success) return c.json({ error: { code: "bad_request", message: "user_code required." } }, 400);
  const code = normalizeUserCode(body.data.user_code);
  if (!code) return c.json({ error: { code: "not_found", message: "No pending request matches that code." } }, 404);
  await purgeExpiredDevices(c.env.DB);
  const row = await c.env.DB.prepare("SELECT created_at, expires_at, status FROM device_codes WHERE user_code = ?")
    .bind(code)
    .first<{ created_at: string; expires_at: string; status: string }>();
  if (!row || row.status !== "pending" || row.expires_at <= nowIso()) {
    return c.json({ error: { code: "not_found", message: "No pending request matches that code." } }, 404);
  }
  return c.json({ ok: true, requested_at: row.created_at });
});

app.post("/device/authorize", async (c) => {
  const user = await userFromRequest(c.env.DB, c.req.raw);
  if (!user) return c.json({ error: { code: "unauthorized", message: "Sign in first." } }, 401);
  const body = z
    .object({
      user_code: z.string().min(4).max(32).optional(),
      device_code: z.string().min(10).max(256).optional(),
      org_id: z.string().min(1).max(128),
      customer_label: z.string().trim().min(1).max(120).optional(),
    })
    .safeParse(await c.req.json().catch(() => null));
  if (!body.success || (!body.data.user_code && !body.data.device_code)) {
    return c.json({ error: { code: "bad_request", message: "user_code and org_id required." } }, 400);
  }
  await purgeExpiredDevices(c.env.DB);
  // Prefer the typed user code; the legacy device_code path exists only so
  // in-flight logins from the previous release can finish, and is removed
  // once those 10-minute codes expire.
  const byUser = body.data.user_code ? normalizeUserCode(body.data.user_code) : null;
  const dev = byUser
    ? await c.env.DB.prepare("SELECT code, device_name, status, expires_at, replaces_key_hash FROM device_codes WHERE user_code = ?")
      .bind(byUser)
      .first<{ code: string; device_name: string | null; status: string; expires_at: string; replaces_key_hash: string | null }>()
    : await c.env.DB.prepare("SELECT code, device_name, status, expires_at, replaces_key_hash FROM device_codes WHERE code = ?")
      .bind(body.data.device_code!)
      .first<{ code: string; device_name: string | null; status: string; expires_at: string; replaces_key_hash: string | null }>();
  if (!dev) return c.json({ error: { code: "not_found", message: "Unknown or mistyped code. Check and retry." } }, 404);
  if (dev.expires_at <= nowIso()) {
    await c.env.DB.prepare("DELETE FROM device_codes WHERE code = ?").bind(dev.code).run();
    return c.json({ error: { code: "expired", message: "Code expired. Run `epi cloud login` again." } }, 410);
  }
  if (dev.status !== "pending") {
    return c.json({ error: { code: "already_authorized", message: "Already authorized. No new key minted." } }, 409);
  }
  const role = await membershipRole(c.env.DB, body.data.org_id, user.id);
  if (role !== "owner" && role !== "member") {
    return c.json({ error: { code: "forbidden", message: "Only workspace owners and members can connect a computer. Ask an owner to invite you." } }, 403);
  }
  // Customer first: if it fails (plan limit, unknown customer) nothing is
  // minted, so a failed attempt never leaves a dead key in the list.
  // The witness URL + sealed secret are stored with the device row and
  // handed to the CLI on first poll, so the user never copies a secret.
  let customerLabel: string | null = null;
  let witnessUrl: string | null = null;
  let witnessSealed: string | null = null;
  const rawLabel = (body.data.customer_label ?? "").trim();
  if (rawLabel) {
    const ensured = await ensureCustomerInbox(c.env.DB, c.env, body.data.org_id, rawLabel, `user:${user.id}`, {
      allowCreateInbox: role === "owner",
      allowCreateAgent: true,
    });
    if (!ensured.ok) return c.json({ error: { code: ensured.code, message: ensured.message } }, ensured.status as 400);
    customerLabel = ensured.label;
    witnessUrl = ensured.url;
    witnessSealed = await sealDeviceKey(c.env, ensured.secret);
  }
  const key = newApiKey();
  const id = newId("key");
  await c.env.DB.prepare(
    "INSERT INTO api_keys (id, org_id, prefix, key_hash, scopes, label, created_by, created_at, last_used_at, revoked_at, customer_label) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)",
  )
    .bind(id, body.data.org_id, key.prefix, await sha256Hex(key.raw), "push", dev.device_name, user.id, nowIso(), customerLabel)
    .run();
  const sealed = await sealDeviceKey(c.env, key.raw);
  const updated = await c.env.DB.prepare(
    "UPDATE device_codes SET status = 'authorized', org_id = ?, api_key_id = ?, api_key_raw = ?, customer_label = ?, witness_url = ?, witness_secret_enc = ?, authorized_at = ? WHERE code = ? AND status = 'pending'",
  )
    .bind(body.data.org_id, id, sealed, customerLabel, witnessUrl, witnessSealed, nowIso(), dev.code)
    .run();
  if (updated.meta.changes === 0) {
    // Lost a double-click race: retire the key we just made.
    await c.env.DB.prepare("UPDATE api_keys SET revoked_at = ? WHERE id = ?").bind(nowIso(), id).run();
    return c.json({ error: { code: "already_authorized", message: "Already authorized. No new key minted." } }, 409);
  }
  // Re-login on the same computer: its previous key (proved by possession at
  // /device/start) is retired, so the key list doesn't fill with dead rows.
  if (dev.replaces_key_hash) {
    const old = await c.env.DB.prepare("UPDATE api_keys SET revoked_at = ? WHERE key_hash = ? AND org_id = ? AND revoked_at IS NULL AND id != ?")
      .bind(nowIso(), dev.replaces_key_hash, body.data.org_id, id).run();
    if (old.meta.changes) {
      await auditLog(d1AuditDb(c.env.DB), { orgId: body.data.org_id, actor: `user:${user.id}`, action: "api_key.revoke", detail: "replaced by re-login" });
    }
  }
  await auditLog(d1AuditDb(c.env.DB), { orgId: body.data.org_id, actor: `user:${user.id}`, action: "api_key.create", detail: `${id} scopes=push via device` });
  return c.json({ ok: true });
});

void STATE_TTL_MS;
void randomHex;

export default app;
