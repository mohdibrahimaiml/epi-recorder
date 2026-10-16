// Ordered hash-chained witness log (pure logic; the Durable Object is a
// thin wrapper in do/witness.ts, unit tests run this over node:sqlite).
//
// entry_hash = sha256(prev_hash ‖ sha256(payload_raw) ‖ received_at)
// (‖ = plain concatenation, plan §6.2). Chain starts at prev_hash
// "GENESIS". payload_raw is the EXACT vendor report bytes (export.jsonl
// report bytes (export.jsonl stays byte-compatible with received.jsonl).

import { sha256Hex } from "./crypto.ts";
import { edSign, edVerify } from "./signing.ts";

export { sha256Hex };

export const GENESIS = "GENESIS";

export interface Envelope {
  seq: number;
  received_at: string;
  payload_raw: string;
  prev_hash: string;
  entry_hash: string;
}

export async function entryHash(prevHash: string, payloadRaw: string, receivedAt: string): Promise<string> {
  return sha256Hex(`${prevHash}${await sha256Hex(payloadRaw)}${receivedAt}`);
}

/** Recompute the whole chain. Returns first mismatch or null when intact. */
export async function verifyChain(
  envelopes: Envelope[],
): Promise<{ ok: true; head: string; count: number } | { ok: false; atSeq: number; reason: string }> {
  let prev = GENESIS;
  for (const e of envelopes) {
    if (e.prev_hash !== prev) return { ok: false, atSeq: e.seq, reason: `prev_hash links to ${e.prev_hash}, chain has ${prev}` };
    const recomputed = await entryHash(e.prev_hash, e.payload_raw, e.received_at);
    if (recomputed !== e.entry_hash) return { ok: false, atSeq: e.seq, reason: "entry_hash does not recompute" };
    prev = e.entry_hash;
  }
  return { ok: true, head: prev === GENESIS ? GENESIS : prev, count: envelopes.length };
}

/** Canonical checkpoint message. Key order is part of the signature. */
export function canonicalCheckpoint(inbox: string, day: string, count: number, headHash: string): string {
  return JSON.stringify({ inbox, day, count, head_hash: headHash });
}

// Per-line witness receipt (M6). The daily checkpoint only signs head_hash,
// so a single line can never be tied to it without replaying the whole chain
// (NO-STOP finding). The witness therefore also signs a "stamped ticket" per
// append: {"artifact_sha256","inbox_id","line_sha256","received_at","seq"}.
// Key order is part of the signature — the CLI must serialize identically.
// This says ONLY "this line is in my log at position N"; full-log
// consistency stays covered by the signed daily checkpoint (Merkle inclusion
// proofs are a post-raise design, not present).
export interface LineReceipt {
  inbox_id: string;
  seq: number;
  line_sha256: string;
  artifact_sha256: string;
  received_at: string;
  signature: string;
}

export function canonicalReceipt(r: {
  inbox_id: string; seq: number; line_sha256: string; artifact_sha256: string; received_at: string;
}): string {
  return JSON.stringify({
    artifact_sha256: r.artifact_sha256,
    inbox_id: r.inbox_id,
    line_sha256: r.line_sha256,
    received_at: r.received_at,
    seq: r.seq,
  });
}

export function signReceipt(
  witnessSecretHex: string,
  r: { inbox_id: string; seq: number; line_sha256: string; artifact_sha256: string; received_at: string },
): LineReceipt {
  const canonical = canonicalReceipt(r);
  return { ...r, signature: edSign(witnessSecretHex, new TextEncoder().encode(canonical)) };
}

export function verifyReceipt(witnessPubHex: string, r: LineReceipt): boolean {
  const { signature, ...unsigned } = r;
  return edVerify(witnessPubHex, new TextEncoder().encode(canonicalReceipt(unsigned)), signature);
}

/** artifact_sha256 binding: first identifying digest present in the report. */
export function receiptArtifactSha(payload: unknown): string {
  if (payload && typeof payload === "object") {
    for (const k of ["file_sha256", "manifest_hash", "content_digest"]) {
      const v = (payload as Record<string, unknown>)[k];
      if (typeof v === "string" && v.length > 0) return v;
    }
  }
  return "";
}
export function checkpointSha256(canonical: string): Promise<string> {
  return sha256Hex(canonical);
}

/** UTC day bucket of an ISO timestamp. */
export function dayOf(iso: string): string {
  return iso.slice(0, 10);
}
