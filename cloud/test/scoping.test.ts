// Dashboard v2 (A1): a trust link scoped to customer A must never return
// customer B's artifacts or witness lines. Uses the real schema (sqlite)
// plus stub witness DOs so export/chain scoping is exercised end to end.
import { describe, expect, it } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { app } from "../src/index.ts";
import { sha256Hex } from "../src/lib/crypto.ts";
import { sealSecret } from "../src/lib/secretbox.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const BOX_KEY = "ab".repeat(32);

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

class FakeWitnessNS {
  constructor(private lines: Record<string, string>) {}
  idFromName(name: string) {
    return { name };
  }
  get(id: { name: string }) {
    const body = this.lines[id.name] ?? "";
    return {
      fetch: async (url: string) => {
        const path = new URL(url).pathname;
        if (path === "/export") return new Response(body);
        if (path === "/chain") return Response.json({ envelopes: [] });
        if (path === "/info") return Response.json({ count: 0, head_hash: "00" });
        return new Response("{}", { status: 200 });
      },
    };
  }
}

function envFor(db: DatabaseSync, lines: Record<string, string>) {
  return {
    DB: new SqliteD1(db) as unknown as D1Database,
    ROOM: {} as R2Bucket,
    WITNESS: new FakeWitnessNS(lines) as unknown as DurableObjectNamespace,
    APP_ORIGIN: "https://cloud.epilabs.org",
    PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
    SESSION_KEY: "test-session-key-scoping",
    GITHUB_CLIENT_ID: "x",
    GITHUB_CLIENT_SECRET: "y",
    INBOX_SECRET_KEY: BOX_KEY,
  };
}

async function setup() {
  const db = openDb();
  const lines = { inb_A: "line-a-1\n", inb_B: "line-b-1\n" };
  const env = envFor(db, lines);
  const d1 = new SqliteD1(db) as unknown as D1Database;
  const run = (sql: string, ...args: unknown[]) => db.prepare(sql).run(...(args as never[]));
  run("INSERT INTO orgs (id, slug, name, plan, created_at) VALUES ('o1','acme','Acme','growth','t')");
  run("INSERT INTO users (id, email, display_name, email_verified, created_at) VALUES ('u1','o@x.test','O',1,'t')");
  const raw = "sess-owner-scoping-0123456789abcdef0123456789abcdef";
  const h = await sha256Hex(raw);
  run("INSERT INTO sessions (id_hash, user_id, expires_at) VALUES (?,?,?)", h, "u1", "2999-01-01T00:00:00.000Z");
  run("INSERT INTO memberships (org_id, user_id, role) VALUES ('o1','u1','owner')");
  const encA = await sealSecret(BOX_KEY, "s3cr3t-a");
  const encB = await sealSecret(BOX_KEY, "s3cr3t-b");
  run("INSERT INTO inboxes (id, org_id, customer_label, hmac_secret_enc, created_at, closed_at) VALUES ('inb_A','o1','Acme Bank',?,'t',NULL)", encA);
  run("INSERT INTO inboxes (id, org_id, customer_label, hmac_secret_enc, created_at, closed_at) VALUES ('inb_B','o1','Other Bank',?,'t',NULL)", encB);
  run("INSERT INTO agents (id, org_id, name, status, created_at) VALUES ('agt_A','o1','Acme Bank','active','t')");
  run("INSERT INTO agents (id, org_id, name, status, created_at) VALUES ('agt_B','o1','Other Bank','active','t')");
  const art = (id: string, agent: string, sha: string) =>
    run(
      "INSERT INTO artifacts (id, org_id, agent_id, claimed_sha256, claimed_crc32, size_bytes, manifest_json, signature_check, witness_status, reason, object_key, upload_state, uploaded_at, retention_until) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      id, "o1", agent, sha, 1, 10, '{"spec_version":"2"}', "unsigned", "not_in_witness", "sample", `o1/${id}.epi`, "pending", "2026-10-17T00:00:00.000Z", "2026-11-17T00:00:00.000Z",
    );
  art("art_A", "agt_A", "a".repeat(64));
  art("art_B", "agt_B", "b".repeat(64));
  void d1;
  const cookie = `epi_session=${raw}`;
  const jsonHeaders = { Cookie: cookie, "Content-Type": "application/json" };
  // Customer-A link, scoped the way the dashboard scopes it.
  const scoped = (await (
    await app.request("/v1/orgs/o1/share-links", { method: "POST", headers: jsonHeaders, body: JSON.stringify({ label: "Acme review", scope: { agents: ["agt_A"], inboxes: ["inb_A"] } }) }, env as never)
  ).json()) as { id: string; token: string };
  // Legacy all/all link (explicit opt-in on the dashboard).
  const open = (await (
    await app.request("/v1/orgs/o1/share-links", { method: "POST", headers: jsonHeaders, body: JSON.stringify({ label: "all", scope: { agents: "all", inboxes: "all" } }) }, env as never)
  ).json()) as { id: string; token: string };
  return { db, env, scoped, open };
}

describe("trust-link customer scoping (Bank A never sees Bank B)", () => {
  it("trust doc, artifact list, exports, and chain honor inbox+agent scope", async () => {
    const { env, scoped, open } = await setup();
    const tokA = { "X-EPI-Share-Token": scoped.token };
    const tokAll = { "X-EPI-Share-Token": open.token };

    const doc = (await (await app.request(`/v1/trust/${scoped.id}`, { headers: tokA }, env as never)).json()) as {
      inboxes: { id: string }[]; artifacts: { id: string }[];
    };
    expect(doc.inboxes.map((i) => i.id)).toEqual(["inb_A"]);
    expect(doc.artifacts.map((a) => a.id)).toEqual(["art_A"]);

    const list = (await (await app.request("/v1/orgs/o1/artifacts", { headers: tokA }, env as never)).json()) as {
      artifacts: { id: string }[];
    };
    expect(list.artifacts.map((a) => a.id)).toEqual(["art_A"]);

    expect(await (await app.request("/w/inb_A/export.jsonl", { headers: tokA }, env as never)).text()).toContain("line-a-1");
    expect((await app.request("/w/inb_B/export.jsonl", { headers: tokA }, env as never)).status).toBe(403);
    expect((await app.request("/w/inb_B/chain.jsonl", { headers: tokA }, env as never)).status).toBe(403);
    expect((await app.request("/w/inb_A/chain.jsonl", { headers: tokA }, env as never)).status).toBe(200);

    // Explicit all/all links keep the old behavior.
    expect((await app.request("/w/inb_B/export.jsonl", { headers: tokAll }, env as never)).status).toBe(200);
    const docAll = (await (await app.request(`/v1/trust/${open.id}`, { headers: tokAll }, env as never)).json()) as {
      artifacts: { id: string }[];
    };
    expect(docAll.artifacts.map((a) => a.id).sort()).toEqual(["art_A", "art_B"]);

    // A forged/unknown token sees nothing.
    expect((await app.request("/w/inb_A/export.jsonl", { headers: { "X-EPI-Share-Token": "nope" } }, env as never)).status).toBe(403);
  });
});
