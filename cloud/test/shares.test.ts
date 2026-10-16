import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { app } from "../src/index.ts";
import { sha256Hex } from "../src/lib/crypto.ts";

type Row = Record<string, unknown>;

class FakeD1 {
  orgs = new Map<string, Row>();
  users = new Map<string, Row>();
  sessions = new Map<string, Row>();
  memberships = new Map<string, Row>();
  links = new Map<string, Row>();
  events: Row[] = [];
  agents = new Map<string, Row>();
  inboxes = new Map<string, Row>();
  checkpoints: Row[] = [];
  artifacts: Row[] = [];
  keys: Row[] = [];
  audit: Row[] = [];
  counters = new Map<string, Row>();

  prepare(sql: string) {
    const q = sql.replace(/\s+/g, " ").trim();
    const self = this;
    const bound = (args: unknown[]) => ({
      first: async (): Promise<Row | null> => self.one(q, args),
      all: async (): Promise<{ results: Row[] }> => ({ results: self.many(q, args) }),
      run: async (): Promise<{ meta: { changes: number } }> => ({ meta: { changes: self.exec(q, args) } }),
    });
    return { bind: (...a: unknown[]) => bound(a), first: () => bound([]).first(), all: () => bound([]).all(), run: () => bound([]).run() };
  }

  private one(q: string, a: unknown[]): Row | null {
    if (q.includes("?") && a.length === 0) throw new Error(`FakeD1 unbound placeholders: ${q}`);
    if (q.startsWith("SELECT s.user_id")) {
      const s = this.sessions.get(a[0] as string);
      if (!s) return null;
      return { user_id: s.user_id, expires_at: s.expires_at, email: this.users.get(s.user_id as string)?.email ?? null };
    }
    if (q.startsWith("SELECT role FROM memberships")) return this.memberships.get(`${a[0]}|${a[1]}`) ?? null;
    if (q.startsWith("SELECT plan FROM orgs")) {
      const o = this.orgs.get(a[0] as string);
      return o ? { plan: o.plan } : null;
    }
    if (q.startsWith("SELECT name FROM orgs")) {
      const o = this.orgs.get(a[0] as string);
      return o ? { name: o.name } : null;
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM share_links")) {
      let n = 0;
      for (const l of this.links.values()) if (l.org_id === a[0] && l.revoked_at == null) n++;
      return { n };
    }
    if (q.startsWith("SELECT id, org_id, label, scope, expires_at, revoked_at FROM share_links WHERE token_hash")) {
      for (const l of this.links.values()) {
        if (l.token_hash === a[0]) return { id: l.id, org_id: l.org_id, label: l.label, scope: l.scope, expires_at: l.expires_at, revoked_at: l.revoked_at };
      }
      return null;
    }
    if (q.startsWith("SELECT id FROM share_links WHERE id = ? AND org_id = ?")) {
      const l = this.links.get(a[0] as string);
      return l && l.org_id === a[1] ? { id: l.id } : null;
    }
    if (q.startsWith("SELECT entry_hash FROM audit_log")) {
      const rows = this.audit.filter((r) => (r.org_id ?? null) === (a[0] ?? null));
      return rows.length ? { entry_hash: rows[rows.length - 1]!.entry_hash } : null;
    }
    if (q.startsWith("SELECT count, window_expires_at FROM rate_counters")) return this.counters.get(a[0] as string) ?? null;
    if (q.startsWith("SELECT COUNT(*) AS n FROM")) return { n: 0 };
    throw new Error(`FakeD1 unhandled one: ${q}`);
  }

  private many(q: string, a: unknown[]): Row[] {
    if (q.includes("?") && a.length === 0) throw new Error(`FakeD1 unbound placeholders: ${q}`);
    if (q.startsWith("SELECT id, label, scope, created_at, expires_at, revoked_at FROM share_links")) {
      return [...this.links.values()].filter((l) => l.org_id === a[0]);
    }
    if (q.startsWith("SELECT id, name, status FROM agents")) {
      return [...this.agents.values()].filter((g) => g.org_id === a[0]);
    }
    if (q.startsWith("SELECT id, customer_label, closed_at FROM inboxes")) {
      return [...this.inboxes.values()].filter((i) => i.org_id === a[0]);
    }
    if (q.startsWith("SELECT day, count, head_hash, signed_at, rekor_uuid FROM checkpoints")) {
      return this.checkpoints.filter((r) => r.inbox_id === a[0] && (r.day as string) >= (a[1] as string)).sort((x, y) => ((x.day as string) < (y.day as string) ? -1 : 1));
    }
    if (q.startsWith("SELECT id, agent_id, claimed_sha256")) return this.artifacts.filter((r) => r.org_id === a[0]);
    if (q.startsWith("SELECT fingerprint, label, valid_from, revoked_at, revoke_reason FROM org_keys")) {
      return this.keys.filter((r) => r.org_id === a[0]);
    }
    if (q.startsWith("SELECT kind, detail, at FROM trust_events")) {
      return this.events.filter((e) => e.share_link_id === a[0]);
    }
    throw new Error(`FakeD1 unhandled many: ${q}`);
  }

  private exec(q: string, a: unknown[]): number {
    if (q.startsWith("INSERT INTO share_links")) {
      this.links.set(a[0] as string, { id: a[0], org_id: a[1], token_hash: a[2], label: a[3], scope: a[4], created_at: a[5], expires_at: a[6], revoked_at: null });
      return 1;
    }
    if (q.startsWith("UPDATE share_links SET revoked_at")) {
      const l = this.links.get(a[1] as string);
      if (!l || l.org_id !== a[2] || l.revoked_at != null) return 0;
      l.revoked_at = a[0];
      return 1;
    }
    if (q.startsWith("INSERT INTO trust_events")) {
      this.events.push({ share_link_id: a[0], kind: a[1], detail: a[2], at: a[3] });
      return 1;
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

class FakeNS {
  counts = new Map<string, number>();
  idFromName(name: string) {
    return { name };
  }
  get(id: { name: string }) {
    const n = this.counts.get(id.name) ?? 0;
    return { fetch: async () => Response.json({ count: n, head_hash: "GENESIS" }) };
  }
}

async function setup() {
  const db = new FakeD1();
  const ns = new FakeNS();
  const env = {
    DB: db as unknown as D1Database,
    ROOM: {} as R2Bucket,
    WITNESS: ns as unknown as DurableObjectNamespace,
    APP_ORIGIN: "https://cloud.epilabs.org",
    PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
  };
  db.orgs.set("o1", { id: "o1", slug: "acme", name: "Acme Corp", plan: "free" });
  db.users.set("u_owner", { id: "u_owner", email: "o@x.test" });
  db.users.set("u_member", { id: "u_member", email: "m@x.test" });
  for (const [raw, uid] of [["sess-owner", "u_owner"], ["sess-member", "u_member"]] as const) {
    const h = await sha256Hex(raw);
    db.sessions.set(h, { id_hash: h, user_id: uid, expires_at: "2999-01-01T00:00:00.000Z" });
  }
  db.memberships.set("o1|u_owner", { org_id: "o1", user_id: "u_owner", role: "owner" });
  db.memberships.set("o1|u_member", { org_id: "o1", user_id: "u_member", role: "member" });
  db.agents.set("g1", { id: "g1", org_id: "o1", name: "loans", status: "active" });
  db.inboxes.set("inb_1", { id: "inb_1", org_id: "o1", customer_label: "Acme Bank", closed_at: null });
  ns.counts.set("inb_1", 40);
  const ck = (raw: string) => ({ Cookie: `epi_session=${raw}`, "Content-Type": "application/json" });
  return { db, env, ck };
}

describe("share links", () => {
  it("owner mints (token once), lists, revokes; member blocked; free limit 1", async () => {
    const { db, env, ck } = await setup();
    const mint = await app.request("/v1/orgs/o1/share-links", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ label: "Acme Bank Q3" }) }, env as never);
    expect(mint.status).toBe(201);
    const { id, token, url } = (await mint.json()) as { id: string; token: string; url: string };
    expect(token).toMatch(/^[0-9a-f]{64}$/);
    expect(url).toBe(`/t/${id}#k=${token}`);
    expect(db.links.get(id)!.token_hash).toBe(await sha256Hex(token)); // stored hashed
    const member = await app.request("/v1/orgs/o1/share-links", { method: "POST", headers: ck("sess-member"), body: JSON.stringify({ label: "x" }) }, env as never);
    expect(member.status).toBe(403);
    const second = await app.request("/v1/orgs/o1/share-links", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ label: "y" }) }, env as never);
    expect(second.status).toBe(402); // free: 1 link
    const list = (await (await app.request("/v1/orgs/o1/share-links", { headers: ck("sess-owner") }, env as never)).json()) as { links: { id: string }[] };
    expect(list.links).toHaveLength(1);
    expect((await app.request(`/v1/orgs/o1/share-links/${id}`, { method: "DELETE", headers: ck("sess-owner") }, env as never)).status).toBe(200);
    // Revoked token no longer resolves.
    const gone = await app.request(`/v1/trust/${id}`, { headers: { "X-EPI-Share-Token": token } }, env as never);
    expect(gone.status).toBe(404);
  });

  it("trust doc serves scoped data; expired links 404", async () => {
    const { db, env, ck } = await setup();
    const today = new Date().toISOString().slice(0, 10);
    db.checkpoints.push({ inbox_id: "inb_1", day: today, count: 40, head_hash: "ff", signed_at: today, rekor_uuid: "u1" });
    const mint = await app.request("/v1/orgs/o1/share-links", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ label: "Bank" }) }, env as never);
    const { id, token } = (await mint.json()) as { id: string; token: string };
    const doc = (await (await app.request(`/v1/trust/${id}`, { headers: { "X-EPI-Share-Token": token } }, env as never)).json()) as {
      vendor: string; agents: { name: string }[]; inboxes: { label: string; total_witnessed: number; d30: number; awaiting_checkpoint: boolean }[]; artifacts: unknown[]; keys: unknown[];
    };
    expect(doc.vendor).toBe("Acme Corp");
    expect(doc.agents.map((a) => a.name)).toEqual(["loans"]);
    expect(doc.inboxes[0]).toMatchObject({ label: "Acme Bank", total_witnessed: 40, d30: 40 });
    expect(doc.inboxes[0]!.awaiting_checkpoint).toBe(false);
    expect(doc.artifacts).toEqual([]);
    // Wrong slug, query token, and expired links all 404.
    expect((await app.request("/v1/trust/sh_nope", { headers: { "X-EPI-Share-Token": token } }, env as never)).status).toBe(404);
    expect((await app.request(`/v1/trust/${id}?k=${token}`, {}, env as never)).status).toBe(404);
    db.links.get(id)!.expires_at = "2000-01-01T00:00:00.000Z";
    expect((await app.request(`/v1/trust/${id}`, { headers: { "X-EPI-Share-Token": token } }, env as never)).status).toBe(404);
  });

  it("says awaiting-checkpoint instead of showing 0", async () => {
    const { env, ck } = await setup();
    // DO reports 40 entries (see setup) but no checkpoint rows exist yet.
    const mint = await app.request("/v1/orgs/o1/share-links", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ label: "Bank" }) }, env as never);
    const { id, token } = (await mint.json()) as { id: string; token: string };
    const doc = (await (await app.request(`/v1/trust/${id}`, { headers: { "X-EPI-Share-Token": token } }, env as never)).json()) as {
      inboxes: { total_witnessed: number; d30: number; awaiting_checkpoint: boolean }[];
    };
    expect(doc.inboxes[0]).toMatchObject({ total_witnessed: 40, d30: 0, awaiting_checkpoint: true });
  });

  it("events record human actions; vendors read them per link", async () => {
    const { db, env, ck } = await setup();
    const { id, token } = (await (await app.request("/v1/orgs/o1/share-links", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ label: "Bank" }) }, env as never)).json()) as { id: string; token: string };
    const h = { "X-EPI-Share-Token": token, "Content-Type": "application/json" };
    expect((await app.request(`/v1/trust/${id}/events`, { method: "POST", headers: h, body: JSON.stringify({ kind: "opened" }) }, env as never)).status).toBe(200);
    expect((await app.request(`/v1/trust/${id}/events`, { method: "POST", headers: h, body: JSON.stringify({ kind: "viewed" }) }, env as never)).status).toBe(400);
    const seen = (await (await app.request(`/v1/orgs/o1/share-links/${id}/events`, { headers: ck("sess-member") }, env as never)).json()) as { events: { kind: string }[] };
    expect(seen.events.map((e) => e.kind)).toEqual(["opened"]);
    expect(db.events).toHaveLength(1);
    // Other org's member sees nothing.
    db.orgs.set("o2", { id: "o2", slug: "evil", name: "Evil", plan: "free" });
    db.users.set("u_evil", { id: "u_evil", email: "e@x.test" });
    const he = await sha256Hex("sess-evil");
    db.sessions.set(he, { id_hash: he, user_id: "u_evil", expires_at: "2999-01-01T00:00:00.000Z" });
    db.memberships.set("o2|u_evil", { org_id: "o2", user_id: "u_evil", role: "owner" });
    const evilCk = { Cookie: "epi_session=sess-evil", "Content-Type": "application/json" };
    expect((await app.request(`/v1/orgs/o1/share-links/${id}/events`, { headers: evilCk }, env as never)).status).toBe(403);
  });
});

describe("server log hygiene", () => {
  it("no share token, key, or secret can reach logs", () => {
    // Request-handling code must never print: a stray console.log could
    // carry a token, key, or HMAC secret. Exactly one console.log exists:
    // the scheduled-cron summary in index.ts (counts only, no request data).
    const root = join(__dirname, "..", "src");
    const logged: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir, { withFileTypes: true })) {
        const p = join(dir, name.name);
        if (name.isDirectory()) walk(p);
        else if (p.endsWith(".ts") && /console\.(log|debug|info)/.test(readFileSync(p, "utf8"))) logged.push(p);
      }
    };
    walk(root);
    expect(logged.map((p) => p.replace(/\\/g, "/"))).toEqual([join(root, "index.ts").replace(/\\/g, "/")]);
    const lines = readFileSync(join(root, "index.ts"), "utf8").split("\n").filter((l) => /console\.(log|debug|info)/.test(l));
    expect(lines).toHaveLength(1);
    expect(lines.join(" ")).not.toMatch(/token|key|secret|header|cookie|auth/i);
  });
});
