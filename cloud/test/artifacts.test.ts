import { describe, expect, it } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { app } from "../src/index.ts";
import { hmacHex, sha256Hex } from "../src/lib/crypto.ts";
import { sealSecret } from "../src/lib/secretbox.ts";
import { purgeExpiredArtifacts } from "../src/retention.ts";
import { WitnessInbox } from "../src/do/witness.ts";

type Row = Record<string, unknown>;
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const FIXTURE_MANIFEST = readFileSync(join(root, "test", "fixtures", "sample-manifest.json"), "utf8");
const BOX_KEY = "ab".repeat(32);

function doAdapter(db: DatabaseSync) {
  return {
    exec(sql: string, ...params: unknown[]) {
      const p = params as never[];
      if (/^\s*select/i.test(sql) || /returning/i.test(sql)) {
        const stmt = db.prepare(sql);
        return {
          toArray: () => stmt.all(...p) as Row[],
          one: () => (stmt.get(...p) as Row | undefined) ?? undefined,
        };
      }
      db.prepare(sql).run(...p);
      return { toArray: () => [] as Row[], one: () => undefined };
    },
  };
}

class FakeInboxNS {
  boxes = new Map<string, WitnessInbox>();
  idFromName(name: string) {
    return { name };
  }
  get(id: { name: string }) {
    let b = this.boxes.get(id.name);
    if (!b) {
      const db = new DatabaseSync(":memory:");
      b = new WitnessInbox({ storage: { sql: doAdapter(db) } } as unknown as DurableObjectState);
      this.boxes.set(id.name, b);
    }
    const box = b;
    return { fetch: (url: string, init?: RequestInit) => box.fetch(new Request(`https://inbox${new URL(url).pathname}${new URL(url).search}`, init)) };
  }
}

class FakeR2 {
  store = new Map<string, Uint8Array>();
  async put(key: string, body: unknown) {
    const bytes = await readBody(body);
    this.store.set(key, bytes);
  }
  async get(key: string) {
    const b = this.store.get(key);
    return b ? { body: b } : null;
  }
  async delete(key: string) {
    this.store.delete(key);
  }
}

async function readBody(body: unknown): Promise<Uint8Array> {
  if (body instanceof Uint8Array) return body;
  if (typeof body === "string") return new TextEncoder().encode(body);
  const reader = (body as ReadableStream<Uint8Array>).getReader();
  const chunks: Uint8Array[] = [];
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) chunks.push(value);
  }
  const out = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

// Covers exactly the statements the artifact routes emit.
class FakeD1 {
  orgs = new Map<string, Row>();
  users = new Map<string, Row>();
  sessions = new Map<string, Row>();
  memberships = new Map<string, Row>();
  inboxes = new Map<string, Row>();
  agents = new Map<string, Row>();
  artifacts = new Map<string, Row>();
  links = new Map<string, Row>();
  keys = new Map<string, Row>();
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
    if (q.startsWith("SELECT COUNT(*) AS n FROM agents WHERE org_id = ?")) {
      let n = 0;
      for (const g of this.agents.values()) if (g.org_id === a[0] && g.status === "active") n++;
      return { n };
    }
    if (q.startsWith("SELECT id, hmac_secret_enc FROM inboxes WHERE org_id = ? AND customer_label = ?")) {
      for (const i of this.inboxes.values()) {
        if (i.org_id === a[0] && i.customer_label === a[1] && i.closed_at == null) {
          return { id: i.id, hmac_secret_enc: i.hmac_secret_enc };
        }
      }
      return null;
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM inboxes WHERE org_id = ?")) {
      let n = 0;
      for (const i of this.inboxes.values()) if (i.org_id === a[0] && i.closed_at == null) n++;
      return { n };
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM artifacts")) {
      let n = 0;
      for (const r of this.artifacts.values()) if (r.org_id === a[0] && r.deleted_at == null) n++;
      return { n };
    }
    if (q.startsWith("SELECT id, agent_id, manifest_json, upload_state, witness_status, signature_check FROM artifacts")) {
      for (const r of this.artifacts.values()) {
        if (r.org_id === a[0] && r.claimed_sha256 === a[1]) {
          return { id: r.id, agent_id: r.agent_id ?? null, manifest_json: r.manifest_json, upload_state: r.upload_state, witness_status: r.witness_status, signature_check: r.signature_check };
        }
      }
      return null;
    }
    if (q.startsWith("SELECT name FROM agents WHERE id = ?")) {
      for (const g of this.agents.values()) if (g.id === a[0]) return { name: g.name };
      return null;
    }
    if (q.startsWith("SELECT id FROM agents WHERE org_id = ? AND name = ?")) {
      for (const g of this.agents.values()) if (g.org_id === a[0] && g.name === a[1]) return { id: g.id };
      return null;
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM agents WHERE org_id = ?")) {
      let n = 0;
      for (const g of this.agents.values()) if (g.org_id === a[0] && g.status === "active") n++;
      return { n };
    }
    if (q.startsWith("SELECT id, hmac_secret_enc FROM inboxes WHERE org_id = ? AND customer_label = ?")) {
      for (const i of this.inboxes.values()) {
        if (i.org_id === a[0] && i.customer_label === a[1] && i.closed_at == null) {
          return { id: i.id, hmac_secret_enc: i.hmac_secret_enc };
        }
      }
      return null;
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM inboxes WHERE org_id = ?")) {
      let n = 0;
      for (const i of this.inboxes.values()) if (i.org_id === a[0] && i.closed_at == null) n++;
      return { n };
    }
    if (q.startsWith("SELECT id, size_bytes, object_key, upload_state FROM artifacts")) {
      const r = this.artifacts.get(a[0] as string);
      return r && r.org_id === a[1] && r.deleted_at == null ? { id: r.id, size_bytes: r.size_bytes, object_key: r.object_key, upload_state: r.upload_state } : null;
    }
    if (q.startsWith("SELECT id, agent_id, object_key, upload_state FROM artifacts")) {
      const r = this.artifacts.get(a[0] as string);
      return r && r.org_id === a[1] && r.deleted_at == null ? { id: r.id, agent_id: r.agent_id, object_key: r.object_key, upload_state: r.upload_state } : null;
    }
    if (q.startsWith("SELECT id, object_key, legal_hold FROM artifacts")) {
      const r = this.artifacts.get(a[0] as string);
      return r && r.org_id === a[1] && r.deleted_at == null ? { id: r.id, object_key: r.object_key, legal_hold: r.legal_hold } : null;
    }
    if (q.startsWith("SELECT id, manifest_json, claimed_sha256 FROM artifacts")) {
      const r = this.artifacts.get(a[0] as string);
      return r && r.org_id === a[1] && r.deleted_at == null ? { id: r.id, manifest_json: r.manifest_json, claimed_sha256: r.claimed_sha256 } : null;
    }
    if (q.includes("FROM artifacts WHERE id = ?")) {
      const r = this.artifacts.get(a[0] as string);
      if (!r || r.org_id !== a[1] || r.deleted_at != null) return null;
      const { manifest_json: _omit, object_key: _key, ...rest } = r;
      void _omit;
      void _key;
      return rest;
    }
    if (q.startsWith("SELECT id, org_id, scopes FROM api_keys")) {
      for (const k of this.keys.values()) {
        if (k.key_hash === a[0] && k.revoked_at == null) return { id: k.id, org_id: k.org_id, scopes: k.scopes };
      }
      return null;
    }
    if (q.startsWith("SELECT id, org_id, label, scope, expires_at, revoked_at FROM share_links WHERE token_hash")) {
      for (const l of this.links.values()) {
        if (l.token_hash === a[0]) return { id: l.id, org_id: l.org_id, label: l.label, scope: l.scope, expires_at: l.expires_at, revoked_at: l.revoked_at };
      }
      return null;
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
    if (q.startsWith("SELECT id FROM inboxes WHERE org_id = ? AND closed_at IS NULL")) {
      return [...this.inboxes.values()].filter((i) => i.org_id === a[0] && i.closed_at == null).map((i) => ({ id: i.id }));
    }
    if (q.startsWith("SELECT id, customer_label FROM inboxes")) {
      return [...this.inboxes.values()].filter((i) => i.org_id === a[0]);
    }
    if (q.includes("FROM artifacts WHERE org_id = ? AND deleted_at IS NULL ORDER BY uploaded_at DESC")) {
      return [...this.artifacts.values()].filter((r) => r.org_id === a[0] && r.deleted_at == null);
    }
    if (q.startsWith("SELECT id, org_id, object_key FROM artifacts WHERE deleted_at IS NULL")) {
      return [...this.artifacts.values()].filter((r) => r.deleted_at == null && r.legal_hold === 0 && (r.retention_until as string) <= (a[0] as string));
    }
    throw new Error(`FakeD1 unhandled many: ${q}`);
  }

  private exec(q: string, a: unknown[]): number {
    if (q.startsWith("INSERT INTO artifacts")) {
      this.artifacts.set(a[0] as string, {
        id: a[0], org_id: a[1], agent_id: a[2], claimed_sha256: a[3], claimed_crc32: a[4], size_bytes: a[5],
        manifest_json: a[6], spec_version: a[7], workflow_id: a[8], goal: a[9], steps: a[10], sealed_at: a[11],
        key_fingerprint: a[12], signature_check: a[13], witness_status: a[14], reason: a[15], object_key: a[16],
        upload_state: "pending", uploaded_at: a[17], retention_until: a[18], legal_hold: 0, deleted_at: null,
      });
      return 1;
    }
    if (q.startsWith("UPDATE artifacts SET upload_state")) {
      for (const r of this.artifacts.values()) if (r.id === a[0]) r.upload_state = "stored";
      return 1;
    }
    if (q.startsWith("UPDATE artifacts SET legal_hold")) {
      for (const r of this.artifacts.values()) {
        if (r.id === a[1] && r.org_id === a[2] && r.deleted_at == null) {
          r.legal_hold = a[0];
          return 1;
        }
      }
      return 0;
    }
    if (q.startsWith("UPDATE artifacts SET agent_id")) {
      for (const r of this.artifacts.values()) {
        if (r.id === a[2] && r.org_id !== undefined) {
          r.agent_id = a[0];
          r.witness_status = a[1];
          return 1;
        }
      }
      return 0;
    }
    if (q.startsWith("UPDATE artifacts SET deleted_at")) {
      for (const r of this.artifacts.values()) if (r.id === a[1]) r.deleted_at = a[0];
      return 1;
    }
    if (q.startsWith("INSERT INTO agents")) {
      this.agents.set(a[0] as string, { id: a[0], org_id: a[1], name: a[2], status: "active", created_at: a[3] });
      return 1;
    }
    if (q.startsWith("INSERT INTO inboxes")) {
      this.inboxes.set(a[0] as string, { id: a[0], org_id: a[1], customer_label: a[2], hmac_secret_enc: a[3], created_at: a[4], closed_at: a[5] });
      return 1;
    }
    if (q.startsWith("INSERT INTO orgs")) {
      this.orgs.set(a[0] as string, { id: a[0], slug: a[1], name: a[2], plan: "free", created_at: a[3] });
      return 1;
    }
    if (q.startsWith("INSERT INTO memberships")) {
      this.memberships.set(`${a[0]}|${a[1]}`, { org_id: a[0], user_id: a[1], role: a.length > 2 ? a[2] : "owner" });
      return 1;
    }
    if (q.startsWith("INSERT INTO users")) {
      this.users.set(a[0] as string, { id: a[0], email: a[1], display_name: a[2], email_verified: a[3], created_at: a[4] });
      return 1;
    }
    if (q.startsWith("INSERT INTO sessions")) {
      this.sessions.set(a[0] as string, { id_hash: a[0], user_id: a[1], expires_at: a[2] });
      return 1;
    }
    if (q.startsWith("INSERT INTO share_links")) {
      this.links.set(a[0] as string, { id: a[0], org_id: a[1], token_hash: a[2], label: a[3], scope: a[4], created_at: a[5], expires_at: a[6], revoked_at: null });
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
    if (q.startsWith("UPDATE api_keys SET last_used_at")) return 1;
    throw new Error(`FakeD1 unhandled exec: ${q}`);
  }
}

const RAW_KEY = "epik_0123456789abcdef0123456789abcdef01234567";

async function setup(opts: { withWitness?: boolean } = {}) {
  const db = new FakeD1();
  const ns = new FakeInboxNS();
  const r2 = new FakeR2();
  const env = {
    DB: db as unknown as D1Database,
    ROOM: r2 as unknown as R2Bucket,
    WITNESS: ns as unknown as DurableObjectNamespace,
    APP_ORIGIN: "https://cloud.epilabs.org",
    PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
    INBOX_SECRET_KEY: BOX_KEY,
  };
  db.orgs.set("o1", { id: "o1", slug: "acme", name: "Acme", plan: "startup" });
  db.orgs.set("o2", { id: "o2", slug: "evil", name: "Evil", plan: "free" });
  db.users.set("u_owner", { id: "u_owner", email: "o@x.test" });
  db.users.set("u_viewer", { id: "u_viewer", email: "v@x.test" });
  for (const [raw, uid] of [["sess-owner", "u_owner"], ["sess-viewer", "u_viewer"]] as const) {
    const h = await sha256Hex(raw);
    db.sessions.set(h, { id_hash: h, user_id: uid, expires_at: "2999-01-01T00:00:00.000Z" });
  }
  db.memberships.set("o1|u_owner", { org_id: "o1", user_id: "u_owner", role: "owner" });
  db.memberships.set("o1|u_viewer", { org_id: "o1", user_id: "u_viewer", role: "viewer" });
  db.agents.set("g1", { id: "g1", org_id: "o1", name: "loans", status: "active" });
  db.keys.set("key_1", { id: "key_1", org_id: "o1", key_hash: await sha256Hex(RAW_KEY), scopes: "push,read", revoked_at: null });
  db.inboxes.set("inb_1", { id: "inb_1", org_id: "o1", customer_label: "Acme Bank", hmac_secret_enc: await sealSecret(BOX_KEY, "s3cr3t"), created_at: "t", closed_at: null });
  if (opts.withWitness) {
    const stub = ns.get(ns.idFromName("inb_1"));
    const payload = JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: "other-workflow", file_sha256: "FILEHASH", content_digest: "DIGEST" });
    await stub.fetch("https://inbox/append", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload_raw: payload }) });
  }
  const ck = (raw: string) => ({ Cookie: `epi_session=${raw}`, "Content-Type": "application/json" });
  const key = { Authorization: `Bearer ${RAW_KEY}`, "Content-Type": "application/json" };
  return { db, ns, r2, env, ck, key };
}

const FILE_BYTES = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
// sha256 of FILE_BYTES (computed with Python hashlib).
const FILE_SHA = "66840dda154e8a113c31dd0ad32f7f3a366a80e8136979d8f5a101d3d29d6f72";

function initBody(over: Record<string, unknown> = {}) {
  return {
    manifest_json: FIXTURE_MANIFEST,
    claimed_sha256: FILE_SHA,
    claimed_crc32: 12345,
    size_bytes: FILE_BYTES.length,
    agent: "loans",
    reason: "sample",
    ...over,
  };
}

describe("push flow", () => {
  it("init verifies the seal, checks the witness, streams bytes to R2", async () => {
    const { db, r2, env, key } = await setup();
    const stub = (env.WITNESS as unknown as FakeInboxNS).get((env.WITNESS as unknown as FakeInboxNS).idFromName("inb_1"));
    const manifest = JSON.parse(FIXTURE_MANIFEST) as { workflow_id: string };
    await stub.fetch("https://inbox/append", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload_raw: JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: manifest.workflow_id, file_sha256: FILE_SHA }) }),
    });
    const init = await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody()) }, env as never);
    expect(init.status).toBe(201);
    const created = (await init.json()) as { id: string; put_url: string; witness_status: string; signature_check: string };
    expect(created).toMatchObject({ witness_status: "witnessed", signature_check: "valid" });
    expect(created.put_url).toContain(created.id);
    const put = await app.request(`/v1/orgs/o1/artifacts/${created.id}/content`, {
      method: "PUT", headers: { ...key, "Content-Length": String(FILE_BYTES.length) }, body: FILE_BYTES,
    }, env as never);
    expect(put.status).toBe(200);
    expect(r2.store.get(`o1/${created.id}.epi`)).toEqual(FILE_BYTES);
    const one = (await (await app.request(`/v1/orgs/o1/artifacts/${created.id}`, { headers: key }, env as never)).json()) as { content_url: string; witness_status: string };
    expect(one.content_url).toContain(created.id);
    expect(one.witness_status).toBe("witnessed");
    const content = await app.request(`/v1/orgs/o1/artifacts/${created.id}/content`, { headers: key }, env as never);
    expect(content.status).toBe(200);
    expect(content.headers.get("Content-Disposition")).toContain("attachment");
    expect(new Uint8Array(await content.arrayBuffer())).toEqual(FILE_BYTES);
    const row = [...db.artifacts.values()][0]!;
    expect(row.key_fingerprint).toBe("7004fce0a4a92327");
    expect(row.reason).toBe("sample");
    expect(db.audit.map((a) => a.action)).toEqual(["artifact.init", "artifact.store"]);
  });

  it("marks tampered, unsigned, and legacy manifests honestly", async () => {
    const { env, key } = await setup();
    const tampered = FIXTURE_MANIFEST.replace("Website sample.epi", "Website sample!epi");
    const t = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ manifest_json: tampered })) }, env as never)).json()) as { signature_check: string };
    expect(t.signature_check).toBe("invalid");
    const manifest = JSON.parse(FIXTURE_MANIFEST) as Record<string, unknown>;
    delete manifest.signature;
    const u = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ manifest_json: JSON.stringify(manifest), claimed_sha256: "b".repeat(64) })) }, env as never)).json()) as { signature_check: string };
    expect(u.signature_check).toBe("unsigned");
    const cborManifest = JSON.parse(FIXTURE_MANIFEST) as Record<string, unknown>;
    cborManifest.spec_version = "1.0";
    const cbor = await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ manifest_json: JSON.stringify(cborManifest), claimed_sha256: "c".repeat(64) })) }, env as never);
    expect(cbor.status).toBe(400);
  });

  it("reports different_version and not_in_witness", async () => {
    const { env, key } = await setup({ withWitness: true });
    const d = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody()) }, env as never)).json()) as { witness_status: string };
    expect(d.witness_status).toBe("not_in_witness");
    const stub = (env.WITNESS as unknown as FakeInboxNS).get((env.WITNESS as unknown as FakeInboxNS).idFromName("inb_1"));
    const manifest = JSON.parse(FIXTURE_MANIFEST) as { workflow_id: string };
    await stub.fetch("https://inbox/append", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload_raw: JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: manifest.workflow_id, file_sha256: "OTHER" }) }),
    });
    const d2 = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ claimed_sha256: "d".repeat(64) })) }, env as never)).json()) as { witness_status: string };
    expect(d2.witness_status).toBe("different_version");
  });

  it("dedupe re-push fills the tag when the stored run has none, never moves a tagged run", async () => {
    const { db, env, key } = await setup();
    db.agents.set("g2", { id: "g2", org_id: "o1", name: "other", status: "active", created_at: "t" });
    const first = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ agent: null })) }, env as never)).json()) as { id: string; agent: string | null };
    expect(first.agent).toBeNull();
    // Same bytes re-pushed from a computer logged in for "loans": tag fills in.
    const second = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody()) }, env as never)).json()) as { id: string; deduped: boolean; agent: string | null };
    expect(second).toMatchObject({ id: first.id, deduped: true, agent: "loans" });
    expect([...db.artifacts.values()].find((a) => a.id === first.id)!.agent_id).toBe("g1");
    expect(db.audit.map((a) => a.action)).toContain("artifact.assign");
    // Same bytes re-pushed from a computer logged in for "other": the run
    // stays with "loans" — it must never appear on another customer's link.
    const third = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ agent: "other" })) }, env as never)).json()) as { id: string; deduped: boolean; agent: string | null };
    expect(third).toMatchObject({ id: first.id, deduped: true, agent: "loans" });
    expect([...db.artifacts.values()].find((a) => a.id === first.id)!.agent_id).toBe("g1");
  });

  it("dedupe re-push refreshes a stale witness status", async () => {
    const { db, env, key } = await setup();
    const first = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody()) }, env as never)).json()) as { id: string; witness_status: string };
    expect(first.witness_status).toBe("not_in_witness");
    // The witness report arrives after the first push.
    const stub = (env.WITNESS as unknown as FakeInboxNS).get((env.WITNESS as unknown as FakeInboxNS).idFromName("inb_1"));
    const manifest = JSON.parse(FIXTURE_MANIFEST) as { workflow_id: string };
    await stub.fetch("https://inbox/append", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload_raw: JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: manifest.workflow_id, file_sha256: FILE_SHA }) }),
    });
    const second = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody()) }, env as never)).json()) as { id: string; deduped: boolean; witness_status: string };
    expect(second).toMatchObject({ id: first.id, deduped: true, witness_status: "witnessed" });
    expect(db.audit.map((a) => a.action)).toContain("artifact.refresh");
  });

  it("dedupes, rejects double-store and length lies", async () => {
    const { env, key } = await setup();
    const first = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody()) }, env as never)).json()) as { id: string; put_url: string };
    const second = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody()) }, env as never)).json()) as { id: string; deduped: boolean; put_url: string };
    expect(second).toMatchObject({ id: first.id, deduped: true });
    expect(second.put_url).toContain(first.id);
    const lie = await app.request(`/v1/orgs/o1/artifacts/${first.id}/content`, {
      method: "PUT", headers: { ...key, "Content-Length": "999" }, body: FILE_BYTES,
    }, env as never);
    expect(lie.status).toBe(400);
    const put = await app.request(`/v1/orgs/o1/artifacts/${first.id}/content`, {
      method: "PUT", headers: { ...key, "Content-Length": String(FILE_BYTES.length) }, body: FILE_BYTES,
    }, env as never);
    expect(put.status).toBe(200);
    const again = await app.request(`/v1/orgs/o1/artifacts/${first.id}/content`, {
      method: "PUT", headers: { ...key, "Content-Length": String(FILE_BYTES.length) }, body: FILE_BYTES,
    }, env as never);
    expect(again.status).toBe(409);
    const big = await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ size_bytes: 26 * 1024 * 1024 })) }, env as never);
    expect(big.status).toBe(400);
    const unknownAgent = await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ agent: "nope", claimed_sha256: "e".repeat(64) })) }, env as never);
    expect(unknownAgent.status).toBe(400);
  });

  it("isolates tenants and roles", async () => {
    const { env, key, ck } = await setup();
    expect((await app.request("/v1/orgs/o2/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody()) }, env as never)).status).toBe(403);
    expect((await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: ck("sess-viewer"), body: JSON.stringify(initBody()) }, env as never)).status).toBe(403);
    expect((await app.request("/v1/orgs/o1/artifacts", { headers: ck("sess-viewer") }, env as never)).status).toBe(200);
    expect((await app.request("/v1/orgs/o1/artifacts", {}, env as never)).status).toBe(403);
  });
});

describe("assign agent", () => {
  it("re-tags an Unassigned run to a customer; unknown agent 400; viewer 403", async () => {
    const { db, env, key, ck } = await setup();
    const init = await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: key, body: JSON.stringify(initBody({ agent: null })) }, env as never);
    expect(init.status).toBe(201);
    const created = (await init.json()) as { id: string; witness_status: string };
    const row = [...db.artifacts.values()].find((a) => a.id === created.id)!;
    expect(row.agent_id).toBeNull();
    const assign = await app.request(`/v1/orgs/o1/artifacts/${created.id}/agent`, { method: "PATCH", headers: key, body: JSON.stringify({ agent: "loans" }) }, env as never);
    expect(assign.status).toBe(200);
    expect(await assign.json()).toMatchObject({ id: created.id, agent_id: "g1" });
    expect([...db.artifacts.values()].find((a) => a.id === created.id)!.agent_id).toBe("g1");
    expect(db.audit.map((a) => a.action)).toContain("artifact.assign");
    // Unknown customer recorder name is rejected like init does.
    const bad = await app.request(`/v1/orgs/o1/artifacts/${created.id}/agent`, { method: "PATCH", headers: key, body: JSON.stringify({ agent: "nope" }) }, env as never);
    expect(bad.status).toBe(400);
    // Viewers cannot re-tag.
    const viewer = await app.request(`/v1/orgs/o1/artifacts/${created.id}/agent`, { method: "PATCH", headers: ck("sess-viewer"), body: JSON.stringify({ agent: "loans" }) }, env as never);
    expect(viewer.status).toBe(403);
    // Missing run 404s.
    const missing = await app.request("/v1/orgs/o1/artifacts/art_nope/agent", { method: "PATCH", headers: key, body: JSON.stringify({ agent: "loans" }) }, env as never);
    expect(missing.status).toBe(404);
  });
});

describe("by-customer resolve (onboarding without copied secrets)", () => {
  it("owner creates agent+inbox on demand; second call selects without recreating", async () => {
    const { db, env, ck } = await setup();
    const first = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "New Bank" }) }, env as never);
    expect(first.status).toBe(201);
    const created = (await first.json()) as { id: string; agent_id: string; url: string; secret: string; created: boolean };
    expect(created.created).toBe(true);
    expect(created.url).toBe(`https://cloud.epilabs.org/w/${created.id}`);
    expect(created.secret).toMatch(/^[0-9a-f]{64}$/);
    expect(created.agent_id).toBeTruthy();
    expect(db.audit.map((a) => a.action)).toContain("inbox.resolve");
    const second = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "New Bank" }) }, env as never);
    expect(second.status).toBe(200);
    const again = (await second.json()) as { id: string; secret: string; created: boolean };
    expect(again.id).toBe(created.id);
    expect(again.secret).toBe(created.secret);
    expect(again.created).toBe(false);
    expect(db.inboxes.get(created.id)!.customer_label).toBe("New Bank");
  });

  it("plan limits apply on creation; blank name 400s", async () => {
    const { env, ck } = await setup();
    const blank = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "  " }) }, env as never);
    expect(blank.status).toBe(400);
    // Free plan allows 1 inbox: create one, then the second new name 402s.
    const org = (await (await app.request("/v1/orgs", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ name: "Small", slug: "small-free" }) }, env as never)).json()) as { id: string };
    const one = await app.request(`/v1/orgs/${org.id}/inboxes/by-customer`, { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "Only Bank" }) }, env as never);
    expect(one.status).toBe(201);
    const two = await app.request(`/v1/orgs/${org.id}/inboxes/by-customer`, { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "Second Bank" }) }, env as never);
    expect(two.status).toBe(402);
  });

  it("least privilege: push keys never get secrets; members resolve without secrets", async () => {
    const { env, ck, key, db } = await setup();
    // Owner seeds one customer first (inb_1 Acme Bank already exists; owner gets secret).
    const seed = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "Acme Bank" }) }, env as never);
    expect(seed.status).toBe(200);
    expect(((await seed.json()) as { secret: string }).secret).toMatch(/^[0-9a-f]{64}$|^s3cr3t$/);
    // Push-only key gets 403 for existing AND new customers (never a secret).
    const sel = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: key, body: JSON.stringify({ customer_label: "Acme Bank" }) }, env as never);
    expect(sel.status).toBe(403);
    const nope = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: key, body: JSON.stringify({ customer_label: "Nope Bank" }) }, env as never);
    expect(nope.status).toBe(403);
    // Repeat push call still 403 (no re-reveal).
    const again = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: key, body: JSON.stringify({ customer_label: "Acme Bank" }) }, env as never);
    expect(again.status).toBe(403);
    // Viewer has no access at all.
    const denied = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: ck("sess-viewer"), body: JSON.stringify({ customer_label: "Acme Bank" }) }, env as never);
    expect(denied.status).toBe(403);
  });

  it("push key for Bank A cannot get Bank B secret; member resolves URL without secret", async () => {
    const { env, ck, key, db } = await setup();
    // Owner creates Bank B.
    const b = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "Bank B" }) }, env as never);
    expect(b.status).toBe(201);
    const bBody = (await b.json()) as { secret: string };
    expect(bBody.secret).toMatch(/^[0-9a-f]{64}$/);
    // Push key (bound to nothing here) cannot fetch Bank B.
    const pb = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: key, body: JSON.stringify({ customer_label: "Bank B" }) }, env as never);
    expect(pb.status).toBe(403);
    // Member resolves Bank B URL but gets no secret.
    const { sha256Hex: _h } = await import("../src/lib/crypto.ts");
    db.users.set("u_member", { id: "u_member", email: "m@x.test" });
    db.memberships.set("o1|u_member", { org_id: "o1", user_id: "u_member", role: "member" });
    const mh = await _h("sess-member");
    db.sessions.set(mh, { id_hash: mh, user_id: "u_member", expires_at: "2999-01-01T00:00:00.000Z" });
    const mres = await app.request("/v1/orgs/o1/inboxes/by-customer", { method: "POST", headers: ck("sess-member"), body: JSON.stringify({ customer_label: "Bank B" }) }, env as never);
    expect(mres.status).toBe(200);
    const mBody = (await mres.json()) as { secret: string | null; url: string };
    expect(mBody.secret).toBeNull();
    expect(mBody.url).toMatch(/\/w\//);
  });
});

describe("holds, deletes, retention, export", () => {
  async function stored() {
    const s = await setup();
    const init = (await (await app.request("/v1/orgs/o1/artifacts/init", { method: "POST", headers: s.key, body: JSON.stringify(initBody()) }, s.env as never)).json()) as { id: string };
    await app.request(`/v1/orgs/o1/artifacts/${init.id}/content`, {
      method: "PUT", headers: { ...s.key, "Content-Length": String(FILE_BYTES.length) }, body: FILE_BYTES,
    }, s.env as never);
    return { ...s, id: init.id };
  }

  it("legal hold blocks delete; release allows it", async () => {
    const { db, r2, env, ck, id } = await stored();
    expect((await app.request(`/v1/orgs/o1/artifacts/${id}/legal-hold`, { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ hold: true }) }, env as never)).status).toBe(200);
    expect((await app.request(`/v1/orgs/o1/artifacts/${id}`, { method: "DELETE", headers: ck("sess-owner") }, env as never)).status).toBe(409);
    expect((await app.request(`/v1/orgs/o1/artifacts/${id}/legal-hold`, { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ hold: false }) }, env as never)).status).toBe(200);
    expect((await app.request(`/v1/orgs/o1/artifacts/${id}`, { method: "DELETE", headers: ck("sess-owner") }, env as never)).status).toBe(200);
    expect(r2.store.has(`o1/${id}.epi`)).toBe(false);
    expect(db.artifacts.get(id)!.deleted_at).toBeTruthy();
    expect(db.audit.map((a) => a.action)).toContain("artifact.delete");
  });

  it("retention purge deletes expired, keeps held and fresh", async () => {
    const { db, r2, env } = await setup();
    db.artifacts.set("old", { id: "old", org_id: "o1", object_key: "o1/old.epi", retention_until: "2000-01-01T00:00:00.000Z", legal_hold: 0, deleted_at: null });
    db.artifacts.set("held", { id: "held", org_id: "o1", object_key: "o1/held.epi", retention_until: "2000-01-01T00:00:00.000Z", legal_hold: 1, deleted_at: null });
    db.artifacts.set("fresh", { id: "fresh", org_id: "o1", object_key: "o1/fresh.epi", retention_until: "2999-01-01T00:00:00.000Z", legal_hold: 0, deleted_at: null });
    r2.store.set("o1/old.epi", new Uint8Array([9]));
    r2.store.set("o1/held.epi", new Uint8Array([9]));
    const s = await purgeExpiredArtifacts(env as never, "2026-10-15T00:00:00.000Z");
    expect(s).toEqual({ examined: 1, deleted: 1 });
    expect(r2.store.has("o1/old.epi")).toBe(false);
    expect(r2.store.has("o1/held.epi")).toBe(true);
    expect(db.audit.map((a) => a.action)).toEqual(["artifact.retention_delete"]);
  });

  it("export mints a scoped link reviewers can download through", async () => {
    const { env, key } = await stored();
    const exp = (await (await app.request("/v1/orgs/o1/export", { method: "POST", headers: key }, env as never)).json()) as {
      share_url: string; files: { content_url: string }[]; witness_exports: { export_url: string }[];
    };
    expect(exp.share_url).toMatch(/^\/t\/sh_[0-9a-f]+#k=[0-9a-f]{64}$/);
    expect(exp.files).toHaveLength(1);
    expect(exp.witness_exports[0]).toMatchObject({ export_url: "/w/inb_1/export.jsonl" });
    const token = exp.share_url.split("#k=")[1]!;
    const h = { "X-EPI-Share-Token": token };
    const list = (await (await app.request("/v1/orgs/o1/artifacts", { headers: h }, env as never)).json()) as { artifacts: unknown[] };
    expect(list.artifacts).toHaveLength(1);
    const bytes = await app.request(exp.files[0]!.content_url, { headers: h }, env as never);
    expect(bytes.status).toBe(200);
    expect(new Uint8Array(await bytes.arrayBuffer())).toEqual(FILE_BYTES);
  });
});
