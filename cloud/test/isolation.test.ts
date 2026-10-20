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
    if (q.startsWith("SELECT user_id FROM memberships WHERE org_id = ? AND role")) {
      const owners = [...this.memberships.values()]
        .filter((m) => m.org_id === a[0] && m.role === a[1])
        .map((m) => m.user_id as string)
        .sort();
      return owners.length ? { user_id: owners[0] } : null;
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
    if (q.startsWith("SELECT id, org_id, role, expires_at, accepted_at FROM invites") || q.startsWith("SELECT id, org_id, email, role, expires_at, accepted_at FROM invites")) {
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
    if (q.startsWith("SELECT id, email_verified FROM users WHERE email") || q.startsWith("SELECT id FROM users WHERE email")) {
      for (const u of this.users.values()) if (u.email === a[0]) return { id: u.id, email_verified: u.email_verified ?? 0 };
      return null;
    }
    if (q.startsWith("SELECT email FROM users WHERE id")) {
      const u = this.users.get(a[0] as string);
      return u ? { email: u.email } : null;
    }
    if (q.startsWith("SELECT email_verified FROM users WHERE id")) {
      const u = this.users.get(a[0] as string);
      return u ? { email_verified: u.email_verified ?? 0 } : null;
    }
    if (q.startsWith("SELECT user_id FROM identities")) return null;
    if (q.includes("FROM device_codes")) return null;
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
    if (q.startsWith("SELECT id, slug, name, plan FROM orgs")) {
      return [...this.orgs.values()].map((o) => ({ id: o.id, slug: o.slug, name: o.name, plan: o.plan }));
    }
    if (q.startsWith("SELECT id, name, status, created_at FROM agents")) {
      return [...this.agents.values()].filter((g) => g.org_id === a[0]).map((g) => ({ id: g.id, name: g.name, status: g.status, created_at: g.created_at }));
    }
    if (q.startsWith("SELECT id, prefix, scopes")) {
      return [...this.apiKeys.values()].filter((k) => k.org_id === a[0]).map((k) => ({ id: k.id, prefix: k.prefix, scopes: k.scopes, label: k.label ?? null, created_by: k.created_by, created_at: k.created_at, last_used_at: k.last_used_at, revoked_at: k.revoked_at }));
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
      // New: (id, email, display_name, email_verified, created_at); old: 4-col.
      if (a.length === 5) this.users.set(a[0] as string, { id: a[0], email: a[1], display_name: a[2], email_verified: a[3], created_at: a[4] });
      else this.users.set(a[0] as string, { id: a[0], email: a[1], display_name: a[2], email_verified: 0, created_at: a[3] });
      return 1;
    }
    if (q.startsWith("UPDATE users SET email = ?, email_verified = 1")) {
      const u = this.users.get(a[1] as string);
      if (u) { u.email = a[0]; u.email_verified = 1; }
      return 1;
    }
    if (q.startsWith("UPDATE users SET email")) {
      const u = this.users.get(a[1] as string);
      if (u) u.email = a[0];
      return 1;
    }
    if (q.startsWith("UPDATE orgs SET plan")) {
      const o = this.orgs.get(a[1] as string);
      if (!o) return 0;
      o.plan = a[0];
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
      this.apiKeys.set(a[0] as string, { id: a[0], org_id: a[1], prefix: a[2], key_hash: a[3], scopes: a[4], label: a[5] ?? null, created_by: a[6], created_at: a[7], last_used_at: null, revoked_at: null });
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
    if (q.startsWith("INSERT INTO device_codes") || q.startsWith("UPDATE device_codes") || q.startsWith("DELETE FROM device_codes")) return 1;
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

async function seedSession(db: FakeD1, userId: string, email: string, verified = 1): Promise<string> {
  db.users.set(userId, { id: userId, email, display_name: "T", created_at: "t", email_verified: verified });
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
    // Labels round-trip (device names for CLI logins).
    const labeled = await req("org_A", a, "/v1/orgs/:org/api-keys", { method: "POST", body: JSON.stringify({ scopes: ["read"], label: "laptop-1" }) });
    expect(labeled.status).toBe(201);
    const listed = (await (await req("org_A", a, "/v1/orgs/:org/api-keys")).json()) as { keys: { id: string; label: string | null }[] };
    const labeledId = ((await labeled.json()) as { id: string }).id;
    expect(listed.keys.find((k) => k.id === keyId)?.label).toBeNull();
    expect(listed.keys.find((k) => k.id === labeledId)?.label).toBe("laptop-1");
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

  it("an invite only works for the email it was made for (a forwarded link can't make someone owner)", async () => {
    const db = new FakeD1();
    const env = ENV(db);
    await seedSession(db, "usr_a", "a@x.test");
    const m = await seedSession(db, "usr_m", "mallory@x.test");
    db.orgs.set("org_A", { id: "org_A", slug: "a", name: "A", plan: "free", created_at: "t" });
    db.memberships.set("org_A|usr_a", { org_id: "org_A", user_id: "usr_a", role: "owner" });
    const raw = "inviterawtoken-ownerinvite-0123456789abcdef0123456789abcdef";
    db.invites.set(await sha256Hex(raw), { id: "inv_2", org_id: "org_A", email: "Boss@X.test", role: "owner", token_hash: await sha256Hex(raw), expires_at: "2999-01-01T00:00:00.000Z", accepted_at: null });
    const r = await app.request(`/v1/invites/${raw}/accept`, { method: "POST", headers: { ...cookie(m), "Content-Type": "application/json" } }, env as never);
    expect(r.status).toBe(403);
    expect(((await r.json()) as { error: { code: string } }).error.code).toBe("wrong_account");
    expect(db.memberships.get("org_A|usr_m")).toBeUndefined();
    // The invited address (any case) can still accept.
    const b = await seedSession(db, "usr_b", "boss@x.test");
    const ok = await app.request(`/v1/invites/${raw}/accept`, { method: "POST", headers: { ...cookie(b), "Content-Type": "application/json" } }, env as never);
    expect(ok.status).toBe(200);
    expect(db.memberships.get("org_A|usr_b")?.role).toBe("owner");
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

  it("founder plan admin lists workspaces and changes plans (audited); others get 403", async () => {
    const db = new FakeD1();
    const env = ENV(db);
    const a = await seedSession(db, "usr_a", "a@x.test");
    const f = await seedSession(db, "usr_founder", "f@x.test");
    db.orgs.set("org_A", { id: "org_A", slug: "a", name: "A Corp", plan: "free", created_at: "t" });
    db.memberships.set("org_A|usr_a", { org_id: "org_A", user_id: "usr_a", role: "owner" });

    // Non-founder: 403 on list and plan change. No session: 401.
    expect((await app.request("/admin/orgs", { headers: cookie(a) }, env as never)).status).toBe(403);
    const denied = await app.request("/admin/orgs/org_A/plan", {
      method: "POST", headers: { ...cookie(a), "Content-Type": "application/json" }, body: JSON.stringify({ plan: "enterprise" }),
    }, env as never);
    expect(denied.status).toBe(403);
    expect((await app.request("/admin/orgs", {}, env as never)).status).toBe(401);
    expect(db.orgs.get("org_A")!.plan).toBe("free");

    // Founder: list shows the workspace with owner email and usage.
    const list = await app.request("/admin/orgs", { headers: cookie(f) }, env as never);
    expect(list.status).toBe(200);
    const orgs = ((await list.json()) as { orgs: { id: string; name: string; plan: string; owner_email: string; usage: Record<string, number> }[] }).orgs;
    expect(orgs).toHaveLength(1);
    expect(orgs[0]).toMatchObject({ id: "org_A", name: "A Corp", plan: "free", owner_email: "a@x.test" });

    // Bad plan value rejected; unknown workspace 404s.
    const bad = await app.request("/admin/orgs/org_A/plan", {
      method: "POST", headers: { ...cookie(f), "Content-Type": "application/json" }, body: JSON.stringify({ plan: "platinum" }),
    }, env as never);
    expect(bad.status).toBe(400);
    const missing = await app.request("/admin/orgs/nope/plan", {
      method: "POST", headers: { ...cookie(f), "Content-Type": "application/json" }, body: JSON.stringify({ plan: "enterprise" }),
    }, env as never);
    expect(missing.status).toBe(404);

    // Change the plan: stored, audited, then visible in the list.
    const change = await app.request("/admin/orgs/org_A/plan", {
      method: "POST", headers: { ...cookie(f), "Content-Type": "application/json" }, body: JSON.stringify({ plan: "enterprise" }),
    }, env as never);
    expect(change.status).toBe(200);
    expect(await change.json()).toMatchObject({ id: "org_A", plan: "enterprise" });
    expect(db.orgs.get("org_A")!.plan).toBe("enterprise");
    expect(db.audit.map((r) => r.action)).toContain("org.plan");
    const again = (await (await app.request("/admin/orgs", { headers: cookie(f) }, env as never)).json()) as { orgs: { plan: string }[] };
    expect(again.orgs[0]!.plan).toBe("enterprise");

    // Founder page renders for a signed-in founder, showing who is signed in.
    const pageRes = await app.request("/admin", { headers: cookie(f) }, env as never);
    expect(pageRes.status).toBe(200);
    const pageHtml = await pageRes.text();
    expect(pageHtml).toContain("Workspaces");
    expect(pageHtml).toContain("f@x.test");
  });

  it("founder allowlist needs a verified login: unverified ids get 403", async () => {
    const db = new FakeD1();
    const base = ENV(db);
    const f = await seedSession(db, "usr_founder", "f@x.test");
    const u = await seedSession(db, "usr_unverified", "someone-else@x.test", 0);
    const env = { ...base, FOUNDER_USER_IDS: "usr_founder,usr_unverified" };
    // Verified founder: fine.
    expect((await app.request("/admin/orgs", { headers: cookie(f) }, env as never)).status).toBe(200);
    // Same allowlist, but the login never verified its email: blocked
    // everywhere, because a bare id must not grant founder power.
    expect((await app.request("/admin/orgs", { headers: cookie(u) }, env as never)).status).toBe(403);
    expect((await app.request("/admin/usage", { headers: cookie(u) }, env as never)).status).toBe(403);
    expect((await app.request("/admin", { headers: cookie(u) }, env as never)).status).toBe(403);
  });
});
