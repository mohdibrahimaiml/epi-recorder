import { describe, expect, it } from "vitest";
import { DatabaseSync } from "node:sqlite";
import {
  GENESIS,
  canonicalCheckpoint,
  canonicalReceipt,
  dayOf,
  entryHash,
  receiptArtifactSha,
  sha256Hex,
  signReceipt,
  verifyChain,
  verifyReceipt,
  type Envelope,
} from "../src/lib/witnessChain.ts";
import { edKeygen } from "../src/lib/signing.ts";

async function chain3(): Promise<Envelope[]> {
  const raws = ['{"schema":"epi-witness/v1","n":1}', '{"schema":"epi-witness/v1","n":2}', '{"schema":"epi-witness/v1","n":3}'];
  const times = ["2026-10-15T00:00:01.000Z", "2026-10-15T00:00:02.000Z", "2026-10-16T00:00:01.000Z"];
  const out: Envelope[] = [];
  let prev = GENESIS;
  for (let i = 0; i < raws.length; i++) {
    const h = await entryHash(prev, raws[i]!, times[i]!);
    out.push({ seq: i + 1, received_at: times[i]!, payload_raw: raws[i]!, prev_hash: prev, entry_hash: h });
    prev = h;
  }
  return out;
}

describe("witness hash chain", () => {
  it("matches the cross-language golden vector (python computes the same)", async () => {
    // inner = sha256("{}"), entry = sha256("GENESIS" + inner + at).
    expect(await sha256Hex("{}")).toBe("44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a");
    expect(await entryHash("GENESIS", "{}", "2026-10-15T00:00:00.000Z")).toBe(
      "a377c51f2f43263e82d147a89a25b2220b440a9fba762c2d0c33775e0d1b6f33",
    );
  });

  it("builds and verifies a 3-entry chain", async () => {
    const env = await chain3();
    const r = await verifyChain(env);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.count).toBe(3);
      expect(r.head).toBe(env[2]!.entry_hash);
    }
  });

  it("catches an edited payload line", async () => {
    const env = await chain3();
    env[1]!.payload_raw += " ";
    const r = await verifyChain(env);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.atSeq).toBe(2);
  });

  it("catches deletion and reordering", async () => {
    const env = await chain3();
    const dropped = await verifyChain([env[0]!, env[2]!]);
    expect(dropped.ok).toBe(false);
    const reordered = await verifyChain([env[1]!, env[0]!, env[2]!]);
    expect(reordered.ok).toBe(false);
  });

  it("canonical checkpoint has the exact signed shape", () => {
    expect(canonicalCheckpoint("inb_x", "2026-10-15", 3, "abc")).toBe(
      '{"inbox":"inb_x","day":"2026-10-15","count":3,"head_hash":"abc"}',
    );
    expect(dayOf("2026-10-15T23:59:59.999Z")).toBe("2026-10-15");
  });

  it("runs against real SQLite semantics", async () => {
    const db = new DatabaseSync(":memory:");
    db.exec("CREATE TABLE e(seq INTEGER PRIMARY KEY AUTOINCREMENT, h TEXT)");
    db.prepare("INSERT INTO e(h) VALUES (?)").run("x");
    expect((db.prepare("SELECT h FROM e").get() as { h: string }).h).toBe("x");
    db.close();
  });

  it("canonical receipt has the exact signed shape (CLI must match)", () => {
    expect(canonicalReceipt({
      inbox_id: "inb_x", seq: 7, line_sha256: "aa", artifact_sha256: "bb", received_at: "2026-10-15T00:00:01.000Z",
    })).toBe(
      '{"artifact_sha256":"bb","inbox_id":"inb_x","line_sha256":"aa","received_at":"2026-10-15T00:00:01.000Z","seq":7}',
    );
  });

  it("receipt signs and verifies; tampered line or forged key fails", async () => {
    const { secretHex, pubHex } = edKeygen();
    const r = signReceipt(secretHex, {
      inbox_id: "inb_x", seq: 7, line_sha256: await sha256Hex("raw"),
      artifact_sha256: "bb", received_at: "2026-10-15T00:00:01.000Z",
    });
    expect(verifyReceipt(pubHex, r)).toBe(true);
    expect(verifyReceipt(pubHex, { ...r, line_sha256: "cc" })).toBe(false);
    expect(verifyReceipt(pubHex, { ...r, seq: 8 })).toBe(false);
    expect(verifyReceipt(edKeygen().pubHex, r)).toBe(false);
  });

  it("receipt binds the first identifying digest, else empty", () => {
    expect(receiptArtifactSha({ file_sha256: "f", manifest_hash: "m" })).toBe("f");
    expect(receiptArtifactSha({ manifest_hash: "m", content_digest: "c" })).toBe("m");
    expect(receiptArtifactSha({ workflow_id: "w" })).toBe("");
    expect(receiptArtifactSha(null)).toBe("");
  });
});
