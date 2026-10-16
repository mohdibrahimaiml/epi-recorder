import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../env.ts";
import { nowIso, sha256Hex, verifyHmac } from "../lib/crypto.ts";
import { checkRateLimit, d1CounterStore } from "../lib/ratelimit.ts";
import { edPubOfSecret, p256PubOfSecret, p256SpkiPem } from "../lib/signing.ts";
import { receiptArtifactSha, signReceipt } from "../lib/witnessChain.ts";
import { keyFromRequest, membershipRole, userFromRequest } from "../lib/auth.ts";
import { inboxSecret } from "./inboxes.ts";

const app = new Hono<{ Bindings: Env }>();

const MAX_BODY = 16 * 1024; // plan §6.2: witness body ≤16 KB

const reportSchema = z.object({
  schema: z.literal("epi-witness/v1"),
  type: z.literal("epi.sealed"),
  workflow_id: z.string().min(1),
  manifest_hash: z.string().min(1).optional(),
  file_sha256: z.string().min(1).optional(),
  content_digest: z.string().min(1).optional(),
  public_key: z.string().min(1).optional(),
  key_fingerprint: z.string().min(1).optional(),
  steps: z.number().int().nonnegative().optional(),
  sealed_at: z.string().min(1).optional(),
}).passthrough();

function inboxStub(env: Env, inboxId: string) {
  return env.WITNESS.get(env.WITNESS.idFromName(inboxId));
}

// Vendor recorder/gateway: hash-only report. Same protocol as `epi witness serve`.
app.post("/:inboxId", async (c) => {
  const inboxId = c.req.param("inboxId");
  const inbox = await c.env.DB.prepare("SELECT org_id, closed_at FROM inboxes WHERE id = ?").bind(inboxId).first<{ org_id: string; closed_at: string | null }>();
  if (!inbox) return c.json({ error: { code: "not_found", message: "Unknown inbox." } }, 404);
  if (inbox.closed_at) return c.json({ error: { code: "inbox_closed", message: "Inbox is closed." } }, 410);
  const secret = await inboxSecret(c.env.DB, c.env, inboxId);
  if (!secret) return c.json({ error: { code: "not_configured", message: "Witness inbox is not configured yet." } }, 503);

  const raw = await c.req.text();
  if (raw.length > MAX_BODY || raw.length === 0) {
    return c.json({ error: { code: "too_large", message: "Witness body must be 1 byte–16 KB." } }, 413);
  }
  if (!(await verifyHmac(c.req.header("X-EPI-Signature"), secret, raw))) {
    return c.json({ error: { code: "bad_signature", message: "Bad or missing X-EPI-Signature HMAC." } }, 401);
  }
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    return c.json({ error: { code: "bad_request", message: "Body must be JSON." } }, 400);
  }
  if (!reportSchema.safeParse(payload).success) {
    return c.json({ error: { code: "bad_schema", message: "Body must be an epi-witness/v1 epi.sealed report." } }, 400);
  }
  const limited = await checkRateLimit(d1CounterStore(c.env.DB), `witness:${inboxId}`, 600, 60);
  if (!limited.ok) {
    return c.json({ error: { code: "rate_limited", message: "Witness rate limit hit. Retry soon." } }, 429);
  }
  const stub = inboxStub(c.env, inboxId);
  const res = await stub.fetch("https://inbox/append", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payload_raw: raw }),
  });
  if (!res.ok) return c.json({ error: { code: "internal", message: "Witness append failed." } }, 500);
  const { seq, received_at } = (await res.json()) as { seq: number; received_at: string };
  // M6 per-line receipt ("stamped ticket"): signed here in the Worker, which
  // holds WITNESS_SIGNING_KEY — the DO never sees the key. A missed attach
  // (key unconfigured, DO hiccup) is covered by cron backfill; the line is
  // already chained, so the append itself never fails for receipt reasons.
  let receiptAttached = false;
  if (c.env.WITNESS_SIGNING_KEY && typeof received_at === "string") {
    try {
      const lineSha = await sha256Hex(raw);
      const receipt = signReceipt(c.env.WITNESS_SIGNING_KEY, {
        inbox_id: inboxId,
        seq,
        line_sha256: lineSha,
        artifact_sha256: receiptArtifactSha(payload),
        received_at,
      });
      const put = await stub.fetch("https://inbox/receipt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seq, receipt_sig: receipt.signature }),
      });
      receiptAttached = put.ok;
    } catch {
      receiptAttached = false;
    }
  }
  return c.json({ accepted: true, seq, receipt_attached: receiptAttached }, 202);
});

async function orgOfInbox(db: D1Database, inboxId: string): Promise<string | null> {
  const row = await db.prepare("SELECT org_id FROM inboxes WHERE id = ?").bind(inboxId).first<{ org_id: string }>();
  return row?.org_id ?? null;
}

// Member of the owning org (API key auth arrives in M3 push; share-token in M2).
async function canReadExport(db: D1Database, req: Request, orgId: string): Promise<boolean> {
  const user = await userFromRequest(db, req);
  if (user && (await membershipRole(db, orgId, user.id))) return true;
  const key = await keyFromRequest(db, req);
  return !!key && key.orgId === orgId && key.scopes.includes("read");
}

// Byte-compatible with received.jsonl from `epi witness serve`.
app.get("/:inboxId/export.jsonl", async (c) => {
  const inboxId = c.req.param("inboxId");
  const orgId = await orgOfInbox(c.env.DB, inboxId);
  if (!orgId) return c.json({ error: { code: "not_found", message: "Unknown inbox." } }, 404);
  if (!(await canReadExport(c.env.DB, c.req.raw, orgId))) {
    return c.json({ error: { code: "forbidden", message: "Member, read key, or share token required." } }, 403);
  }
  const res = await inboxStub(c.env, inboxId).fetch("https://inbox/export");
  return new Response(res.body, { headers: { "Content-Type": "application/x-ndjson", "Content-Disposition": `attachment; filename="${inboxId}-export.jsonl"` } });
});

// Audit envelope: seq + server stamp + chain links (for `epi witness check`).
app.get("/:inboxId/chain.jsonl", async (c) => {
  const inboxId = c.req.param("inboxId");
  const orgId = await orgOfInbox(c.env.DB, inboxId);
  if (!orgId) return c.json({ error: { code: "not_found", message: "Unknown inbox." } }, 404);
  if (!(await canReadExport(c.env.DB, c.req.raw, orgId))) {
    return c.json({ error: { code: "forbidden", message: "Member, read key, or share token required." } }, 403);
  }
  const res = await inboxStub(c.env, inboxId).fetch("https://inbox/chain");
  const { envelopes } = (await res.json()) as { envelopes: unknown[] };
  const lines = envelopes.map((e) => JSON.stringify(e)).join("\n") + (envelopes.length ? "\n" : "");
  return new Response(lines, { headers: { "Content-Type": "application/x-ndjson" } });
});

// Signed daily checkpoints (+ Rekor/TSA references). Public.
app.get("/:inboxId/checkpoints", async (c) => {
  const inboxId = c.req.param("inboxId");
  const orgId = await orgOfInbox(c.env.DB, inboxId);
  if (!orgId) return c.json({ error: { code: "not_found", message: "Unknown inbox." } }, 404);
  const rows = await c.env.DB.prepare(
    "SELECT inbox_id, day, count, head_hash, signature, signed_at, rekor_uuid, rekor_log_index, tsa_token_b64 FROM checkpoints WHERE inbox_id = ? ORDER BY day ASC",
  ).bind(inboxId).all();
  return c.json({ inbox: inboxId, checkpoints: rows.results });
});

// Witness public keys (Ed25519 checkpoint key + P-256 Rekor anchor key).
// Served at /.well-known/epi-witness-key.json (mounted in index.ts). Public.
export function witnessKeys(env: Env): {
  witness_ed25519_pub_hex: string | null;
  anchor_p256_pem: string | null;
  note: string;
} {
  if (!env.WITNESS_SIGNING_KEY) {
    return { witness_ed25519_pub_hex: null, anchor_p256_pem: null, note: "Witness keys are not configured yet (docs/CLOUD.md §4)." };
  }
  let witness: string | null = null;
  try {
    witness = edPubOfSecret(env.WITNESS_SIGNING_KEY);
  } catch {
    witness = null;
  }
  let anchor: string | null = null;
  if (env.ANCHOR_SIGNING_KEY) {
    try {
      anchor = p256SpkiPem(p256PubOfSecret(env.ANCHOR_SIGNING_KEY));
    } catch {
      anchor = null;
    }
  }
  return {
    witness_ed25519_pub_hex: witness,
    anchor_p256_pem: anchor,
    note: "Checkpoints are Ed25519-signed by the witness key; the P-256 key only submits checkpoint hashes to Rekor.",
  };
}

export default app;
