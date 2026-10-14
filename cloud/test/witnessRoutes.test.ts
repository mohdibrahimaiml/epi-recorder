// M1 route tests: real WitnessInbox DO (node:sqlite adapter) behind the real
// Hono app. Covers receive ordering, export byte-compat, chain audit,
// inbox isolation, and the checkpoint cron loop.

import { describe, expect, it } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { app } from "../src/index.ts";
import { hmacHex, sha256Hex } from "../src/lib/crypto.ts";
import { edKeygen, edVerify, p256Keygen } from "../src/lib/signing.ts";
import { openSecret } from "../src/lib/secretbox.ts";
import { verifyChain } from "../src/lib/witnessChain.ts";
import { runCheckpointCron } from "../src/cron.ts";
import { WitnessInbox } from "../src/do/witness.ts";

type Row = Record<string, unknown>;
const te = new TextEncoder();

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
    return {
      fetch: (url: string, init?: RequestInit) => box.fetch(new Request(`https://inbox${new URL(url).pathname}`, init)),
    };
  }
}

// Covers exactly the statements the M1 routes emit.
class FakeD1 {
  orgs = new Map<string, Row>();
  users = new Map<string, Row>();
  sessions = new Map<string, Row>();
  memberships = new Map<string, Row>();
  inboxes = new Map<string, Row>();
  checkpoints: Row[] = [];
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
    if (q.startsWith("SELECT s.user_id")) {
      const s = this.sessions.get(a[0] as string);
      if (!s) return null;
      return { user_id: s.user_id, expires_at: s.expires_at, email: this.users.get(s.user_id as string)?.email ?? null };
    }
    if (q.startsWith("SELECT role FROM memberships")) {
      return this.memberships.get(`${a[0]}|${a[1]}`) ?? null;
    }
    if (q === "SELECT id FROM orgs WHERE id = ?") return this.orgs.has(a[0] as string) ? { id: a[0] } : null;
    if (q.startsWith("SELECT plan FROM orgs")) {
      const o = this.orgs.get(a[0] as string);
      return o ? { plan: o.plan } : null;
    }
    if (q.startsWith("SELECT org_id, closed_at FROM inboxes")) {
      const i = this.inboxes.get(a[0] as string);
      return i ? { org_id: i.org_id, closed_at: i.closed_at } : null;
    }
    if (q.startsWith("SELECT org_id FROM inboxes")) {
      const i = this.inboxes.get(a[0] as string);
      return i ? { org_id: i.org_id } : null;
    }
    if (q.startsWith("SELECT hmac_secret_enc FROM inboxes")) {
      const i = this.inboxes.get(a[0] as string);
      return i ? { hmac_secret_enc: i.hmac_secret_enc } : null;
    }
    if (q.startsWith("SELECT COUNT(*) AS n FROM inboxes")) {
      let n = 0;
      for (const i of this.inboxes.values()) if (i.org_id === a[0] && i.closed_at == null) n++;
      return { n };
    }
    if (q.startsWith("SELECT id, org_id, scopes FROM api_keys")) return null;
    if (q.startsWith("SELECT entry_hash FROM audit_log")) {
      const rows = this.audit.filter((r) => (r.org_id ?? null) === (a[0] ?? null));
      return rows.length ? { entry_hash: rows[rows.length - 1]!.entry_hash } : null;
    }
    if (q.startsWith("SELECT count, window_expires_at FROM rate_counters")) return this.counters.get(a[0] as string) ?? null;
    if (q.startsWith("SELECT COUNT(*) AS n FROM")) return { n: 0 };
    throw new Error(`FakeD1 unhandled one: ${q}`);
  }

  private many(q: string, a: unknown[]): Row[] {
    if (q.startsWith("SELECT id, customer_label")) return [...this.inboxes.values()].filter((i) => i.org_id === a[0]);
    if (q.startsWith("SELECT inbox_id, day, count")) {
      return this.checkpoints.filter((r) => r.inbox_id === a[0]).sort((x, y) => (x.day as string) < (y.day as string) ? -1 : 1);
    }
    if (q.startsWith("SELECT id FROM inboxes WHERE closed_at IS NULL")) {
      return [...this.inboxes.values()].filter((i) => i.closed_at == null).map((i) => ({ id: i.id }));
    }
    throw new Error(`FakeD1 unhandled many: ${q}`);
  }

  private exec(q: string, a: unknown[]): number {
    if (q.startsWith("INSERT INTO inboxes")) {
      this.inboxes.set(a[0] as string, { id: a[0], org_id: a[1], customer_label: a[2], hmac_secret_enc: a[3], created_at: a[4], closed_at: a[5] });
      return 1;
    }
    if (q.startsWith("UPDATE inboxes SET closed_at")) {
      const i = this.inboxes.get(a[1] as string);
      if (!i || i.org_id !== a[2] || i.closed_at != null) return 0;
      i.closed_at = a[0];
      return 1;
    }
    if (q.startsWith("INSERT INTO checkpoints")) {
      const key = `${a[0]}|${a[1]}`;
      const ex = this.checkpoints.find((r) => `${r.inbox_id}|${r.day}` === key);
      const row = { inbox_id: a[0], day: a[1], count: a[2], head_hash: a[3], signature: a[4], signed_at: a[5], rekor_uuid: a[6], rekor_log_index: a[7], tsa_token_b64: a[8] };
      if (ex) {
        Object.assign(ex, {
          count: row.count, head_hash: row.head_hash, signature: row.signature, signed_at: row.signed_at,
          rekor_uuid: row.rekor_uuid ?? ex.rekor_uuid, rekor_log_index: row.rekor_log_index ?? ex.rekor_log_index, tsa_token_b64: row.tsa_token_b64 ?? ex.tsa_token_b64,
        });
      } else this.checkpoints.push(row);
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

const BOX_KEY = "ab".repeat(32);

async function setup() {
  const db = new FakeD1();
  const ns = new FakeInboxNS();
  const ed = edKeygen();
  const anchor = p256Keygen();
  const env = {
    DB: db as unknown as D1Database,
    ROOM: {} as R2Bucket,
    WITNESS: ns as unknown as DurableObjectNamespace,
    APP_ORIGIN: "https://cloud.epilabs.org",
    PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
    INBOX_SECRET_KEY: BOX_KEY,
    WITNESS_SIGNING_KEY: ed.secretHex,
    ANCHOR_SIGNING_KEY: anchor.secretHex,
  };
  db.orgs.set("o1", { id: "o1", slug: "acme", name: "Acme", plan: "free" });
  db.users.set("u_owner", { id: "u_owner", email: "o@x.test" });
  db.users.set("u_other", { id: "u_other", email: "x@x.test" });
  const sOwner = await sha256Hex("sess-owner");
  const sOther = await sha256Hex("sess-other");
  db.sessions.set(sOwner, { id_hash: sOwner, user_id: "u_owner", expires_at: "2999-01-01T00:00:00.000Z" });
  db.sessions.set(sOther, { id_hash: sOther, user_id: "u_other", expires_at: "2999-01-01T00:00:00.000Z" });
  db.memberships.set("o1|u_owner", { org_id: "o1", user_id: "u_owner", role: "owner" });
  const ck = (raw: string) => ({ Cookie: `epi_session=${raw}`, "Content-Type": "application/json" });
  return { db, ns, env, ed, anchor, ck };
}

const REPORT = (n: number) =>
  JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: `wf-${n}`, content_digest: `cd-${n}`, public_key: "ab", steps: n });

describe("inbox management", () => {
  it("owner creates (secret shown once), lists, closes; others blocked; free limit 1 open", async () => {
    const { db, env, ck } = await setup();
    const create = await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "Acme Bank" }) }, env as never);
    expect(create.status).toBe(201);
    const { id, url, secret } = (await create.json()) as { id: string; url: string; secret: string };
    expect(url).toBe(`https://cloud.epilabs.org/w/${id}`);
    expect(secret).toMatch(/^[0-9a-f]{64}$/);
    // Secret is stored encrypted, never plaintext.
    const stored = db.inboxes.get(id)!.hmac_secret_enc as string;
    expect(stored).not.toContain(secret);
    expect(await openSecret(BOX_KEY, stored)).toBe(secret);

    const other = await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-other"), body: JSON.stringify({ customer_label: "Evil" }) }, env as never);
    expect(other.status).toBe(403);
    const second = await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "Two" }) }, env as never);
    expect(second.status).toBe(402); // free plan: 1 inbox
    const close = await app.request(`/v1/orgs/o1/inboxes/${id}/close`, { method: "POST", headers: ck("sess-owner") }, env as never);
    expect(close.status).toBe(200);
    expect((await app.request(`/v1/orgs/o1/inboxes/${id}/close`, { method: "POST", headers: ck("sess-owner") }, env as never)).status).toBe(404);
    const list = (await (await app.request("/v1/orgs/o1/inboxes", { headers: ck("sess-owner") }, env as never)).json()) as { inboxes: { closed_at: string | null }[] };
    expect(list.inboxes).toHaveLength(1);
    expect(list.inboxes[0]!.closed_at).toBeTruthy();
  });
});

describe("witness receive + export", () => {
  it("stays strictly ordered under a 1,000-report burst (DO log)", async () => {
    const { env, ck } = await setup();
    const { id } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string };
    const stub = (env.WITNESS as unknown as FakeInboxNS).get((env.WITNESS as unknown as FakeInboxNS).idFromName(id));
    for (let i = 0; i < 1000; i++) {
      const r = await stub.fetch("https://inbox/append", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ payload_raw: REPORT(i) }),
      });
      expect(r.status).toBe(200);
      expect(((await r.json()) as { seq: number }).seq).toBe(i + 1);
    }
    const { envelopes } = (await (await setupNsFetch(env, id, "/chain")).json()) as { envelopes: Parameters<typeof verifyChain>[0] };
    expect(envelopes.map((e) => e.seq)).toEqual(Array.from({ length: 1000 }, (_, i) => i + 1));
    expect((await verifyChain(envelopes)).ok).toBe(true);
  });

  it("rate-limits witness intake at 600/min/inbox", async () => {
    const { env, ck } = await setup();
    const { id, secret } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string; secret: string };
    let limitedAt = -1;
    for (let i = 0; i < 605; i++) {
      const raw = REPORT(i);
      const r = await app.request(`/w/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(secret, raw)}` },
        body: raw,
      }, env as never);
      if (r.status === 429) {
        limitedAt = i;
        break;
      }
      expect(r.status).toBe(202);
    }
    expect(limitedAt).toBe(600);
  });

  it("accepts ordered reports (202), export is byte-identical, chain verifies", async () => {
    const { env, ck } = await setup();
    const { id, secret } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string; secret: string };
    const raws = [REPORT(1), REPORT(2), REPORT(3)];
    for (let i = 0; i < raws.length; i++) {
      const r = await app.request(`/w/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(secret, raws[i]!)}` },
        body: raws[i],
      }, env as never);
      expect(r.status).toBe(202);
      expect((await r.json()) as { seq: number }).toEqual({ accepted: true, seq: i + 1 });
    }
    const exp = await app.request(`/w/${id}/export.jsonl`, { headers: ck("sess-owner") }, env as never);
    expect(exp.status).toBe(200);
    expect(await exp.text()).toBe(raws.join("\n") + "\n");
    // Chain envelopes verify end to end:
    const { envelopes } = (await (await setupNsFetch(env, id, "/chain")).json()) as { envelopes: Parameters<typeof verifyChain>[0] };
    expect((await verifyChain(envelopes)).ok).toBe(true);
  });

  it("rejects bad HMAC (401), bad schema (400), oversize (413), unknown (404), closed (410)", async () => {
    const { env, ck } = await setup();
    const { id, secret } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string; secret: string };
    const raw = REPORT(1);
    const post = (body: string, sig: string) =>
      app.request(`/w/${id}`, { method: "POST", headers: { "Content-Type": "application/json", "X-EPI-Signature": sig }, body }, env as never);
    expect((await post(raw, "sha256=00")).status).toBe(401);
    expect((await post(raw, "")).status).toBe(401);
    expect((await post('{"schema":"nope"}', `sha256=${await hmacHex(secret, '{"schema":"nope"}')}`)).status).toBe(400);
    const big = "x".repeat(16 * 1024 + 1);
    expect((await post(big, `sha256=${await hmacHex(secret, big)}`)).status).toBe(413);
    expect((await app.request("/w/inb_missing", { method: "POST", headers: { "Content-Type": "application/json", "X-EPI-Signature": "sha256=00" }, body: raw }, env as never)).status).toBe(404);
    await app.request(`/v1/orgs/o1/inboxes/${id}/close`, { method: "POST", headers: ck("sess-owner") }, env as never);
    expect((await post(raw, `sha256=${await hmacHex(secret, raw)}`)).status).toBe(410);
  });

  it("export is forbidden cross-tenant and anonymous (403)", async () => {
    const { env, ck } = await setup();
    const { id, secret } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string; secret: string };
    const raw = REPORT(1);
    await app.request(`/w/${id}`, { method: "POST", headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(secret, raw)}` }, body: raw }, env as never);
    expect((await app.request(`/w/${id}/export.jsonl`, { headers: ck("sess-other") }, env as never)).status).toBe(403);
    expect((await app.request(`/w/${id}/export.jsonl`, {}, env as never)).status).toBe(403);
    expect((await app.request(`/w/${id}/chain.jsonl`, { headers: ck("sess-other") }, env as never)).status).toBe(403);
  });
});

async function setupNsFetch(env: { WITNESS: DurableObjectNamespace }, inboxId: string, path: string): Promise<Response> {
  const stub = (env.WITNESS as unknown as FakeInboxNS).get((env.WITNESS as unknown as FakeInboxNS).idFromName(inboxId));
  return stub.fetch(`https://inbox${path}`);
}

describe("checkpoint cron", () => {
  it("signs per-day checkpoints, anchors, stores, and advances the cursor", async () => {
    const { db, env, ed, ck } = await setup();
    const { id } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string };
    // Seed three envelopes through the DO stub (server-stamped, same day).
    const stub = (env.WITNESS as unknown as FakeInboxNS).get((env.WITNESS as unknown as FakeInboxNS).idFromName(id));
    const raws = ['{"n":1}', '{"n":2}', '{"n":3}'];
    for (let i = 0; i < raws.length; i++) {
      await stub.fetch("https://inbox/append", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload_raw: raws[i] }) });
    }
    const calls: string[] = [];
    const fetchFn = (async (url: unknown, init?: { body?: { toString(): string } }) => {
      calls.push(String(url));
      if (String(url).includes("rekor")) {
        return { ok: true, status: 201, json: async () => ({ "uuid-1": { logIndex: 5 } }) } as unknown as Response;
      }
      const token = new Uint8Array([0xa0, 0x04, 0x04, 0x02, 0xde, 0xad]);
      const der = new Uint8Array([0x30, 0x0b, 0x30, 0x03, 0x02, 0x01, 0x00, ...token]);
      return { ok: true, status: 200, arrayBuffer: async () => der.buffer as ArrayBuffer } as unknown as Response;
    }) as unknown as typeof fetch;

    const s1 = await runCheckpointCron(env as never, fetchFn);
    expect(s1.inboxes).toBe(1);
    expect(s1.checkpoints).toBeGreaterThanOrEqual(1);
    expect(s1.anchored).toBe(s1.checkpoints);
    for (const row of db.checkpoints) {
      expect(edVerify(ed.pubHex, te.encode(`{"inbox":"${id}","day":"${row.day}","count":${row.count},"head_hash":"${row.head_hash}"}`), row.signature as string)).toBe(true);
      expect(row.rekor_uuid).toBe("uuid-1");
      expect(row.tsa_token_b64).toBeTruthy();
    }
    // Second run: cursor advanced, nothing new.
    const callsBefore = calls.length;
    const s2 = await runCheckpointCron(env as never, fetchFn);
    expect(s2.checkpoints).toBe(0);
    expect(calls.length).toBe(callsBefore);
    // Public checkpoints endpoint serves the rows.
    const pub = (await (await app.request(`/w/${id}/checkpoints`, {}, env as never)).json()) as { checkpoints: unknown[] };
    expect(pub.checkpoints.length).toBe(db.checkpoints.length);
  });

  it("skips cleanly without signing keys", async () => {
    const { env } = await setup();
    const keyless = { ...env, WITNESS_SIGNING_KEY: undefined, ANCHOR_SIGNING_KEY: undefined };
    const s = await runCheckpointCron(keyless as never);
    expect(s.checkpoints).toBe(0);
    expect(s.skipped.length).toBeGreaterThan(0);
  });
});

describe("well-known witness keys", () => {
  it("publishes the Ed25519 + anchor keys; nulls when unconfigured", async () => {
    const { env, ed } = await setup();
    const body = (await (await app.request("/.well-known/epi-witness-key.json", {}, env as never)).json()) as { witness_ed25519_pub_hex: string; anchor_p256_pem: string };
    expect(body.witness_ed25519_pub_hex).toBe(ed.pubHex);
    expect(body.anchor_p256_pem).toContain("BEGIN PUBLIC KEY");
    const bare = await app.request("/.well-known/epi-witness-key.json", {}, { ...env, WITNESS_SIGNING_KEY: undefined } as never);
    expect(((await bare.json()) as { witness_ed25519_pub_hex: string | null }).witness_ed25519_pub_hex).toBeNull();
  });
});
