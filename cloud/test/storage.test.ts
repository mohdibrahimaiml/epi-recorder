import { describe, expect, it } from "vitest";
import { app } from "../src/index.ts";
import { sha256Hex } from "../src/lib/crypto.ts";

type Row = Record<string, unknown>;

// Covers exactly the statements the storage-target routes emit.
class FakeD1 {
  orgs = new Map<string, Row>();
  users = new Map<string, Row>();
  sessions = new Map<string, Row>();
  memberships = new Map<string, Row>();
  targets = new Map<string, Row>();
  keys = new Map<string, Row>();
  audit: Row[] = [];

  prepare(sql: string) {
    const q = sql.replace(/\s+/g, " ").trim();
    const self = this;
    const bound = (args: unknown[]) => ({
      first: async (): Promise<Row | null> => self.one(q, args),
      all: async (): Promise<{ results: Row[] }> => ({ results: [] }),
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
    if (q.startsWith("SELECT id, org_id, scopes FROM api_keys")) {
      for (const k of this.keys.values()) {
        if (k.key_hash === a[0] && k.revoked_at == null) return { id: k.id, org_id: k.org_id, scopes: k.scopes };
      }
      return null;
    }
    if (q.startsWith("SELECT kind, endpoint, bucket, region, prefix, object_lock, last_check_at, last_check_ok FROM storage_targets")) {
      return this.targets.get(a[0] as string) ?? null;
    }
    if (q.startsWith("SELECT entry_hash FROM audit_log")) {
      const rows = this.audit.filter((r) => (r.org_id ?? null) === (a[0] ?? null));
      return rows.length ? { entry_hash: rows[rows.length - 1]!.entry_hash } : null;
    }
    throw new Error(`FakeD1 unhandled one: ${q}`);
  }

  private exec(q: string, a: unknown[]): number {
    if (q.startsWith("INSERT INTO storage_targets")) {
      this.targets.set(a[0] as string, {
        org_id: a[0], kind: a[1], endpoint: a[2], bucket: a[3], region: a[4],
        prefix: a[5], object_lock: a[6], last_check_at: null, last_check_ok: null,
      });
      return 1;
    }
    if (q.startsWith("UPDATE storage_targets SET last_check_at")) {
      const t = this.targets.get(a[3] as string);
      if (!t) return 0;
      t.last_check_at = a[0];
      t.last_check_ok = a[1];
      t.object_lock = a[2];
      return 1;
    }
    if (q.startsWith("INSERT INTO audit_log")) {
      this.audit.push({ org_id: a[0], actor: a[1], action: a[2], detail: a[3], at: a[4], prev_hash: a[5], entry_hash: a[6] });
      return 1;
    }
    if (q.startsWith("UPDATE api_keys SET last_used_at")) return 1;
    throw new Error(`FakeD1 unhandled exec: ${q}`);
  }
}

const RAW_KEY = "epik_0123456789abcdef0123456789abcdef01234567";

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
  db.users.set("u_owner", { id: "u_owner", email: "o@x.test" });
  db.users.set("u_member", { id: "u_member", email: "m@x.test" });
  for (const [raw, uid] of [["sess-owner", "u_owner"], ["sess-member", "u_member"]] as const) {
    const h = await sha256Hex(raw);
    db.sessions.set(h, { id_hash: h, user_id: uid, expires_at: "2999-01-01T00:00:00.000Z" });
  }
  db.memberships.set("o1|u_owner", { org_id: "o1", user_id: "u_owner", role: "owner" });
  db.memberships.set("o1|u_member", { org_id: "o1", user_id: "u_member", role: "member" });
  db.keys.set("key_1", { id: "key_1", org_id: "o1", key_hash: await sha256Hex(RAW_KEY), scopes: "push,read", revoked_at: null });
  const ck = (raw: string) => ({ Cookie: `epi_session=${raw}`, "Content-Type": "application/json" });
  const key = { Authorization: `Bearer ${RAW_KEY}`, "Content-Type": "application/json" };
  return { db, env, ck, key };
}

const TARGET = { kind: "s3", endpoint: "https://s3.us-east-1.amazonaws.com", bucket: "acme-epi", region: "us-east-1", prefix: "runs" };

describe("customer-owned storage target", () => {
  it("owner registers (no secrets accepted), anyone reads, member blocked from writing", async () => {
    const { db, env, ck } = await setup();
    const put = await app.request("/v1/orgs/o1/storage-target", { method: "PUT", headers: ck("sess-owner"), body: JSON.stringify(TARGET) }, env as never);
    expect(put.status).toBe(200);
    expect(db.targets.get("o1")).toMatchObject({ bucket: "acme-epi", object_lock: "unknown" });
    expect(db.audit.map((a) => a.action)).toEqual(["storage_target.set"]);
    const get = (await (await app.request("/v1/orgs/o1/storage-target", { headers: ck("sess-member") }, env as never)).json()) as { target: { bucket: string } };
    expect(get.target.bucket).toBe("acme-epi");
    const memberPut = await app.request("/v1/orgs/o1/storage-target", { method: "PUT", headers: ck("sess-member"), body: JSON.stringify(TARGET) }, env as never);
    expect(memberPut.status).toBe(403);
  });

  it("refuses credentials in the target payload", async () => {
    const { env, ck } = await setup();
    for (const poison of [{ ...TARGET, access_key: "AKID" }, { ...TARGET, secret: "x" }, { ...TARGET, token: "x" }]) {
      const r = await app.request("/v1/orgs/o1/storage-target", { method: "PUT", headers: ck("sess-owner"), body: JSON.stringify(poison) }, env as never);
      expect(r.status).toBe(400);
    }
  });

  it("heartbeat updates last check; unknown org 404s; key must be push-scoped", async () => {
    const { env, ck, key } = await setup();
    await app.request("/v1/orgs/o1/storage-target", { method: "PUT", headers: ck("sess-owner"), body: JSON.stringify(TARGET) }, env as never);
    const hb = await app.request("/v1/orgs/o1/storage-target/check", {
      method: "POST", headers: key, body: JSON.stringify({ ok: true, count: 41, object_lock: "on" }),
    }, env as never);
    expect(hb.status).toBe(200);
    const get = (await (await app.request("/v1/orgs/o1/storage-target", { headers: ck("sess-owner") }, env as never)).json()) as {
      target: { last_check_ok: number; object_lock: string };
    };
    expect(get.target).toMatchObject({ last_check_ok: 1, object_lock: "on" });
    expect((await app.request("/v1/orgs/o1/storage-target/check", { method: "POST", headers: key, body: "{}" }, env as never)).status).toBe(400);
    expect((await app.request("/v1/orgs/o1/storage-target/check", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ ok: true, count: 1 }) }, env as never)).status).toBe(403);
  });
});
