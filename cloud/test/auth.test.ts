// Login cleanup: GitHub User-Agent, safe linking, device flow, e2e.
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { app } from "../src/index.ts";
import { hmacHex, sha256Hex } from "../src/lib/crypto.ts";
import { findOrLinkUser, GITHUB_USER_AGENT } from "../src/routes/auth.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function openDb(): DatabaseSync {
  const db = new DatabaseSync(":memory:");
  const files = readdirSync(join(root, "migrations")).filter((f) => f.endsWith(".sql")).sort();
  for (const f of files) db.exec(readFileSync(join(root, "migrations", f), "utf8"));
  return db;
}

// Minimal D1 shim over node:sqlite (real schema, incl. 0003 columns).
class SqliteD1 {
  constructor(private db: DatabaseSync) {}
  prepare(sql: string) {
    const q = sql.replace(/\s+/g, " ").trim();
    const db = this.db;
    const bound = (args: unknown[]) => ({
      first: async (): Promise<Record<string, unknown> | null> => {
        try {
          const row = (db.prepare(q).get(...(args as never[])) as Record<string, unknown> | undefined) ?? null;
          return row;
        } catch (err) {
          // D1 returns null on no-row; sqlite get returns undefined (handled).
          // Re-throw real SQL errors so sql.test parity holds.
          throw err;
        }
      },
      all: async (): Promise<{ results: Record<string, unknown>[] }> => {
        const rows = db.prepare(q).all(...(args as never[])) as Record<string, unknown>[];
        return { results: rows };
      },
      run: async (): Promise<{ meta: { changes: number } }> => {
        const r = db.prepare(q).run(...(args as never[])) as unknown as { changes: number | bigint };
        return { meta: { changes: Number(r.changes ?? 0) } };
      },
    });
    return {
      bind: (...a: unknown[]) => bound(a),
      first: () => bound([]).first(),
      all: () => bound([]).all(),
      run: () => bound([]).run(),
    };
  }
}

class FakeR2 {
  store = new Map<string, Uint8Array>();
  async put(key: string, body: unknown) {
    this.store.set(key, new Uint8Array([1]));
    void body;
  }
  async get(key: string) {
    const b = this.store.get(key);
    return b ? { body: b } : null;
  }
  async delete(key: string) {
    this.store.delete(key);
  }
}

function envFor(db: DatabaseSync) {
  return {
    DB: new SqliteD1(db) as unknown as D1Database,
    ROOM: new FakeR2() as unknown as R2Bucket,
    WITNESS: { get: () => ({ fetch: async () => new Response(JSON.stringify({ count: 0 }), { status: 200 }) }) } as unknown as DurableObjectNamespace,
    APP_ORIGIN: "https://cloud.epilabs.org",
    PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
    SESSION_KEY: "test-session-key-0123456789abcdef",
    GITHUB_CLIENT_ID: "test-github-id",
    GITHUB_CLIENT_SECRET: "test-github-secret",
    GOOGLE_CLIENT_ID: "test-google-id",
    GOOGLE_CLIENT_SECRET: "test-google-secret",
    INBOX_SECRET_KEY: "ab".repeat(32),
  };
}

type SeenFetch = { url: string; headers: Record<string, string> };
let seen: SeenFetch[] = [];
let githubProfile: { id: number; login: string; email: string; verified: boolean } = {
  id: 111,
  login: "victim",
  email: "victim@example.com",
  verified: true,
};
const realFetch = globalThis.fetch;

function mockGithub() {
  seen = [];
  globalThis.fetch = (async (url: unknown, init?: RequestInit) => {
    const u = String(url);
    const headers: Record<string, string> = {};
    const h = (init as RequestInit | undefined)?.headers;
    if (h instanceof Headers) h.forEach((v, k) => (headers[k.toLowerCase()] = v));
    else if (h && typeof h === "object") Object.assign(headers, Object.fromEntries(Object.entries(h as Record<string, string>).map(([k, v]) => [k.toLowerCase(), String(v)])));
    seen.push({ url: u, headers });
    if (u === "https://github.com/login/oauth/access_token") {
      return Response.json({ access_token: "tok-test" });
    }
    if (u === "https://api.github.com/user") {
      return Response.json({ id: githubProfile.id, login: githubProfile.login, name: githubProfile.login });
    }
    if (u === "https://api.github.com/user/emails") {
      return Response.json([{ email: githubProfile.email, verified: githubProfile.verified, primary: true }]);
    }
    throw new Error(`unexpected fetch in test: ${u}`);
  }) as typeof fetch;
}

beforeEach(() => {
  mockGithub();
});
afterEach(() => {
  globalThis.fetch = realFetch;
  vi.unstubAllGlobals();
});

describe("github User-Agent", () => {
  it("sends User-Agent: epi-cloud on token exchange and api.github.com", async () => {
    const db = openDb();
    const env = envFor(db);
    githubProfile = { id: 999, login: "ua-test", email: "ua@test.example", verified: true };
    const start = await app.request("/auth/github", {}, env as never);
    const loc = new URL(start.headers.get("Location")!);
    const stateParam = loc.searchParams.get("state")!;
    const oauthState = start.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!;
    const cb = await app.request(`/auth/github/callback?code=c&state=${encodeURIComponent(stateParam)}`, { headers: { Cookie: `epi_oauth_state=${oauthState}` } }, env as never);
    expect(cb.status).toBe(302);
    expect(GITHUB_USER_AGENT).toBe("epi-cloud");
    const urls = seen.map((s) => s.url);
    expect(urls).toContain("https://github.com/login/oauth/access_token");
    expect(urls).toContain("https://api.github.com/user");
    expect(urls).toContain("https://api.github.com/user/emails");
    for (const s of seen) {
      expect(s.headers["user-agent"], `missing UA on ${s.url}`).toBe("epi-cloud");
    }
    db.close();
  });
});

describe("safe account linking", () => {
  it("never links a verified Google login into an unverified GitHub pre-registered account", async () => {
    const db = openDb();
    const d1 = new SqliteD1(db) as unknown as D1Database;
    // Attacker: GitHub account with victim email, never verified.
    const attackerId = await findOrLinkUser(d1, "github", "gh-attacker", "victim@example.com", false, "Attacker");
    const attackerRow = db.prepare("SELECT id, email, email_verified FROM users WHERE id = ?").get(attackerId) as { email_verified: number };
    expect(Number(attackerRow.email_verified)).toBe(0);
    // Victim: Google login, same email, verified.
    const victimId = await findOrLinkUser(d1, "google", "goog-victim", "victim@example.com", true, "Victim");
    expect(victimId).not.toBe(attackerId);
    const victimRow = db.prepare("SELECT id, email_verified FROM users WHERE id = ?").get(victimId) as { email_verified: number };
    expect(Number(victimRow.email_verified)).toBe(1);
    // Identities stay separate.
    const n = db.prepare("SELECT COUNT(*) AS n FROM users WHERE email = ?").get("victim@example.com") as { n: number };
    expect(n.n).toBe(2);
    db.close();
  });

  it("links when BOTH stored and new emails are verified", async () => {
    const db = openDb();
    const d1 = new SqliteD1(db) as unknown as D1Database;
    const first = await findOrLinkUser(d1, "google", "goog-1", "friend@example.com", true, "Friend");
    const second = await findOrLinkUser(d1, "github", "gh-1", "friend@example.com", true, "Friend");
    expect(second).toBe(first);
    db.close();
  });

  it("does not overwrite a verified email with an unverified one on re-login", async () => {
    const db = openDb();
    const d1 = new SqliteD1(db) as unknown as D1Database;
    const id = await findOrLinkUser(d1, "google", "goog-1", "me@example.com", true, "Me");
    // Same provider identity returns with a different unverified email (edge).
    const same = await findOrLinkUser(d1, "google", "goog-1", "other@example.com", false, "Me");
    expect(same).toBe(id);
    const row = db.prepare("SELECT email FROM users WHERE id = ?").get(id) as { email: string };
    expect(row.email).toBe("me@example.com");
    db.close();
  });
});

describe("device flow + dashboard e2e (mocked GitHub)", () => {
  it("github -> org -> key -> device authorize -> push init works", async () => {
    const db = openDb();
    const env = envFor(db);
    githubProfile = { id: 4242, login: "e2e-user", email: "e2e@example.com", verified: true };

    // 1. GitHub sign-in (mocked OAuth).
    const start = await app.request("/auth/github", {}, env as never);
    expect(start.status).toBe(302);
    const stateParam = new URL(start.headers.get("Location")!).searchParams.get("state")!;
    const oauthState = start.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!;
    const cb = await app.request(`/auth/github/callback?code=e2e&state=${encodeURIComponent(stateParam)}`, { headers: { Cookie: `epi_oauth_state=${oauthState}` } }, env as never);
    expect(cb.status).toBe(302);
    const cookie = `epi_session=${cb.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!}`;

    // 2. Create org.
    const orgRes = await app.request("/v1/orgs", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ name: "Acme", slug: "acme" }) }, env as never);
    expect(orgRes.status).toBe(201);
    const org = (await orgRes.json()) as { id: string };

    // 3. Create API key (push).
    const keyRes = await app.request(`/v1/orgs/${org.id}/api-keys`, { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ scopes: ["push"] }) }, env as never);
    expect(keyRes.status).toBe(201);
    const keyBody = (await keyRes.json()) as { key: string; id: string };
    expect(keyBody.key.startsWith("epik_")).toBe(true);

    // 4. Device flow (RFC 8628): start -> type user_code -> authorize -> poll once.
    const devStart = await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" } }, env as never);
    expect(devStart.status).toBe(201);
    const dev = (await devStart.json()) as { device_code: string; user_code: string; verification_url: string; interval: number };
    expect(dev.user_code).toMatch(/^[A-Z2-9]{4}-[A-Z2-9]{4}$/);
    expect(dev.verification_url).toBe("https://cloud.epilabs.org/auth/device");
    expect(dev.verification_url).not.toContain(dev.device_code);
    const pending = (await (await app.request(`/auth/device/${dev.device_code}/status`, {}, env as never)).json()) as { status: string };
    expect(pending.status).toBe("pending");
    const lookup = await app.request("/auth/device/lookup", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: dev.user_code.toLowerCase().replace("-", " ") }) }, env as never);
    expect(lookup.status).toBe(200);
    const authz = await app.request("/auth/device/authorize", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: dev.user_code, org_id: org.id }) }, env as never);
    expect(authz.status).toBe(200);
    // Second click mints nothing.
    const again = await app.request("/auth/device/authorize", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: dev.user_code, org_id: org.id }) }, env as never);
    expect(again.status).toBe(409);
    const done = (await (await app.request(`/auth/device/${dev.device_code}/status`, {}, env as never)).json()) as { status: string; api_key: string; org_id: string };
    expect(done.status).toBe("authorized");
    expect(done.api_key.startsWith("epik_")).toBe(true);
    expect(done.org_id).toBe(org.id);
    // Key is single-retrieval: a second poll gets no key.
    const consumed = (await (await app.request(`/auth/device/${dev.device_code}/status`, {}, env as never)).json()) as { status: string; api_key: string | null };
    expect(consumed.status).toBe("authorized");
    expect(consumed.api_key).toBeNull();

    // 5. `epi cloud login`-equivalent check + push init with the minted key.
    // Push-only device keys can init (writer) but cannot list (reader needs `read`).
    const list = await app.request(`/v1/orgs/${org.id}/artifacts`, { headers: { Cookie: cookie } }, env as never);
    expect(list.status).toBe(200);
    const manifest = JSON.stringify({ spec_version: "2", workflow_id: "w1", goal: "g", total_steps: 1, created_at: new Date().toISOString() });
    const init = await app.request(`/v1/orgs/${org.id}/artifacts/init`, {
      method: "POST",
      headers: { Authorization: `Bearer ${done.api_key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ manifest_json: manifest, claimed_sha256: "a".repeat(64), claimed_crc32: 1, size_bytes: 10, reason: "sample" }),
    }, env as never);
    expect([201, 200]).toContain(init.status);

    // 6. Dashboard (front door): guided start, then dashboard tabs.
    // Trust links are built at runtime, scoped per customer by default.
    const home = await app.request("/", { headers: { Cookie: cookie } }, env as never);
    expect(home.status).toBe(200);
    const html = await home.text();
    for (const copy of ["Name your company", "Connect your computer", "Record your first run", "Add a customer", "Computers &amp; keys", "Advanced"]) {
      expect(html).toContain(copy);
    }
    expect(html).toContain('TRUST_ORIGIN="https://epilabs.org"');
    expect(html).toContain("{agents:[agent.id],inboxes:[inboxId]}");
    expect(html).not.toContain("Create API key");
    db.close();
  });

  it("OAuth carries a safe relative next through to the redirect", async () => {
    const db = openDb();
    const env = envFor(db);
    githubProfile = { id: 777, login: "next-user", email: "next@example.com", verified: true };
    const start = await app.request("/auth/github?next=/auth/device", {}, env as never);
    expect(start.status).toBe(302);
    const loc = new URL(start.headers.get("Location")!);
    const stateParam = loc.searchParams.get("state")!;
    const cookies = start.headers.getSetCookie().join("; ");
    const oauthState = /epi_oauth_state=([^;]+)/.exec(cookies)![1]!;
    const oauthNext = /epi_oauth_next=([^;]+)/.exec(cookies)![1]!;
    const cb = await app.request(`/auth/github/callback?code=n&state=${encodeURIComponent(stateParam)}`, { headers: { Cookie: `epi_oauth_state=${oauthState}; epi_oauth_next=${oauthNext}` } }, env as never);
    expect(cb.status).toBe(302);
    expect(cb.headers.get("Location")).toBe("https://cloud.epilabs.org/auth/device");
    // Open redirects are refused: absolute URLs never become the target.
    const evil = await app.request("/auth/github?next=https://evil.test/phish", {}, env as never);
    expect(evil.headers.getSetCookie().join("; ")).not.toContain("epi_oauth_next");
    db.close();
  });

  it("device name flows start -> authorize -> key label", async () => {
    const db = openDb();
    const env = envFor(db);
    githubProfile = { id: 4243, login: "name-user", email: "name@example.com", verified: true };
    const start = await app.request("/auth/github", {}, env as never);
    const stateParam = new URL(start.headers.get("Location")!).searchParams.get("state")!;
    const oauthState = start.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!;
    const cb = await app.request(`/auth/github/callback?code=n&state=${encodeURIComponent(stateParam)}`, { headers: { Cookie: `epi_oauth_state=${oauthState}` } }, env as never);
    const cookie = `epi_session=${cb.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!}`;
    const org = (await (
      await app.request("/v1/orgs", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ name: "Acme", slug: "acme" }) }, env as never)
    ).json()) as { id: string };
    const dev = (await (
      await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ device_name: "field-laptop" }) }, env as never)
    ).json()) as { device_code: string; user_code: string };
    const authz = await app.request("/auth/device/authorize", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: dev.user_code, org_id: org.id }) }, env as never);
    expect(authz.status).toBe(200);
    const row = db.prepare("SELECT label, scopes FROM api_keys WHERE org_id = ?").get(org.id) as { label: string | null; scopes: string };
    expect(row.label).toBe("field-laptop");
    expect(row.scopes).toBe("push");
    db.close();
  });

  it("device authorize with a customer hands the witness secret to the CLI once", async () => {
    const db = openDb();
    const env = envFor(db);
    githubProfile = { id: 4244, login: "cust-user", email: "cust@example.com", verified: true };
    const start = await app.request("/auth/github", {}, env as never);
    const stateParam = new URL(start.headers.get("Location")!).searchParams.get("state")!;
    const oauthState = start.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!;
    const cb = await app.request(`/auth/github/callback?code=n&state=${encodeURIComponent(stateParam)}`, { headers: { Cookie: `epi_oauth_state=${oauthState}` } }, env as never);
    const cookie = `epi_session=${cb.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!}`;
    const org = (await (
      await app.request("/v1/orgs", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ name: "Acme", slug: "acme" }) }, env as never)
    ).json()) as { id: string };
    const dev = (await (
      await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }, env as never)
    ).json()) as { device_code: string; user_code: string };
    // New customer typed at authorize time: owner mints agent + inbox.
    const authz = await app.request("/auth/device/authorize", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: dev.user_code, org_id: org.id, customer_label: "Acme Bank" }) }, env as never);
    expect(authz.status).toBe(200);
    const done = (await (await app.request(`/auth/device/${dev.device_code}/status`, {}, env as never)).json()) as { status: string; witness_url: string | null; witness_secret: string | null; customer_label: string | null; api_key: string };
    expect(done.status).toBe("authorized");
    expect(done.customer_label).toBe("Acme Bank");
    expect(done.witness_url).toMatch(/^https:\/\/cloud\.epilabs\.org\/w\/inb_/);
    expect(done.witness_secret).toMatch(/^[0-9a-f]{64}$/);
    expect(done.api_key.startsWith("epik_")).toBe(true);
    // Single retrieval: the secret is nulled after the first poll.
    const again = (await (await app.request(`/auth/device/${dev.device_code}/status`, {}, env as never)).json()) as { witness_secret: string | null };
    expect(again.witness_secret).toBeNull();
    // Without a customer the CLI gets a key but no witness material.
    const dev2 = (await (
      await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }, env as never)
    ).json()) as { device_code: string; user_code: string };
    await app.request("/auth/device/authorize", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: dev2.user_code, org_id: org.id }) }, env as never);
    const bare = (await (await app.request(`/auth/device/${dev2.device_code}/status`, {}, env as never)).json()) as { witness_url: string | null; witness_secret: string | null; customer_label: string | null };
    expect(bare.customer_label).toBeNull();
    expect(bare.witness_url).toBeNull();
    expect(bare.witness_secret).toBeNull();
    db.close();
  });

  it("members cannot mint new customer inboxes via device flow, but can select", async () => {
    const db = openDb();
    const env = envFor(db);
    githubProfile = { id: 4245, login: "owner2", email: "owner2@example.com", verified: true };
    const start = await app.request("/auth/github", {}, env as never);
    const stateParam = new URL(start.headers.get("Location")!).searchParams.get("state")!;
    const oauthState = start.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!;
    const cb = await app.request(`/auth/github/callback?code=n&state=${encodeURIComponent(stateParam)}`, { headers: { Cookie: `epi_oauth_state=${oauthState}` } }, env as never);
    const ownerCookie = `epi_session=${cb.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!}`;
    const org = (await (
      await app.request("/v1/orgs", { method: "POST", headers: { Cookie: ownerCookie, "Content-Type": "application/json" }, body: JSON.stringify({ name: "Acme", slug: "acme" }) }, env as never)
    ).json()) as { id: string };
    // Owner creates the customer inbox first (dashboard or device flow).
    const first = (await (
      await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }, env as never)
    ).json()) as { device_code: string; user_code: string };
    expect((await app.request("/auth/device/authorize", { method: "POST", headers: { Cookie: ownerCookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: first.user_code, org_id: org.id, customer_label: "Acme Bank" }) }, env as never)).status).toBe(200);
    // Lift to growth so plan caps don't mask the permission check below.
    db.prepare("UPDATE orgs SET plan = 'growth'").run();
    // Promote a second user to member (owner-only creation stays closed to them).
    db.prepare("INSERT INTO users (id, email, display_name, email_verified, created_at) VALUES ('u_member','m@x.test','M',1,'t')").run();
    db.prepare("INSERT INTO memberships (org_id, user_id, role) VALUES (?,'u_member','member')").run(org.id);
    const memberHash = await sha256Hex("sess-member");
    db.prepare("INSERT INTO sessions (id_hash, user_id, expires_at) VALUES (?, 'u_member', '2999-01-01T00:00:00.000Z')").run(memberHash);
    const memberCookie = "epi_session=sess-member";
    const second = (await (
      await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }, env as never)
    ).json()) as { device_code: string; user_code: string };
    // New customer as member: 403, nothing minted.
    const denied = await app.request("/auth/device/authorize", { method: "POST", headers: { Cookie: memberCookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: second.user_code, org_id: org.id, customer_label: "Other Bank" }) }, env as never);
    expect(denied.status).toBe(403);
    // Existing customer as member: fine, witness secret included.
    const third = (await (
      await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) }, env as never)
    ).json()) as { device_code: string; user_code: string };
    const okRes = await app.request("/auth/device/authorize", { method: "POST", headers: { Cookie: memberCookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: third.user_code, org_id: org.id, customer_label: "Acme Bank" }) }, env as never);
    expect(okRes.status).toBe(200);
    const done = (await (await app.request(`/auth/device/${third.device_code}/status`, {}, env as never)).json()) as { witness_secret: string | null; customer_label: string | null };
    expect(done.customer_label).toBe("Acme Bank");
    expect(done.witness_secret).toMatch(/^[0-9a-f]{64}$/);
    db.close();
  });

  it("GET /v1/version advertises the minimum CLI", async () => {
    const db = openDb();
    const env = envFor(db);
    const res = (await (await app.request("/v1/version", {}, env as never)).json()) as { service: string; min_cli_version: string };
    expect(res.service).toBe("epi-cloud");
    expect(res.min_cli_version).toMatch(/^\d+\.\d+\.\d+$/);
    db.close();
  });

  it("GET /auth/session answers signed-in state with site-only CORS", async () => {
    const db = openDb();
    const env = envFor(db);
    db.prepare("INSERT INTO users (id, email, display_name, email_verified, created_at) VALUES ('u1','u@x.test','U',1,'t')").run();
    const raw = "sessraw-0123456789abcdef0123456789abcdef01234567";
    db.prepare("INSERT INTO sessions (id_hash, user_id, expires_at) VALUES (?, 'u1', '2999-01-01T00:00:00.000Z')").run(await sha256Hex(raw));
    const cookie = `epi_session=${raw}`;

    // Signed in, allowed site origin: true plus an exact-origin CORS grant.
    const ok = await app.request("/auth/session", { headers: { Cookie: cookie, Origin: "https://epilabs.org" } }, env as never);
    expect(ok.status).toBe(200);
    expect(await ok.json()).toEqual({ signed_in: true });
    expect(ok.headers.get("Access-Control-Allow-Origin")).toBe("https://epilabs.org");
    expect(ok.headers.get("Access-Control-Allow-Credentials")).toBe("true");
    expect(ok.headers.get("Vary")).toBe("Origin");
    expect(ok.headers.get("Cache-Control")).toBe("no-store");

    // Signed in, foreign origin: same JSON but no CORS grant, so a foreign
    // page cannot read it (and learns nothing beyond the status shape).
    const evil = await app.request("/auth/session", { headers: { Cookie: cookie, Origin: "https://evil.example" } }, env as never);
    expect(evil.status).toBe(200);
    expect(await evil.json()).toEqual({ signed_in: true });
    expect(evil.headers.get("Access-Control-Allow-Origin")).toBeNull();

    // Signed out: false with no identity in the body, grant intact.
    const out = await app.request("/auth/session", { headers: { Origin: "https://www.epilabs.org" } }, env as never);
    expect(out.status).toBe(200);
    expect(await out.json()).toEqual({ signed_in: false });
    expect(out.headers.get("Access-Control-Allow-Origin")).toBe("https://www.epilabs.org");
    db.close();
  });
});
