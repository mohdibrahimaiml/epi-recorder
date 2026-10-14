// Ordered hash-chained witness log (pure logic; the Durable Object is a
// thin wrapper in do/witness.ts, unit tests run this over node:sqlite).
//
// entry_hash = sha256(prev_hash ‖ sha256(payload_raw) ‖ received_at)
// (‖ = plain concatenation, plan §6.2). Chain starts at prev_hash
// "GENESIS". payload_raw is the EXACT vendor report bytes (export.jsonl
// report bytes (export.jsonl stays byte-compatible with received.jsonl).

import { sha256Hex } from "./crypto.ts";

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

export function checkpointSha256(canonical: string): Promise<string> {
  return sha256Hex(canonical);
}

/** UTC day bucket of an ISO timestamp. */
export function dayOf(iso: string): string {
  return iso.slice(0, 10);
}
