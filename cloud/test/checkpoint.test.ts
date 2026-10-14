import { describe, expect, it } from "vitest";
import { edKeygen, edVerify } from "../src/lib/signing.ts";
import { planCheckpoints, signCheckpoint } from "../src/lib/checkpoint.ts";
import type { Envelope } from "../src/lib/witnessChain.ts";
import { entryHash, GENESIS } from "../src/lib/witnessChain.ts";

const te = new TextEncoder();

async function envelopes(): Promise<Envelope[]> {
  const raws = ["r1", "r2", "r3"];
  const times = ["2026-10-15T01:00:00.000Z", "2026-10-15T02:00:00.000Z", "2026-10-16T01:00:00.000Z"];
  const out: Envelope[] = [];
  let prev = GENESIS;
  for (let i = 0; i < raws.length; i++) {
    const h = await entryHash(prev, raws[i]!, times[i]!);
    out.push({ seq: i + 1, received_at: times[i]!, payload_raw: raws[i]!, prev_hash: prev, entry_hash: h });
    prev = h;
  }
  return out;
}

describe("checkpoint planning + signing", () => {
  it("groups by UTC day with per-day count and head", async () => {
    const env = await envelopes();
    const days = planCheckpoints("inb_9", env);
    expect(days.map((d) => [d.day, d.count])).toEqual([["2026-10-15", 2], ["2026-10-16", 1]]);
    expect(days[0]!.headHash).toBe(env[1]!.entry_hash);
    expect(days[1]!.headHash).toBe(env[2]!.entry_hash);
    expect(days[0]!.canonical).toBe(`{"inbox":"inb_9","day":"2026-10-15","count":2,"head_hash":"${env[1]!.entry_hash}"}`);
  });

  it("signs canonically; verifiers recompute the same bytes", async () => {
    const k = edKeygen();
    const { canonical, signature } = signCheckpoint(k.secretHex, "inb_9", "2026-10-15", 2, "ff");
    expect(canonical).toBe('{"inbox":"inb_9","day":"2026-10-15","count":2,"head_hash":"ff"}');
    expect(edVerify(k.pubHex, te.encode(canonical), signature)).toBe(true);
  });
});
