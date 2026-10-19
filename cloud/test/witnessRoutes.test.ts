// M1 route tests: real WitnessInbox DO (node:sqlite adapter) behind the real
// Hono app. Covers receive ordering, export byte-compat, chain audit,
// inbox isolation, and the checkpoint cron loop.

import { describe, expect, it } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { app } from "../src/index.ts";
import { hmacHex, sha256Hex } from "../src/lib/crypto.ts";
import { edKeygen, edVerify, p256Keygen } from "../src/lib/signing.ts";
import { openSecret } from "../src/lib/secretbox.ts";
import { verifyChain, verifyReceipt } from "../src/lib/witnessChain.ts";
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
        return { toArray: () => stmt.all(...p) as Row[] };
      }
      db.prepare(sql).run(...p);
      return { toArray: () => [] as Row[] };
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
      fetch: (url: string, init?: RequestInit) => {
        const u = new URL(url);
        return box.fetch(new Request(`https://inbox${u.pathname}${u.search}`, init));
      },
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
    if (q.includes("?") && a.length === 0) throw new Error(`FakeD1 unbound placeholders: ${q}`);
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
    if (q.includes("?") && a.length === 0) throw new Error(`FakeD1 unbound placeholders: ${q}`);
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
    if (q.startsWith("UPDATE inboxes SET hmac_secret_enc")) {
      const i = this.inboxes.get(a[1] as string);
      if (!i || i.org_id !== a[2]) return 0;
      i.hmac_secret_enc = a[0];
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

describe("witness secret rotation", () => {
  it("old secret stops working immediately; new secret delivers; old lines stay valid", async () => {
    const { db, env, ck } = await setup();
    const { id, secret: s1 } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "Acme Bank" }) }, env as never)).json()) as { id: string; secret: string };
    const raw1 = REPORT(1);
    expect((await app.request(`/w/${id}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(s1, raw1)}` }, body: raw1,
    }, env as never)).status).toBe(202);

    const rot = await app.request(`/v1/orgs/o1/inboxes/${id}/rotate`, { method: "POST", headers: ck("sess-owner") }, env as never);
    expect(rot.status).toBe(200);
    const { secret: s2, url } = (await rot.json()) as { secret: string; url: string };
    expect(url).toBe(`https://cloud.epilabs.org/w/${id}`);
    expect(s2).toMatch(/^[0-9a-f]{64}$/);
    expect(s2).not.toBe(s1);
    const stored = db.inboxes.get(id)!.hmac_secret_enc as string;
    expect(stored).not.toContain(s2);
    expect(stored).not.toContain(s1);
    expect(await openSecret(BOX_KEY, stored)).toBe(s2);

    // Old secret is rejected; new secret is accepted. The first line stays.
    const rawOld = REPORT(2);
    expect((await app.request(`/w/${id}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(s1, rawOld)}` }, body: rawOld,
    }, env as never)).status).toBe(401);
    const raw2 = REPORT(2);
    expect((await app.request(`/w/${id}`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(s2, raw2)}` }, body: raw2,
    }, env as never)).status).toBe(202);
    const exp = await app.request(`/w/${id}/export.jsonl`, { headers: ck("sess-owner") }, env as never);
    expect(await exp.text()).toBe([raw1, raw2].join("\n") + "\n");
  });

  it("non-owner cannot rotate; unknown inbox 404; closed inbox 410", async () => {
    const { env, ck } = await setup();
    const { id } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string };
    expect((await app.request(`/v1/orgs/o1/inboxes/${id}/rotate`, { method: "POST", headers: ck("sess-other") }, env as never)).status).toBe(403);
    expect((await app.request("/v1/orgs/o1/inboxes/inb_nope/rotate", { method: "POST", headers: ck("sess-owner") }, env as never)).status).toBe(404);
    await app.request(`/v1/orgs/o1/inboxes/${id}/close`, { method: "POST", headers: ck("sess-owner") }, env as never);
    expect((await app.request(`/v1/orgs/o1/inboxes/${id}/rotate`, { method: "POST", headers: ck("sess-owner") }, env as never)).status).toBe(410);
  });

  it("errors during create/rotate never log the secret", async () => {
    const { env, ck } = await setup();
    const logs: string[] = [];
    const origErr = console.error;
    console.error = (...a: unknown[]) => { logs.push(a.map(String).join(" ")); };
    try {
      // Force a 500 inside create (broken D1) with a known label; the label
      // is fine to log, but no secret/key/token may appear.
      const brokenDb = { prepare: () => { throw new Error("db down"); } } as unknown as D1Database;
      const brokenEnv = { ...env, DB: brokenDb };
      const r1 = await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "Acme Bank" }) }, brokenEnv as never);
      expect(r1.status).toBe(500);
      // Force a 500 inside rotate the same way.
      const { id } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string };
      const r2 = await app.request(`/v1/orgs/o1/inboxes/${id}/rotate`, { method: "POST", headers: ck("sess-owner") }, brokenEnv as never);
      expect(r2.status).toBe(500);
      // Also exercise the not-configured path: must not echo any secret.
      const noKeyEnv = { ...env, INBOX_SECRET_KEY: undefined };
      const r3 = await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "C" }) }, noKeyEnv as never);
      expect(r3.status).toBe(503);
      const r4 = await app.request(`/v1/orgs/o1/inboxes/${id}/rotate`, { method: "POST", headers: ck("sess-owner") }, noKeyEnv as never);
      expect(r4.status).toBe(503);
    } finally {
      console.error = origErr;
    }
    const blob = logs.join("\n");
    expect(blob).not.toMatch(/[0-9a-f]{32,}/);
    expect(blob.toLowerCase()).not.toMatch(/secret|token|epik_|sess-/);
    // The 500 path logs only the cause line, never request data.
    expect(logs.every((l) => l.startsWith("request failed:"))).toBe(true);
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
      expect((await r.json()) as { seq: number }).toEqual({ accepted: true, seq: i + 1, receipt_attached: true });
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

  it("accepts reports with null optional fields (older installed recorders send nulls)", async () => {
    const { env, ck } = await setup();
    const { id, secret } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string; secret: string };
    const raw = JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: "wf-null", content_digest: null, public_key: null, key_fingerprint: null, steps: 1 });
    const r = await app.request(`/w/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(secret, raw)}` },
      body: raw,
    }, env as never);
    expect(r.status).toBe(202);
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

  it("append signs a per-line receipt; keyless appends are backfilled by cron", async () => {
    const { env, ed, ck } = await setup();
    const { id, secret } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string; secret: string };
    const raw = JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: "wf-9", file_sha256: "ff".repeat(32) });
    const r = await app.request(`/w/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(secret, raw)}` },
      body: raw,
    }, env as never);
    expect(r.status).toBe(202);
    expect(await r.json()).toMatchObject({ accepted: true, seq: 1, receipt_attached: true });
    const found = (await (await setupNsFetch(env, id, `/find-receipts?sha=${"ff".repeat(32)}`)).json()) as {
      entries: { seq: number; received_at: string; payload_raw: string; receipt_sig: string | null }[];
    };
    expect(found.entries).toHaveLength(1);
    expect(found.entries[0]!.receipt_sig).toBeTruthy();
    expect(verifyReceipt(ed.pubHex, {
      inbox_id: id, seq: 1,
      line_sha256: await sha256Hex(raw),
      artifact_sha256: "ff".repeat(32),
      received_at: found.entries[0]!.received_at,
      signature: found.entries[0]!.receipt_sig!,
    })).toBe(true);
    // Keyless append: line chains fine, receipt pending ...
    const keyless = { ...env, WITNESS_SIGNING_KEY: undefined };
    const raw2 = JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: "wf-10", file_sha256: "ee".repeat(32) });
    const r2 = await app.request(`/w/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-EPI-Signature": `sha256=${await hmacHex(secret, raw2)}` },
      body: raw2,
    }, keyless as never);
    expect(await r2.json()).toMatchObject({ accepted: true, seq: 2, receipt_attached: false });
    // ... and the next cron backfills the signature.
    const s = await runCheckpointCron(env as never, async () => ({ ok: true }) as unknown as Response);
    expect(s.receipts).toBeGreaterThanOrEqual(1);
    const found2 = (await (await setupNsFetch(env, id, `/find-receipts?sha=${"ee".repeat(32)}`)).json()) as {
      entries: { receipt_sig: string | null }[];
    };
    expect(found2.entries[0]!.receipt_sig).toBeTruthy();
  });

  it("pre-receipt databases migrate the column in place", async () => {
    const db = new DatabaseSync(":memory:");
    db.exec("CREATE TABLE entries(seq INTEGER PRIMARY KEY AUTOINCREMENT, received_at TEXT NOT NULL, payload_raw TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL)");
    db.prepare("INSERT INTO entries(received_at, payload_raw, prev_hash, entry_hash) VALUES (?,?,?,?)").run("2026-10-15T00:00:01.000Z", '{"n":0}', "GENESIS", "h0");
    const box = new WitnessInbox({ storage: { sql: doAdapter(db) } } as unknown as DurableObjectState);
    const appended = await box.fetch(new Request("https://inbox/append", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload_raw: '{"n":1}' }),
    }));
    expect(appended.status).toBe(200);
    const un = (await (await box.fetch(new Request("https://inbox/unreceipted"))).json()) as { entries: { seq: number }[] };
    expect(un.entries.map((e) => e.seq)).toEqual([1, 2]);
    const put = await box.fetch(new Request("https://inbox/receipts", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ receipts: [{ seq: 1, receipt_sig: "sig1" }] }),
    }));
    expect(((await put.json()) as { attached: number }).attached).toBe(1);
    db.close();
  });

  it("find-receipts matches file_sha256 exactly, never by substring", async () => {
    const { env, ck } = await setup();
    const { id } = (await (await app.request("/v1/orgs/o1/inboxes", { method: "POST", headers: ck("sess-owner"), body: JSON.stringify({ customer_label: "B" }) }, env as never)).json()) as { id: string };
    const decoy = "ab".repeat(32);
    const real = "cd".repeat(32);
    // Legacy-shaped row: no file_sha256, but the decoy sha appears in
    // another field. A LIKE filter would false-match it (and on Cloudflare
    // the 66-char pattern 500s outright).
    const legacy = JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: "wf-exact", goal: `needs ${decoy} here` });
    const stub = (env.WITNESS as unknown as FakeInboxNS).get((env.WITNESS as unknown as FakeInboxNS).idFromName(id));
    await stub.fetch("https://inbox/append", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload_raw: legacy }) });
    const miss = (await (await setupNsFetch(env, id, `/find-receipts?sha=${decoy}`)).json()) as { entries: unknown[] };
    expect(miss.entries).toEqual([]);
    // Exact row is found by its own sha.
    const withSha = JSON.stringify({ schema: "epi-witness/v1", type: "epi.sealed", workflow_id: "wf-exact", file_sha256: real });
    await stub.fetch("https://inbox/append", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ payload_raw: withSha }) });
    const hit = (await (await setupNsFetch(env, id, `/find-receipts?sha=${real}`)).json()) as { entries: { payload_raw: string }[] };
    expect(hit.entries).toHaveLength(1);
    expect(JSON.parse(hit.entries[0]!.payload_raw).file_sha256).toBe(real);
    // Workflow lookup still finds the legacy row (backfill path).
    const wf = (await (await setupNsFetch(env, id, "/find?workflow=wf-exact")).json()) as { matches: string[] };
    expect(wf.matches).toHaveLength(2);
  });
});

async function setupNsFetch(env: { WITNESS: DurableObjectNamespace }, inboxId: string, path: string): Promise<Response> {
  const stub = (env.WITNESS as unknown as FakeInboxNS).get((env.WITNESS as unknown as FakeInboxNS).idFromName(inboxId));
  return stub.fetch(`https://inbox${path}`);
}

describe("workerd safety guards", () => {
  it("the DO never calls cursor .one()/.first() (workerd cursors only have toArray)", () => {
    const root = join(dirname(fileURLToPath(import.meta.url)), "..");
    const src = readFileSync(join(root, "src", "do", "witness.ts"), "utf8");
    expect(src).not.toMatch(/\.one\(\)/);
    expect(src).not.toMatch(/\.first\(\)/);
  });

  it("find routes never use LIKE (Cloudflare rejects >~50-byte patterns)", () => {
    const root = join(dirname(fileURLToPath(import.meta.url)), "..");
    const src = readFileSync(join(root, "src", "do", "witness.ts"), "utf8");
    expect(src).not.toMatch(/ LIKE \?/);
  });

  it("wrangler registers SQLite-backed classes (required, immutable after deploy)", () => {
    const root = join(dirname(fileURLToPath(import.meta.url)), "..");
    const toml = readFileSync(join(root, "wrangler.toml"), "utf8");
    expect(toml).toMatch(/new_sqlite_classes\s*=\s*\["WitnessInbox"\]/);
    expect(toml).not.toMatch(/new_classes\s*=\s*\["WitnessInbox"\]/);
  });
});

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
    // The three direct-DO appends carried no receipts; cron backfilled them.
    expect(s1.receipts).toBe(3);
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
