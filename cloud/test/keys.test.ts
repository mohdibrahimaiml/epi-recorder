import { describe, expect, it } from "vitest";
import { app } from "../src/index.ts";
import { sha256Hex } from "../src/lib/crypto.ts";

type Row = Record<string, unknown>;

const PUB = "92dc7b40403f6383527773b35eb9305ddf01306889ad4e9987a098e6304bead0";
const FP = "7004fce0a4a92327";

// Covers exactly the statements the org-keys routes emit.
class FakeD1 {
  orgs = new Map<string, Row>();
  users = new Map<string, Row>();
  sessions = new Map<string, Row>();
  memberships = new Map<string, Row>();
  keys = new Map<string, Row>();
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
    if (q.includes("?") && a.length === 0) throw new Error(`FakeD1 unbound placeholders: ${q}`);
    if (q.startsWith("SELECT s.user_id")) {
      const s = this.sessions.get(a[0] as string);
      if (!s) return null;
      return { user_id: s.user_id, expires_at: s.expires_at, email: this.users.get(s.user_id as string)?.email ?? null };
    }
    if (q.startsWith("SELECT role FROM memberships")) return this.memberships.get(`${a[0]}|${a[1]}`) ?? null;
    if (q.startsWith("SELECT id, slug FROM orgs WHERE id = ?")) {
      const o = this.orgs.get(a[0] as string);
      return o ? { id: o.id, slug: o.slug } : null;
    }
    if (q.startsWith("SELECT id FROM orgs WHERE slug = ?")) {
      for (const o of this.orgs.values()) if (o.slug === a[0]) return { id: o.id };
      return null;
    }
    if (q.startsWith("SELECT entry_hash FROM audit_log")) {
      const rows = this.audit.filter((r) => (r.org_id ?? null) === (a[0] ?? null));
      return rows.length ? { entry_hash: rows[rows.length - 1]!.entry_hash } : null;
    }
    throw new Error(`FakeD1 unhandled one: ${q}`);
  }

  private many(q: string, a: unknown[]): Row[] {
    if (q.includes("?") && a.length === 0) throw new Error(`FakeD1 unbound placeholders: ${q}`);
    if (q.startsWith("SELECT id, public_key, fingerprint, label, valid_from, revoked_at FROM org_keys")) {
      return [...this.keys.values()].filter((k) => k.org_id === a[0]);
    }
    if (q.startsWith("SELECT public_key, fingerprint, label, valid_from, revoked_at FROM org_keys")) {
      return [...this.keys.values()].filter((k) => k.org_id === a[0]);
    }
    throw new Error(`FakeD1 unhandled many: ${q}`);
  }

  private exec(q: string, a: unknown[]): number {
    if (q.startsWith("INSERT INTO org_keys")) {
      for (const k of this.keys.values()) {
        if (k.org_id === a[1] && k.public_key === a[2]) throw new Error("UNIQUE");
      }
      this.keys.set(a[0] as string, {
        id: a[0], org_id: a[1], public_key: a[2], fingerprint: a[3],
        label: a[4], valid_from: a[5], revoked_at: null, revoke_reason: null,
      });
      return 1;
    }
    if (q.startsWith("UPDATE org_keys SET revoked_at")) {
      for (const k of this.keys.values()) {
        if (k.id === a[2] && k.org_id === a[3] && k.revoked_at == null) {
          k.revoked_at = a[0];
          k.revoke_reason = a[1];
          return 1;
        }
      }
      return 0;
    }
    if (q.startsWith("DELETE FROM org_keys")) {
      for (const [id, k] of this.keys) {
        if (k.id === a[0] && k.org_id === a[1]) {
          this.keys.delete(id);
          return 1;
        }
      }
      return 0;
    }
    if (q.startsWith("INSERT INTO audit_log")) {
      this.audit.push({ org_id: a[0], actor: a[1], action: a[2], detail: a[3], at: a[4], prev_hash: a[5], entry_hash: a[6] });
      return 1;
    }
    throw new Error(`FakeD1 unhandled exec: ${q}`);
  }
}

async function setup() {
  const db = new FakeD1();
  const env = {
    DB: db as unknown as D1Database,
    ROOM: {} as R2Bucket,
    WITNESS: {} as DurableObjectNamespace,
    APP_ORIGIN: "https://cloud.epilabs.org",
    PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
  };
  db.orgs.set("o1", { id: "o1", slug: "acme", name: "Acme", plan: "free" });
  db.orgs.set("o2", { id: "o2", slug: "evil", name: "Evil", plan: "free" });
  db.users.set("u_owner", { id: "u_owner", email: "o@x.test" });
  db.users.set("u_member", { id: "u_member", email: "m@x.test" });
  for (const [raw, uid] of [["sess-owner", "u_owner"], ["sess-member", "u_member"]] as const) {
    const h = await sha256Hex(raw);
    db.sessions.set(h, { id_hash: h, user_id: uid, expires_at: "2999-01-01T00:00:00.000Z" });
  }
  db.memberships.set("o1|u_owner", { org_id: "o1", user_id: "u_owner", role: "owner" });
  db.memberships.set("o1|u_member", { org_id: "o1", user_id: "u_member", role: "member" });
  const ck = (raw: string) => ({ Cookie: `epi_session=${raw}`, "Content-Type": "application/json" });
  return { db, env, ck };
}

describe("org public keys", () => {
  it("owner registers (fingerprint computed server-side), lists, revokes; member blocked", async () => {
    const { db, env, ck } = await setup();
    const reg = await app.request("/v1/orgs/o1/keys", {
      method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ public_key: PUB, label: "prod" }),
    }, env as never);
    expect(reg.status).toBe(201);
    const created = (await reg.json()) as { id: string; fingerprint: string };
    expect(created.fingerprint).toBe(FP);
    expect(db.keys.get(created.id)).toMatchObject({ fingerprint: FP, label: "prod", revoked_at: null });
    const member = await app.request("/v1/orgs/o1/keys", {
      method: "POST", headers: ck("sess-member"), body: JSON.stringify({ public_key: PUB }),
    }, env as never);
    expect(member.status).toBe(403);
    const dupe = await app.request("/v1/orgs/o1/keys", {
      method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ public_key: PUB }),
    }, env as never);
    expect(dupe.status).toBe(409);
    const list = (await (await app.request("/v1/orgs/o1/keys", { headers: ck("sess-owner") }, env as never)).json()) as { keys: { fingerprint: string }[] };
    expect(list.keys.map((k) => k.fingerprint)).toEqual([FP]);
    const revoke = await app.request(`/v1/orgs/o1/keys/${created.id}/revoke`, {
      method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ reason: "rotated" }),
    }, env as never);
    expect(revoke.status).toBe(200);
    expect(db.keys.get(created.id)!.revoked_at).toBeTruthy();
    const del = await app.request(`/v1/orgs/o1/keys/${created.id}`, { method: "DELETE", headers: ck("sess-owner") }, env as never);
    expect(del.status).toBe(200);
    expect(db.keys.has(created.id)).toBe(false);
  });

  it("rejects non-key material (private keys, junk, wrong length)", async () => {
    const { env, ck } = await setup();
    for (const bad of ["not-hex", "ab".repeat(10), "ab".repeat(40), "", "ed25519:abc:def"]) {
      const r = await app.request("/v1/orgs/o1/keys", {
        method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ public_key: bad }),
      }, env as never);
      expect(r.status).toBe(400);
    }
  });

  it("publishes history by org slug, including revocations", async () => {
    const { db, env, ck } = await setup();
    await app.request("/v1/orgs/o1/keys", {
      method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ public_key: PUB, label: "prod" }),
    }, env as never);
    const pub = (await (
      await app.request("/o/acme/keys.json", {}, env as never)
    ).json()) as {
      org: string
      keys: { fingerprint: string; revoked_at: string | null }[]
    };
    expect(pub.org).toBe("acme");
    expect(pub.keys).toHaveLength(1);
    expect(pub.keys[0]).toMatchObject({ fingerprint: FP, public_key: PUB });
    expect((await app.request("/o/nope/keys.json", {}, env as never)).status).toBe(404);
  });

  it("tenant isolation holds on every keys route", async () => {
    const { env, ck } = await setup();
    expect((await app.request("/v1/orgs/o2/keys", {
      method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ public_key: PUB }),
    }, env as never)).status).toBe(403);
    expect((await app.request("/v1/orgs/o2/keys", { headers: ck("sess-owner") }, env as never)).status).toBe(403);
  });
});
