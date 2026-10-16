// Daily checkpoint cron (00:05 UTC): per inbox with new entries, sign
// {"inbox","day","count","head_hash"} with the witness Ed25519 key, anchor
// in Rekor + FreeTSA (best-effort, retried next run), store in D1.
// Honest claim: rewriting the log means rewriting a public transparency log,
// a public timestamp, and public git history — all three checkable.

import type { Env } from "./env.ts";
import { nowIso, sha256Hex } from "./lib/crypto.ts";
import { planCheckpoints, signCheckpoint } from "./lib/checkpoint.ts";
import { anchorCheckpoint } from "./lib/anchor.ts";
import { p256PubOfSecret } from "./lib/signing.ts";
import { checkpointSha256, receiptArtifactSha, signReceipt, type Envelope } from "./lib/witnessChain.ts";

export interface CronSummary {
  inboxes: number;
  checkpoints: number;
  anchored: number;
  receipts: number;
  skipped: string[];
}

export async function runCheckpointCron(env: Env, fetchFn: typeof fetch = fetch): Promise<CronSummary> {
  const summary: CronSummary = { inboxes: 0, checkpoints: 0, anchored: 0, receipts: 0, skipped: [] };
  if (!env.WITNESS_SIGNING_KEY) {
    return { ...summary, skipped: ["WITNESS_SIGNING_KEY not configured (docs/CLOUD.md §4)"] };
  }
  const inboxes = await env.DB.prepare("SELECT id FROM inboxes WHERE closed_at IS NULL").all<{ id: string }>();
  for (const { id } of inboxes.results ?? []) {
    summary.inboxes++;
    try {
      await checkpointInbox(env, fetchFn, id, summary);
    } catch (err) {
      console.error(`checkpoint ${id} failed:`, err);
      summary.skipped.push(`${id}: ${err instanceof Error ? err.message : "error"}`);
    }
  }
  return summary;
}

async function checkpointInbox(env: Env, fetchFn: typeof fetch, inboxId: string, summary: CronSummary): Promise<void> {
  const stub = env.WITNESS.get(env.WITNESS.idFromName(inboxId));
  await backfillReceipts(env, stub, inboxId, summary);
  const pendingRes = await stub.fetch("https://inbox/pending");
  if (!pendingRes.ok) throw new Error("inbox pending failed");
  const { envelopes } = (await pendingRes.json()) as { envelopes: Envelope[] };
  if (!envelopes.length) return;
  const days = planCheckpoints(inboxId, envelopes);
  const signedAt = nowIso();
  for (const d of days) {
    const { signature } = signCheckpoint(env.WITNESS_SIGNING_KEY!, inboxId, d.day, d.count, d.headHash);
    const hashHex = await checkpointSha256(d.canonical);
    const digestBytes = Uint8Array.from(hashHex.match(/.{2}/g)!.map((h) => parseInt(h, 16)));
    let rekorUuid: string | null = null;
    let rekorIndex: number | null = null;
    let tsaB64: string | null = null;
    if (env.ANCHOR_SIGNING_KEY) {
      try {
        const anchored = await anchorCheckpoint(fetchFn, {
          checkpointBytes: new TextEncoder().encode(d.canonical),
          checkpointHashHex: hashHex,
          digestBytes,
          anchorSecretHex: env.ANCHOR_SIGNING_KEY,
          anchorPubHex: p256PubOfSecret(env.ANCHOR_SIGNING_KEY),
          tsaNonce: Math.floor(Math.random() * Number.MAX_SAFE_INTEGER) + 1,
        });
        rekorUuid = anchored.rekor.uuid;
        rekorIndex = anchored.rekor.logIndex;
        tsaB64 = anchored.tsa.tokenB64;
        summary.anchored++;
      } catch (err) {
        console.error(`anchor ${inboxId} ${d.day} failed, will retry:`, err);
      }
    }
    await env.DB.prepare(
      "INSERT INTO checkpoints (inbox_id, day, count, head_hash, signature, signed_at, rekor_uuid, rekor_log_index, tsa_token_b64) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) " +
        "ON CONFLICT(inbox_id, day) DO UPDATE SET count = excluded.count, head_hash = excluded.head_hash, signature = excluded.signature, signed_at = excluded.signed_at, rekor_uuid = COALESCE(excluded.rekor_uuid, checkpoints.rekor_uuid), rekor_log_index = COALESCE(excluded.rekor_log_index, checkpoints.rekor_log_index), tsa_token_b64 = COALESCE(excluded.tsa_token_b64, checkpoints.tsa_token_b64)",
    )
      .bind(inboxId, d.day, d.count, d.headHash, signature, signedAt, rekorUuid, rekorIndex, tsaB64)
      .run();
    summary.checkpoints++;
  }
  const maxSeq = Math.max(...envelopes.map((e) => e.seq));
  await stub.fetch("https://inbox/mark", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seq: maxSeq }),
  });
}

// M6 receipt backfill: lines appended before receipts existed (or whose
// attach missed) get signed here. Honest because the statement only says
// "this line is in my log at position N" — the chain itself is unchanged
// and still covered by the daily checkpoint. Runs before checkpointing so
// a fresh line is receipted at most ~1 day late (usually at append time).
// Capped per inbox per run; the cursor advances oldest-first.
async function backfillReceipts(
  env: Env,
  stub: { fetch: typeof fetch },
  inboxId: string,
  summary: CronSummary,
): Promise<void> {
  if (!env.WITNESS_SIGNING_KEY) return;
  for (let round = 0; round < 3; round++) {
    const res = await stub.fetch("https://inbox/unreceipted");
    if (!res.ok) return;
    const { entries } = (await res.json()) as {
      entries: { seq: number; received_at: string; payload_raw: string }[];
    };
    if (!entries.length) return;
    const receipts = [];
    for (const e of entries) {
      let payload: unknown = null;
      try {
        payload = JSON.parse(e.payload_raw);
      } catch {
        payload = null;
      }
      receipts.push({
        seq: e.seq,
        receipt_sig: signReceipt(env.WITNESS_SIGNING_KEY, {
          inbox_id: inboxId,
          seq: e.seq,
          line_sha256: await sha256Hex(e.payload_raw),
          artifact_sha256: receiptArtifactSha(payload),
          received_at: e.received_at,
        }).signature,
      });
    }
    const put = await stub.fetch("https://inbox/receipts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ receipts }),
    });
    if (!put.ok) return;
    const { attached } = (await put.json()) as { attached: number };
    summary.receipts += attached;
    if (attached < entries.length) return;
  }
}
