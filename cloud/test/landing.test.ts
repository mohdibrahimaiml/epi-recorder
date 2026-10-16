import { describe, expect, it } from "vitest";
import { app } from "../src/index.ts";
import { sha256Hex } from "../src/lib/crypto.ts";

type Row = Record<string, unknown>;

// Minimal D1 double: only what the landing page reads (session -> user).
class FakeD1 {
  users = new Map<string, Row>();
  sessions = new Map<string, Row>();

  prepare(sql: string) {
    const q = sql.replace(/\s+/g, " ").trim();
    const self = this;
    const bound = (args: unknown[]) => ({
      first: async (): Promise<Row | null> => self.one(q, args),
      all: async (): Promise<{ results: Row[] }> => ({ results: [] }),
      run: async (): Promise<{ meta: { changes: number } }> => ({ meta: { changes: 0 } }),
    });
    return { bind: (...a: unknown[]) => bound(a), first: () => bound([]).first(), all: () => bound([]).all(), run: () => bound([]).run() };
  }

  private one(q: string, a: unknown[]): Row | null {
    if (q.startsWith("SELECT s.user_id")) {
      const s = this.sessions.get(a[0] as string);
      if (!s) return null;
      return { user_id: s.user_id, expires_at: s.expires_at, email: this.users.get(s.user_id as string)?.email ?? null };
    }
    throw new Error(`FakeD1 unhandled one: ${q}`);
  }
}

async function setup() {
  const db = new FakeD1();
  const env = {
    DB: db as unknown as D1Database,
    ROOM: {} as R2Bucket,
    WITNESS: { get: () => { throw new Error("no DO in landing test"); } } as unknown as DurableObjectNamespace,
    APP_ORIGIN: "https://cloud.epilabs.org",
    PUBLIC_WITNESS_URL: "https://cloud.epilabs.org",
  };
  db.users.set("u1", { id: "u1", email: "boss@acme.test" });
  db.users.set("u_evil", { id: "u_evil", email: "<script>alert(1)</script>@x.test" });
  for (const [raw, uid] of [["sess-ok", "u1"], ["sess-evil", "u_evil"]] as const) {
    const h = await sha256Hex(raw);
    db.sessions.set(h, { id_hash: h, user_id: uid, expires_at: "2999-01-01T00:00:00.000Z" });
  }
  return { db, env };
}

describe("cloud front door", () => {
  it("anonymous visitors get a sign-in page, never JSON", async () => {
    const { env } = await setup();
    const res = await app.request("/", {}, env as never);
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/html");
    const html = await res.text();
    expect(html).toContain("/auth/github");
    expect(html).toContain("Sign in with GitHub");
    expect(html).not.toContain("boss@acme.test");
  });

  it("signed-in users see their account, email escaped", async () => {
    const { env } = await setup();
    const me = await app.request("/", { headers: { Cookie: "epi_session=sess-ok" } }, env as never);
    expect(await me.text()).toContain("boss@acme.test");
    const evil = await app.request("/", { headers: { Cookie: "epi_session=sess-evil" } }, env as never);
    const body = await evil.text();
    expect(body).not.toContain("<script>alert(1)</script>");
    expect(body).toContain("&lt;script&gt;");
  });

  it("unknown routes still answer JSON 404, and nothing is indexed", async () => {
    const { env } = await setup();
    const res = await app.request("/", {}, env as never);
    expect(res.headers.get("x-robots-tag")).toContain("noindex");
    const missing = await app.request("/nope", {}, env as never);
    expect(missing.status).toBe(404);
    expect((await missing.json()) as { error: { code: string } }).toMatchObject({ error: { code: "not_found" } });
  });
});
