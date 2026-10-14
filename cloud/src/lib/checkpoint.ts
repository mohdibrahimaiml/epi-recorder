// Daily checkpoint planning + signing (pure; cron-tested without runtime).
// Canonical message: {"inbox","day","count","head_hash"} (key order signed).

import { canonicalCheckpoint, dayOf, type Envelope } from "./witnessChain.ts";
import { edSign } from "./signing.ts";

export interface DayCheckpoint {
  day: string;
  count: number;
  headHash: string;
  canonical: string;
}

/** Group pending envelopes by UTC day; head = last entry_hash of the day. */
export function planCheckpoints(inbox: string, pending: Envelope[]): DayCheckpoint[] {
  const byDay = new Map<string, Envelope[]>();
  for (const e of [...pending].sort((a, b) => a.seq - b.seq)) {
    const day = dayOf(e.received_at);
    const list = byDay.get(day) ?? [];
    list.push(e);
    byDay.set(day, list);
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([day, list]) => {
      const headHash = list[list.length - 1]!.entry_hash;
      return { day, count: list.length, headHash, canonical: canonicalCheckpoint(inbox, day, list.length, headHash) };
    });
}

export function signCheckpoint(
  witnessSecretHex: string,
  inbox: string,
  day: string,
  count: number,
  headHash: string,
): { canonical: string; signature: string } {
  const canonical = canonicalCheckpoint(inbox, day, count, headHash);
  return { canonical, signature: edSign(witnessSecretHex, new TextEncoder().encode(canonical)) };
}
