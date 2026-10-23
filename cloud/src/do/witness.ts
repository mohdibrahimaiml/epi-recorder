// WitnessInbox Durable Object: one ordered, hash-chained log per customer
// relationship. Single-threaded per inbox, so concurrent vendor reports stay
// strictly ordered. Entries live here (SQLite), checkpoints in D1 (M1 cron).

import { entryHash, GENESIS, type Envelope } from "../lib/witnessChain.ts";
import { nowIso } from "../lib/crypto.ts";

interface Sql {
  exec(sql: string, ...params: unknown[]): { toArray(): Record<string, unknown>[] };
}

// NOTE: workerd cursors expose only toArray — the single-row helpers throw
// on zero rows. Every read here goes through toArray()[0], which is
// empty-safe everywhere. The first append to an empty inbox must never 500.

export class WitnessInbox {
  private sql: Sql;

  constructor(state: DurableObjectState) {
    const storage = state.storage as unknown as { sql: Sql };
    this.sql = storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS entries(
      seq INTEGER PRIMARY KEY AUTOINCREMENT, received_at TEXT NOT NULL,
      payload_raw TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL,
      receipt_sig TEXT, artifact_sha256 TEXT, workflow_id TEXT)`);
    // Pre-receipt databases (M1–M5): add the column in place. IF NOT EXISTS
    // does not alter existing tables, so migrate explicitly. Duplicate-column
    // on re-boot is expected and ignored.
    try {
      this.sql.exec(`ALTER TABLE entries ADD COLUMN receipt_sig TEXT`);
    } catch {
      // Column already exists.
    }
    // Exact-match lookup columns (M6 fix): Cloudflare SQLite rejects LIKE
    // patterns longer than ~50 bytes ("LIKE or GLOB pattern too complex"),
    // and a file sha256 alone is 64 hex chars — so every /find-receipts
    // query crashed and evidence packs shipped with empty witness.json.
    // Lookups below use `=` on these columns; payload_raw LIKE is gone.
    for (const ddl of [
      `ALTER TABLE entries ADD COLUMN artifact_sha256 TEXT`,
      `ALTER TABLE entries ADD COLUMN workflow_id TEXT`,
    ]) {
      try {
        this.sql.exec(ddl);
      } catch {
        // Column already exists.
      }
    }
    this.sql.exec(`CREATE INDEX IF NOT EXISTS idx_entries_sha ON entries(artifact_sha256)`);
    this.sql.exec(`CREATE INDEX IF NOT EXISTS idx_entries_workflow ON entries(workflow_id)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)`);
  }

  /** Fill exact-match columns for pre-migration rows (bounded per call). */
  private backfillColumns(): void {
    let rows;
    try {
      rows = this.sql.exec(
        "SELECT seq, payload_raw FROM entries WHERE artifact_sha256 IS NULL OR workflow_id IS NULL ORDER BY seq ASC LIMIT 200",
      ).toArray() as Array<{ seq: number; payload_raw: string }>;
    } catch {
      return; // Schema too old for the new columns; the exact-match
      // lookup below will 500 rather than return wrong data.
    }
    for (const r of rows) {
      let sha = "";
      let wf = "";
      try {
        const p = JSON.parse(r.payload_raw) as Record<string, unknown>;
        if (typeof p.file_sha256 === "string") sha = p.file_sha256;
        if (typeof p.workflow_id === "string") wf = p.workflow_id;
      } catch {
        // Unparseable payload: leave searchable-by-nothing, never fail.
      }
      try {
        this.sql.exec("UPDATE entries SET artifact_sha256 = ?, workflow_id = ? WHERE seq = ?", sha, wf, r.seq);
      } catch {
        // Best-effort only.
      }
    }
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    try {
      if (request.method === "POST" && url.pathname === "/append") {
        const body = (await request.json()) as { payload_raw?: unknown };
        if (typeof body.payload_raw !== "string" || body.payload_raw.length === 0) {
          return Response.json({ error: { code: "bad_request", message: "payload_raw required." } }, { status: 400 });
        }
        const receivedAt = nowIso();
        const prev = (this.sql.exec("SELECT entry_hash FROM entries ORDER BY seq DESC LIMIT 1").toArray()[0]?.entry_hash as string | undefined) ?? GENESIS;
        const hash = await entryHash(prev, body.payload_raw, receivedAt);
        let sha = "";
        let wf = "";
        try {
          const p = JSON.parse(body.payload_raw) as Record<string, unknown>;
          if (typeof p.file_sha256 === "string") sha = p.file_sha256;
          if (typeof p.workflow_id === "string") wf = p.workflow_id;
        } catch {
          // Index columns stay empty; the line still chains fine.
        }
        const cursor = this.sql.exec(
          "INSERT INTO entries (received_at, payload_raw, prev_hash, entry_hash, artifact_sha256, workflow_id) VALUES (?, ?, ?, ?, ?, ?) RETURNING seq",
          receivedAt, body.payload_raw, prev, hash, sha, wf,
        );
        const seq = (cursor.toArray()[0] as unknown as { seq: number }).seq;
        return Response.json({ seq, entry_hash: hash, received_at: receivedAt }, { status: 200 });
      }
      if (request.method === "POST" && url.pathname === "/receipt") {
        // Worker-signed per-line receipt (M6): the DO never sees the key.
        const body = (await request.json()) as { seq?: unknown; receipt_sig?: unknown };
        if (typeof body.seq !== "number" || typeof body.receipt_sig !== "string" || !body.receipt_sig) {
          return Response.json({ error: { code: "bad_request", message: "seq + receipt_sig required." } }, { status: 400 });
        }
        const rows = this.sql.exec(
          "UPDATE entries SET receipt_sig = ? WHERE seq = ? AND receipt_sig IS NULL RETURNING seq",
          body.receipt_sig, body.seq,
        ).toArray();
        if (!rows.length) return Response.json({ error: { code: "not_found", message: "No unreceipted entry at seq." } }, { status: 404 });
        return Response.json({ ok: true }, { status: 200 });
      }
      if (request.method === "POST" && url.pathname === "/receipts") {
        // Backfill batch (cron): attach up to N signatures at once.
        const body = (await request.json()) as { receipts?: unknown };
        if (!Array.isArray(body.receipts) || body.receipts.length > 500) {
          return Response.json({ error: { code: "bad_request", message: "receipts[≤500] required." } }, { status: 400 });
        }
        let attached = 0;
        for (const r of body.receipts) {
          const rec = r as { seq?: unknown; receipt_sig?: unknown };
          if (typeof rec.seq !== "number" || typeof rec.receipt_sig !== "string" || !rec.receipt_sig) continue;
          const rows = this.sql.exec(
            "UPDATE entries SET receipt_sig = ? WHERE seq = ? AND receipt_sig IS NULL RETURNING seq",
            rec.receipt_sig, rec.seq,
          ).toArray();
          attached += rows.length;
        }
        return Response.json({ attached }, { status: 200 });
      }
      if (request.method === "GET" && url.pathname === "/unreceipted") {
        // Backfill cursor (cron): oldest lines still missing a receipt.
        const rows = this.sql.exec(
          "SELECT seq, received_at, payload_raw FROM entries WHERE receipt_sig IS NULL ORDER BY seq ASC LIMIT 200",
        ).toArray();
        return Response.json({ entries: rows });
      }
      if (request.method === "GET" && url.pathname === "/find-receipts") {
        // Link-scoped lookup (M6): lines for exactly this file sha, with
        // their receipts. Exact `=` match on the indexed column — never
        // LIKE (Cloudflare SQLite rejects >~50-byte LIKE patterns, and a
        // sha256 alone is 64 hex chars). The Worker exact-matches
        // payload.file_sha256 afterwards as well (fail closed).
        const digest = url.searchParams.get("sha") ?? "";
        if (!digest || digest.length > 128) return Response.json({ error: { code: "bad_request", message: "sha required." } }, { status: 400 });
        this.backfillColumns();
        const rows = this.sql.exec(
          "SELECT seq, received_at, payload_raw, receipt_sig FROM entries WHERE artifact_sha256 = ? ORDER BY seq ASC LIMIT 20",
          digest,
        ).toArray();
        return Response.json({ entries: rows });
      }
      if (request.method === "GET" && url.pathname === "/export") {
        const rows = this.sql.exec("SELECT payload_raw FROM entries ORDER BY seq ASC").toArray();
        return new Response(rows.map((r) => r.payload_raw as string).join("\n") + (rows.length ? "\n" : ""), {
          headers: { "Content-Type": "application/x-ndjson" },
        });
      }
      if (request.method === "GET" && url.pathname === "/chain") {
        const rows = this.sql.exec("SELECT seq, received_at, payload_raw, prev_hash, entry_hash FROM entries ORDER BY seq ASC").toArray();
        return Response.json({ envelopes: rows });
      }
      if (request.method === "GET" && url.pathname === "/pending") {
        const mark = (this.sql.exec("SELECT value FROM meta WHERE key = 'checkpointed_seq'").toArray()[0]?.value as string | undefined) ?? "0";
        const rows = this.sql.exec("SELECT seq, received_at, payload_raw, prev_hash, entry_hash FROM entries WHERE seq > ? ORDER BY seq ASC", Number(mark)).toArray();
        return Response.json({ envelopes: rows as unknown as Envelope[] });
      }
      if (request.method === "POST" && url.pathname === "/mark") {
        const body = (await request.json()) as { seq?: unknown };
        if (typeof body.seq !== "number") return Response.json({ error: { code: "bad_request", message: "seq required." } }, { status: 400 });
        const cur = Number(this.sql.exec("SELECT value FROM meta WHERE key = 'checkpointed_seq'").toArray()[0]?.value ?? "0");
        const next = Math.max(cur, body.seq);
        this.sql.exec("INSERT INTO meta (key, value) VALUES ('checkpointed_seq', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", String(next));
        return Response.json({ checkpointed_seq: next });
      }
      if (request.method === "GET" && url.pathname === "/find") {
        const digest = url.searchParams.get("workflow") ?? "";
        if (!digest || digest.length > 128) return Response.json({ error: { code: "bad_request", message: "workflow required." } }, { status: 400 });
        // Selected-run lookups only: exact match on the indexed column.
        this.backfillColumns();
        const rows = this.sql.exec(
          "SELECT payload_raw FROM entries WHERE workflow_id = ? ORDER BY seq ASC LIMIT 20",
          digest,
        ).toArray();
        return Response.json({ matches: rows.map((r) => r.payload_raw as string) });
      }
      if (request.method === "GET" && url.pathname === "/info") {
        const rows = this.sql.exec("SELECT COUNT(*) AS n FROM entries").toArray();
        const head = (this.sql.exec("SELECT entry_hash FROM entries ORDER BY seq DESC LIMIT 1").toArray()[0]?.entry_hash as string | undefined) ?? GENESIS;
        return Response.json({ count: (rows[0] as { n: number }).n, head_hash: head });
      }
      return Response.json({ error: { code: "not_found", message: "Unknown inbox op." } }, { status: 404 });
    } catch (err) {
      console.error(err);
      return Response.json({ error: { code: "internal", message: "Inbox error." } }, { status: 500 });
    }
  }
}
