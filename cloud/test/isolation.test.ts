// Tenant-isolation suite (M0 acceptance): org A can never read or mutate
// org B, on every M0 org route. Drives the real Hono app with an
// in-memory D1 stand-in implementing exactly the statements the routes use.

import { describe, expect, it } from "vitest";
import { app } from "../src/index.ts";
import { sha256Hex } from "../src/lib/crypto.ts";
import { keyFromRequest } from "../src/lib/auth.ts";

type Row = Record<string, unknown>;

// Minimal D1 stand-in: matches the prepared statements our routes emit.
class FakeD1 {
  orgs = new Map<string, Row>();
  users = new Map<string, Row>();
  sessions = new Map<string, Row>(); // by id_hash
  memberships = new Map<string, Row>(); // org|user -> {role}
  invites = new Map<string, Row>(); // by token_hash
  apiKeys = new Map<string, Row>(); // by id
  agents = new Map<string, Row>(); // by id
  audit: Row[] = [];
  counters = new Map<string, Row>();

  prepare(sql: string) {
    const q = sql.replace(/\s+/g, " ").trim();
    const self = this;
    const bound = (args: unknown[]) => {
      const first = async (): Promise<Row | null> => self.selectOne(q, args);
      const all = async (): Promise<{ results: Row[] }> => ({ results: self.selectMany(q, args) });
      const run = async (): Promise<{ meta: { changes: number } }> => ({ meta: { changes: self.exec(q, args) } });
      return { first, all, run };
    };
    return {
      bind: (...args: unknown[]) => bound(args),
      first: () => bound([]).first(),
      all: () => bound([]).all(),
      run: () => bound([]).run(),
    };
  }

  private mem(orgId: unknown, userId: unknown): Row | undefined {
    return this.memberships.get(`${orgId}|${userId}`);
  }

  private selectOne(q: string, a: unknown[]): Row | null {
    if (q.startsWith("SELECT s.user_id")) {
      const s = this.sessions.get(a[0] as string);
      if (!s) return null;
      const u = this.users.get(s.user_id as string);
      return { user_id: s.user_id, expires_at: s.expires_at, email: u?.email ?? null };
    }
    if (q.startsWith("SELECT role FROM memberships")) {
      const m = this.mem(a[0], a[1]);
      return m ? { role: m.role } : null;
    }
    if (q === "SELECT id FROM orgs WHERE id = ?") return this.orgs.has(a[0] as string) ? { id: a[0] } : null;
    if (q.startsWith("SELECT plan FROM orgs")) {
      const o = this.orgs.get(a[0] as string);
      return o ? { plan: o.plan } : null;
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM agents")) {
      let n = 0;
      for (const g of this.agents.values()) if (g.org_id === a[0] && g.status === "active") n++;
      return { n };
    }
    if (q.startsWith("SELECT id, org_id, role, expires_at, accepted_at FROM invites")) {
      for (const v of this.invites.values()) if (v.token_hash === a[0]) return { ...v };
      return null;
    }
    if (q.startsWith("SELECT id, org_id, scopes FROM api_keys")) {
      for (const k of this.apiKeys.values()) if (k.key_hash === a[0] && k.revoked_at == null) return { id: k.id, org_id: k.org_id, scopes: k.scopes };
      return null;
    }
    if (q.startsWith("SELECT entry_hash FROM audit_log")) {
      const rows = this.audit.filter((r) => (r.org_id ?? null) === (a[0] ?? null));
      return rows.length ? { entry_hash: rows[rows.length - 1]!.entry_hash } : null;
    }
    if (q.startsWith("SELECT count, window_expires_at FROM rate_counters")) {
      return this.counters.get(a[0] as string) ?? null;
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM")) {
      const table = q.split("FROM ")[1]!.split(" ")[0]!;
      const col = { orgs: this.orgs, users: this.users, agents: this.agents } as Record<string, Map<string, Row>>;
      if (table === "api_keys") {
        let n = 0;
        for (const k of this.apiKeys.values()) if (k.revoked_at == null) n++;
        return { n };
      }
      if (table === "inboxes" || table === "artifacts") return { n: 0 };
      return { n: col[table]?.size ?? 0 };
    }
    if (q.startsWith("SELECT id FROM users WHERE email")) {
      for (const u of this.users.values()) if (u.email === a[0]) return { id: u.id };
      return null;
    }
    if (q.startsWith("SELECT user_id FROM identities")) return null;
    throw new Error(`FakeD1 unhandled select: ${q}`);
  }

  private selectMany(q: string, a: unknown[]): Row[] {
    if (q.startsWith("SELECT o.id, o.slug")) {
      const out: Row[] = [];
      for (const m of this.memberships.values()) {
        if (m.user_id !== a[0]) continue;
        const o = this.orgs.get(m.org_id as string)!;
        out.push({ id: o.id, slug: o.slug, name: o.name, plan: o.plan, role: m.role });
      }
      return out;
    }
    if (q.startsWith("SELECT id, name, status, created_at FROM agents")) {
      return [...this.agents.values()].filter((g) => g.org_id === a[0]).map((g) => ({ id: g.id, name: g.name, status: g.status, created_at: g.created_at }));
    }
    if (q.startsWith("SELECT id, prefix, scopes")) {
      return [...this.apiKeys.values()].filter((k) => k.org_id === a[0]).map((k) => ({ id: k.id, prefix: k.prefix, scopes: k.scopes, created_by: k.created_by, created_at: k.created_at, last_used_at: k.last_used_at, revoked_at: k.revoked_at }));
    }
    throw new Error(`FakeD1 unhandled selectMany: ${q}`);
  }

  private exec(q: string, a: unknown[]): number {
    if (q.startsWith("INSERT INTO orgs")) {
      if ([...this.orgs.values()].some((o) => o.slug === a[1])) throw new Error("UNIQUE slug");
      this.orgs.set(a[0] as string, { id: a[0], slug: a[1], name: a[2], plan: a[3], created_at: a[4] });
      return 1;
    }
    if (q.startsWith("INSERT INTO memberships")) {
      this.memberships.set(`${a[0]}|${a[1]}`, { org_id: a[0], user_id: a[1], role: a[2] });
      return 1;
    }
    if (q.startsWith("INSERT INTO users")) {
      this.users.set(a[0] as string, { id: a[0], email: a[1], display_name: a[2], created_at: a[3] });
      return 1;
    }
    if (q.startsWith("UPDATE users SET email")) {
      const u = this.users.get(a[1] as string);
      if (u) u.email = a[0];
      return 1;
    }
    if (q.startsWith("INSERT INTO sessions")) {
      this.sessions.set(a[0] as string, { id_hash: a[0], user_id: a[1], expires_at: a[2] });
      return 1;
    }
    if (q.startsWith("DELETE FROM sessions")) {
      return this.sessions.delete(a[0] as string) ? 1 : 0;
    }
    if (q.startsWith("INSERT INTO agents")) {
      for (const g of this.agents.values()) if (g.org_id === a[1] && g.name === a[2]) throw new Error("UNIQUE agent");
      this.agents.set(a[0] as string, { id: a[0], org_id: a[1], name: a[2], status: a[3], created_at: a[4] });
      return 1;
    }
    if (q.startsWith("UPDATE agents SET status")) {
      const g = this.agents.get(a[1] as string);
      if (!g || g.org_id !== a[2]) return 0;
      g.status = a[0];
      return 1;
    }
    if (q.startsWith("INSERT INTO invites")) {
      this.invites.set(a[4] as string, { id: a[0], org_id: a[1], email: a[2], role: a[3], token_hash: a[4], expires_at: a[5], accepted_at: null });
      return 1;
    }
    if (q.startsWith("UPDATE invites SET accepted_at")) {
      for (const v of this.invites.values()) if (v.id === a[1]) v.accepted_at = a[0];
      return 1;
    }
    if (q.startsWith("INSERT INTO api_keys")) {
      this.apiKeys.set(a[0] as string, { id: a[0], org_id: a[1], prefix: a[2], key_hash: a[3], scopes: a[4], created_by: a[5], created_at: a[6], last_used_at: null, revoked_at: null });
      return 1;
    }
    if (q.startsWith("UPDATE api_keys SET last_used_at")) {
      for (const k of this.apiKeys.values()) if (k.id === a[1]) k.last_used_at = a[0];
      return 1;
    }
    if (q.startsWith("UPDATE api_keys SET revoked_at")) {
      for (const k of this.apiKeys.values()) {
        if (k.id === a[1] && k.org_id === a[2] && k.revoked_at == null) {
          k.revoked_at = a[0];
          return 1;
        }
      }
      return 0;
    }
    if (q.startsWith("INSERT INTO audit_log")) {
      this.audit.push({ org_id: a[0], actor: a[1], action: a[2], detail: a[3], at: a[4], prev_hash: a[5], entry_hash: a[6] });
      return 1;
    }
    if (q.startsWith("INSERT INTO rate_counters")) {
      this.counters.set(a[0] as string, { count: a[1], window_expires_at: a[2] });
      return 1;
    }
    throw new Error(`FakeD1 unhandled exec: ${q}`);
  }
}

const ENV = (db: FakeD1) => ({
  DB: db as unknown as D1Database,
  ROOM: {} as R2Bucket,
  WITNESS: {} as DurableObjectNamespace,
  APP_ORIGIN: "https://cloud.epilabs.org",
  PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
  FOUNDER_USER_IDS: "usr_founder",
});

const cookie = (raw: string) => ({ Cookie: `epi_session=${raw}` });

async function seedSession(db: FakeD1, userId: string, email: string): Promise<string> {
  db.users.set(userId, { id: userId, email, display_name: "T", created_at: "t" });
  // Seed via the same shape createSession writes (tests hash the raw id).
  const raw = `sessraw-${userId}-0123456789abcdef0123456789abcdef`;
  db.sessions.set(await sha256Hex(raw), { id_hash: await sha256Hex(raw), user_id: userId, expires_at: "2999-01-01T00:00:00.000Z" });
  return raw;
}

describe("tenant isolation (org A can never touch org B)", () => {
  it("blocks every org route cross-tenant with 403, allows own org", async () => {
    const db = new FakeD1();
    const env = ENV(db);
    const a = await seedSession(db, "usr_a", "a@x.test");
    const b = await seedSession(db, "usr_b", "b@x.test");
    db.orgs.set("org_A", { id: "org_A", slug: "a", name: "A", plan: "free", created_at: "t" });
    db.orgs.set("org_B", { id: "org_B", slug: "b", name: "B", plan: "free", created_at: "t" });
    db.memberships.set("org_A|usr_a", { org_id: "org_A", user_id: "usr_a", role: "owner" });
    db.memberships.set("org_B|usr_b", { org_id: "org_B", user_id: "usr_b", role: "owner" });

    const req = (org: string, raw: string, path: string, init?: RequestInit) =>
      app.request(path.replace(":org", org), { headers: { ...cookie(raw), "Content-Type": "application/json" }, ...init }, env as never);

    // Agents: list / create / patch.
    expect((await req("org_B", a, "/v1/orgs/:org/agents")).status).toBe(403);
    expect((await req("org_A", a, "/v1/orgs/:org/agents")).status).toBe(200);
    expect((await req("org_B", a, "/v1/orgs/:org/agents", { method: "POST", body: JSON.stringify({ name: "x" }) })).status).toBe(403);
    expect((await req("org_B", a, "/v1/orgs/:org/agents", { method: "PATCH", body: JSON.stringify({ id: "g", status: "archived" }) })).status).toBe(403);

    // API keys: mint / list / revoke.
    expect((await req("org_B", a, "/v1/orgs/:org/api-keys", { method: "POST", body: JSON.stringify({ scopes: ["push"] }) })).status).toBe(403);
    const mint = await req("org_A", a, "/v1/orgs/:org/api-keys", { method: "POST", body: JSON.stringify({ scopes: ["push"] }) });
    expect(mint.status).toBe(201);
    const keyId = ((await mint.json()) as { id: string }).id;
    expect((await req("org_B", a, "/v1/orgs/:org/api-keys")).status).toBe(403);
    expect((await req("org_B", a, `/v1/orgs/:org/api-keys/${keyId}`, { method: "DELETE" })).status).toBe(403);
    expect((await req("org_A", a, `/v1/orgs/:org/api-keys/${keyId}`, { method: "DELETE" })).status).toBe(200);

    // Invites: only owners of that org.
    expect((await req("org_B", a, "/v1/orgs/:org/invites", { method: "POST", body: JSON.stringify({ email: "c@x.test", role: "member" }) })).status).toBe(403);
  });

  it("returns 401 without a session", async () => {
    const db = new FakeD1();
    const env = ENV(db);
    const r = await app.request("/v1/orgs", {}, env as never);
    expect(r.status).toBe(401);
    const r2 = await app.request("/v1/orgs/org_X/agents", {}, env as never);
    expect(r2.status).toBe(401);
  });

  it("invite accept adds the second user to exactly that org", async () => {
    const db = new FakeD1();
    const env = ENV(db);
    const a = await seedSession(db, "usr_a", "a@x.test");
    const c = await seedSession(db, "usr_c", "c@x.test");
    db.orgs.set("org_A", { id: "org_A", slug: "a", name: "A", plan: "free", created_at: "t" });
    db.memberships.set("org_A|usr_a", { org_id: "org_A", user_id: "usr_a", role: "owner" });
    const raw = "inviterawtoken-0123456789abcdef0123456789abcdef01234567";
    db.invites.set(await sha256Hex(raw), { id: "inv_1", org_id: "org_A", email: "c@x.test", role: "member", token_hash: await sha256Hex(raw), expires_at: "2999-01-01T00:00:00.000Z", accepted_at: null });
    const r = await app.request(`/v1/invites/${raw}/accept`, { method: "POST", headers: { ...cookie(c), "Content-Type": "application/json" } }, env as never);
    expect(r.status).toBe(200);
    expect(db.memberships.get("org_A|usr_c")?.role).toBe("member");
  });

  it("API key auth is org-bound and honors revocation", async () => {
    const db = new FakeD1();
    db.orgs.set("org_A", { id: "org_A", slug: "a", name: "A", plan: "free", created_at: "t" });
    const rawKey = "epik_0123456789abcdef0123456789abcdef01234567";
    db.apiKeys.set("key_1", { id: "key_1", org_id: "org_A", prefix: "01234567", key_hash: await sha256Hex(rawKey), scopes: "push", created_by: "usr_a", created_at: "t", last_used_at: null, revoked_at: null });
    const authed = await keyFromRequest(db as unknown as D1Database, new Request("https://x/", { headers: { Authorization: `Bearer ${rawKey}` } }));
    expect(authed?.orgId).toBe("org_A");
    expect(authed?.scopes).toEqual(["push"]);
    expect(await keyFromRequest(db as unknown as D1Database, new Request("https://x/", { headers: { Authorization: "Bearer epik_nope" } }))).toBeNull();
    db.apiKeys.get("key_1")!.revoked_at = "now";
    expect(await keyFromRequest(db as unknown as D1Database, new Request("https://x/", { headers: { Authorization: `Bearer ${rawKey}` } }))).toBeNull();
  });

  it("admin usage is founder-only", async () => {
    const db = new FakeD1();
    const env = ENV(db);
    const a = await seedSession(db, "usr_a", "a@x.test");
    const f = await seedSession(db, "usr_founder", "f@x.test");
    const r1 = await app.request("/admin/usage", { headers: cookie(a) }, env as never);
    expect(r1.status).toBe(403);
    const r2 = await app.request("/admin/usage", { headers: cookie(f) }, env as never);
    expect(r2.status).toBe(200);
    const body = (await r2.json()) as { limits: Record<string, number>; usage: Record<string, number> };
    expect(body.limits.workers_requests_per_day).toBe(100000);
    expect(body.usage.users).toBe(2);
  });
});
