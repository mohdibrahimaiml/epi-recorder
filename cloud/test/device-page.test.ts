// #125 follow-up: real-page regression tests for the device flow.
// The "Authorize this computer does nothing" bug was an extra `}` inside
// the /auth/device inline script. Unit tests that only POST to the JSON
// endpoints can never catch it, so this file loads the REAL pages served
// by the app and (a) compiles every inline script with node:vm (syntax),
// (b) asserts the Authorize button is wired to the user_code endpoints,
// (c) asserts the secret device_code never appears in page HTML or URLs,
// (d) asserts polling and sign-in use separate rate-limit buckets,
// (e) asserts trust links point at epilabs.org and wrap on mobile.
import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { Script } from "node:vm";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { app } from "../src/index.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function openDb(): DatabaseSync {
  const db = new DatabaseSync(":memory:");
  const files = readdirSync(join(root, "migrations")).filter((f) => f.endsWith(".sql")).sort();
  for (const f of files) db.exec(readFileSync(join(root, "migrations", f), "utf8"));
  return db;
}

class SqliteD1 {
  constructor(private db: DatabaseSync) {}
  prepare(sql: string) {
    const q = sql.replace(/\s+/g, " ").trim();
    const db = this.db;
    const bound = (args: unknown[]) => ({
      first: async (): Promise<Record<string, unknown> | null> =>
        ((db.prepare(q).get(...(args as never[])) as Record<string, unknown> | undefined) ?? null),
      all: async (): Promise<{ results: Record<string, unknown>[] }> => ({
        results: db.prepare(q).all(...(args as never[])) as Record<string, unknown>[],
      }),
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

function envFor(db: DatabaseSync) {
  return {
    DB: new SqliteD1(db) as unknown as D1Database,
    ROOM: {} as R2Bucket,
    WITNESS: { get: () => ({ fetch: async () => new Response("{}", { status: 200 }) }) } as unknown as DurableObjectNamespace,
    APP_ORIGIN: "https://cloud.epilabs.org",
    PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
    SESSION_KEY: "test-session-key-device-page",
    GITHUB_CLIENT_ID: "test-github-id",
    GITHUB_CLIENT_SECRET: "test-github-secret",
    INBOX_SECRET_KEY: "ab".repeat(32),
  };
}

const realFetch = globalThis.fetch;

function mockGithub(profile = { id: 5150, login: "page-user", email: "page@example.com", verified: true }) {
  globalThis.fetch = (async (url: unknown) => {
    const u = String(url);
    if (u === "https://github.com/login/oauth/access_token") return Response.json({ access_token: "tok" });
    if (u === "https://api.github.com/user") return Response.json({ id: profile.id, login: profile.login, name: profile.login });
    if (u === "https://api.github.com/user/emails") {
      return Response.json([{ email: profile.email, verified: profile.verified, primary: true }]);
    }
    throw new Error(`unexpected fetch: ${u}`);
  }) as typeof fetch;
}

beforeEach(() => mockGithub());
afterEach(() => {
  globalThis.fetch = realFetch;
});

function inlineScripts(html: string): string[] {
  const out: string[] = [];
  for (const m of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>(.*?)<\/script>/gis)) out.push(m[1]!);
  return out;
}

async function signedInCookie(env: ReturnType<typeof envFor>): Promise<string> {
  const start = await app.request("/auth/github", {}, env as never);
  const stateParam = new URL(start.headers.get("Location")!).searchParams.get("state")!;
  const oauthState = start.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!;
  const cb = await app.request(`/auth/github/callback?code=p&state=${encodeURIComponent(stateParam)}`, { headers: { Cookie: `epi_oauth_state=${oauthState}` } }, env as never);
  expect(cb.status).toBe(302);
  return `epi_session=${cb.headers.get("Set-Cookie")!.split("=")[1]!.split(";")[0]!}`;
}

describe("device + dashboard pages (served HTML)", () => {
  it("every inline script on / and /auth/device parses (no stray brace)", async () => {
    const db = openDb();
    const env = envFor(db);
    const cookie = await signedInCookie(env);
    // Anonymous pages are static by design: no scripts at all (no signal
    // for scanners). Signed-in pages carry small fetch scripts.
    for (const res of [await app.request("/", {}, env as never), await app.request("/auth/device", {}, env as never)]) {
      expect(res.status).toBe(200);
      expect(inlineScripts(await res.text())).toHaveLength(0);
    }
    const dashHtml = await (await app.request("/", { headers: { Cookie: cookie } }, env as never)).text();
    const deviceHtml = await (await app.request("/auth/device", { headers: { Cookie: cookie } }, env as never)).text();
    for (const html of [dashHtml, deviceHtml]) {
      const scripts = inlineScripts(html);
      expect(scripts.length).toBeGreaterThan(0);
      for (const body of scripts) {
        expect(() => new Script(body), `inline script must parse:\n${body.slice(0, 200)}`).not.toThrow();
      }
      // The #125 bug was a doubled close (`...})}};`) that killed the
      // Authorize button. Plain `}};` is valid JS, so match the exact shape.
      expect(html).not.toContain("})}};");
    }
    // Every dashboard function the wiring references must be defined —
    // a dropped definition is a dead button with no console error.
    for (const fn of ["createOrg", "createCustomer", "ensureAgent", "createLink", "renderRuns", "renderCustomers", "renderLinks", "renderKeys", "runTitle", "runSub", "witHint", "witSub", "loadAll", "boot"]) {
      expect(dashHtml, `missing function ${fn}`).toContain(`function ${fn}(`);
    }
    db.close();
  });

  it("Authorize is wired to user_code lookup + authorize (never device_code)", async () => {
    const db = openDb();
    const env = envFor(db);
    const cookie = await signedInCookie(env);
    const html = await (await app.request("/auth/device", { headers: { Cookie: cookie } }, env as never)).text();
    expect(html).toContain('id="go"');
    expect(html).toContain('id="lookup"');
    expect(html).toContain('id="user-code"');
    expect(html).toContain("/auth/device/lookup");
    expect(html).toContain("/auth/device/authorize");
    expect(html).toContain("user_code");
    expect(html).not.toContain("device_code");
    db.close();
  });

  it("verification URL and pages never contain the device secret", async () => {
    const db = openDb();
    const env = envFor(db);
    const started = (await (
      await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" } }, env as never)
    ).json()) as { device_code: string; verification_url: string };
    expect(started.verification_url).not.toContain(started.device_code);
    const pageHtml = await (await app.request("/auth/device", {}, env as never)).text();
    expect(pageHtml).not.toContain(started.device_code);
    db.close();
  });

  it("a bare link authorizes nothing (phishing-resistant)", async () => {
    const db = openDb();
    const env = envFor(db);
    const cookie = await signedInCookie(env);
    const started = (await (
      await app.request("/auth/device/start", { method: "POST", headers: { "Content-Type": "application/json" } }, env as never)
    ).json()) as { device_code: string; user_code: string };
    // Attacker knows the page URL but not the typed code: lookup + authorize fail.
    expect(
      (await app.request("/auth/device/lookup", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body: JSON.stringify({ user_code: "AAAA-AAAA" }) }, env as never)).status,
    ).toBe(404);
    // Unauthenticated authorize fails even with a valid code shape.
    expect(
      (await app.request("/auth/device/authorize", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_code: started.user_code, org_id: "org_x" }) }, env as never)).status,
    ).toBe(401);
    db.close();
  });

  it("polling has its own rate-limit bucket (sign-in stays usable)", async () => {
    const db = openDb();
    const env = envFor(db);
    // Exhaust the interactive login bucket: 10 allowed, 11th blocked.
    for (let i = 0; i < 10; i++) {
      expect((await app.request("/auth/github", {}, env as never)).status).toBe(302);
    }
    expect((await app.request("/auth/github", {}, env as never)).status).toBe(429);
    // Device polling on the same IP still answers (separate 60/min bucket).
    const poll = await app.request("/auth/device/deadbeef/status", {}, env as never);
    expect([404, 200]).toContain(poll.status);
    expect(poll.status).not.toBe(429);
    db.close();
  });

  it("code guessing is throttled (RFC 8628 5.1): guess 11 gets 429", async () => {
    const db = openDb();
    const env = envFor(db);
    const cookie = await signedInCookie(env);
    const guess = (body: string) =>
      app.request("/auth/device/lookup", { method: "POST", headers: { Cookie: cookie, "Content-Type": "application/json" }, body }, env as never);
    for (let i = 0; i < 10; i++) {
      expect((await guess(JSON.stringify({ user_code: "AAAA-AAAA" }))).status).toBe(404);
    }
    const blocked = await guess(JSON.stringify({ user_code: "BBBB-BBBB" }));
    expect(blocked.status).toBe(429);
    expect(blocked.headers.get("Retry-After")).toBeTruthy();
    expect(((await blocked.json()) as { error: { code: string } }).error.code).toBe("rate_limited");
    db.close();
  });

  it("request time renders in local time, not raw UTC", async () => {
    const db = openDb();
    const env = envFor(db);
    const cookie = await signedInCookie(env);
    const html = await (await app.request("/auth/device", { headers: { Cookie: cookie } }, env as never)).text();
    expect(html).toContain("toLocaleString");
    db.close();
  });

  it("trust links point at epilabs.org and long values wrap (390px-safe)", async () => {
    const db = openDb();
    const env = envFor(db);
    const cookie = await signedInCookie(env);
    const html = await (await app.request("/", { headers: { Cookie: cookie } }, env as never)).text();
    // The absolute trust URL is built at runtime from TRUST_ORIGIN, so assert
    // the origin constant plus the per-customer scope shape — and that the
    // old unscoped construction is gone.
    expect(html).toContain('TRUST_ORIGIN="https://epilabs.org"');
    expect(html).toContain("{agents:[agent.id],inboxes:[inboxId]}");
    expect(html).not.toContain('location.origin+"/t/"');
    expect(html).toContain("overflow-wrap:anywhere");
    expect(html).toContain("word-break:break-all");
    expect(html).toContain("width=device-width");
    // Guided flow copy + raw keys out of the main flow.
    for (const copy of ["Name your company", "Connect your computer", "Record your first run", "Add a customer", "Share with", "Advanced", "4.6.1"]) {
      expect(html).toContain(copy);
    }
    expect(html).not.toContain("Create API key");
    db.close();
  });
});
