// RED-TEAM suite (Wave 3): EPI Cloud privilege boundaries.
//
// These tests drive the real Hono app against an in-memory D1 stand-in.
// They assert the SECURE behaviour; against the current code some of them
// FAIL — that failure is the finding, and it becomes the regression guard
// once the route is fixed.
//
// C-01: POST /v1/orgs/:orgId/export mints a whole-org trust link and accepts
//        a `push`-scoped API key — the credential `epi cloud login` puts on a
//        recorder machine. Compare POST /v1/orgs/:orgId/share-links, which is
//        owner-only. The export route also skips the `shareLinks` plan limit.

import { describe, expect, it } from "vitest";
import { app } from "../src/index.ts";
import { sha256Hex } from "../src/lib/crypto.ts";

type Row = Record<string, unknown>;

class FakeD1 {
  orgs = new Map<string, Row>();
  users = new Map<string, Row>();
  sessions = new Map<string, Row>();
  memberships = new Map<string, Row>();
  apiKeys = new Map<string, Row>();
  links = new Map<string, Row>();
  agents = new Map<string, Row>();
  inboxes = new Map<string, Row>();
  artifacts: Row[] = [];
  audit: Row[] = [];

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
    if (q.startsWith("SELECT id, org_id, scopes FROM api_keys")) {
      const k = this.apiKeys.get(a[0] as string);
      return k ? { id: k.id, org_id: k.org_id, scopes: k.scopes } : null;
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM share_links")) {
      let n = 0;
      for (const l of this.links.values()) if (l.org_id === a[0] && l.revoked_at == null) n++;
      return { n };
    }
    if (q.startsWith("SELECT entry_hash FROM audit_log")) {
      const rows = this.audit.filter((r) => (r.org_id ?? null) === (a[0] ?? null));
      return rows.length ? { entry_hash: rows[rows.length - 1]!.entry_hash } : null;
    }
    throw new Error(`FakeD1 unhandled one: ${q}`);
  }

  private many(q: string, a: unknown[]): Row[] {
    if (q.startsWith("SELECT id, claimed_sha256, size_bytes, workflow_id FROM artifacts")) {
      return this.artifacts.filter((r) => r.org_id === a[0] && r.deleted_at == null);
    }
    if (q.startsWith("SELECT id, customer_label FROM inboxes")) {
      return [...this.inboxes.values()].filter((i) => i.org_id === a[0]);
    }
    if (q.startsWith("SELECT id, label, scope, created_at, expires_at, revoked_at FROM share_links")) {
      return [...this.links.values()].filter((l) => l.org_id === a[0]);
    }
    throw new Error(`FakeD1 unhandled many: ${q}`);
  }

  private exec(q: string, a: unknown[]): number {
    if (q.startsWith("INSERT INTO share_links")) {
      this.links.set(a[0] as string, {
        id: a[0], org_id: a[1], token_hash: a[2], label: a[3], scope: a[4],
        created_at: a[5], expires_at: a[6], revoked_at: null,
      });
      return 1;
    }
    if (q.startsWith("UPDATE api_keys SET last_used_at")) return 1;
    if (q.startsWith("INSERT INTO audit_log")) {
      this.audit.push({ org_id: a[0], actor: a[1], action: a[2], detail: a[3], at: a[4], prev_hash: a[5], entry_hash: a[6] });
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

const PUSH_KEY = "epik_" + "a".repeat(40);
const READ_KEY = "epik_" + "b".repeat(40);

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
  const sh = await sha256Hex("sess-owner");
  db.sessions.set(sh, { id_hash: sh, user_id: "u_owner", expires_at: "2999-01-01T00:00:00.000Z" });
  db.memberships.set("o1|u_owner", { org_id: "o1", user_id: "u_owner", role: "owner" });
  db.agents.set("g1", { id: "g1", org_id: "o1", name: "loans", status: "active" });
  db.inboxes.set("inb_1", { id: "inb_1", org_id: "o1", customer_label: "Acme Bank", closed_at: null });
  db.artifacts.push({
    id: "art_1", org_id: "o1", claimed_sha256: "d".repeat(64), size_bytes: 10,
    workflow_id: "wf-1", deleted_at: null,
  });
  db.apiKeys.set(await sha256Hex(PUSH_KEY), {
    id: "k_push", org_id: "o1", scopes: "push", revoked_at: null,
  });
  db.apiKeys.set(await sha256Hex(READ_KEY), {
    id: "k_read", org_id: "o1", scopes: "read", revoked_at: null,
  });
  const ck = (raw: string) => ({ Cookie: `epi_session=${raw}`, "Content-Type": "application/json" });
  const bearer = (key: string) => ({ Authorization: `Bearer ${key}` });
  return { db, env, ck, bearer };
}

describe("red-team: export route privilege boundary", () => {
  it("C-01 a push-only API key must not mint a whole-org trust link", async () => {
    const { env, bearer } = await setup();

    const res = await app.request("/v1/orgs/o1/export", {
      method: "POST",
      headers: bearer(PUSH_KEY),
    }, env as never);

    // A push key is a machine credential: it can upload evidence. It must not
    // be able to mint a reviewer-facing trust link covering the whole org.
    expect(res.status).toBe(403);
  });

  it("C-01 the export route must not bypass the shareLinks plan limit", async () => {
    const { db, env, ck, bearer } = await setup();

    // Free plan allows exactly 1 share link. Spend it.
    const first = await app.request("/v1/orgs/o1/share-links", {
      method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ label: "first" }),
    }, env as never);
    expect(first.status).toBe(201);
    expect(db.links.size).toBe(1);

    // A second link must be refused by the plan limit...
    const second = await app.request("/v1/orgs/o1/share-links", {
      method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ label: "second" }),
    }, env as never);
    expect(second.status).toBe(402);

    // ...and the full-export path must respect the same limit.
    const exported = await app.request("/v1/orgs/o1/export", {
      method: "POST", headers: ck("sess-owner"),
    }, env as never);
    expect(exported.status).toBe(402);
    expect(db.links.size).toBe(1);
  });

  it("C-01 the export route must not mint links for a member (owner-only)", async () => {
    const { db, env } = await setup();
    // Demote the session's user from owner to member, in the SAME db instance
    // the app is wired to.
    db.memberships.set("o1|u_owner", { org_id: "o1", user_id: "u_owner", role: "member" });

    const res = await app.request("/v1/orgs/o1/export", {
      method: "POST", headers: { Cookie: "epi_session=sess-owner", "Content-Type": "application/json" },
    }, env as never);

    expect(res.status).toBe(403);
  });

  it("control: a read-only API key also must not mint a trust link", async () => {
    const { env, bearer } = await setup();

    const res = await app.request("/v1/orgs/o1/export", {
      method: "POST",
      headers: bearer(READ_KEY),
    }, env as never);

    expect(res.status).toBe(403);
  });
});
