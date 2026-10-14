import { describe, expect, it, vi } from "vitest";
import { createVerify, createPublicKey } from "node:crypto";
import {
  FREETSA_URL,
  REKOR_URL,
  anchorCheckpoint,
  buildRekorEntry,
  requestTimestamp,
  submitRekor,
} from "../src/lib/anchor.ts";
import { p256Keygen, p256SpkiPem } from "../src/lib/signing.ts";
import { sha256Hex } from "../src/lib/crypto.ts";

const te = new TextEncoder();

function resp(status: number, json: unknown, buf?: Uint8Array): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => json,
    arrayBuffer: async () => buf!.buffer as ArrayBuffer,
    text: async () => JSON.stringify(json),
  } as unknown as Response;
}

describe("Rekor client", () => {
  it("builds the live-proven hashedrekord shape", () => {
    const k = p256Keygen();
    const e = buildRekorEntry("ab".repeat(32), k.pubUncompressedHex, new Uint8Array([0x30, 0x06, 0x02, 0x01, 0x01, 0x02, 0x01, 0x02]));
    expect(e.kind).toBe("hashedrekord");
    expect(e.apiVersion).toBe("0.0.1");
    expect(e.spec.data.hash).toEqual({ algorithm: "sha256", value: "ab".repeat(32) });
    expect(e.spec.signature.format).toBe("x509");
    expect(Buffer.from(e.spec.signature.publicKey.content, "base64").toString("utf8")).toContain("BEGIN PUBLIC KEY");
  });

  it("parses uuid + log index from a 201", async () => {
    const fetchFn = vi.fn(async () => resp(201, { deadbeef1234: { logIndex: 99 } }));
    const r = await submitRekor(fetchFn as unknown as typeof fetch, buildRekorEntry("ab".repeat(32), p256Keygen().pubUncompressedHex, new Uint8Array([1])));
    expect(r).toEqual({ uuid: "deadbeef1234", logIndex: 99 });
    expect(fetchFn).toHaveBeenCalledOnce();
    expect((fetchFn.mock.calls[0] as unknown[])[0]).toBe(REKOR_URL);
  });

  it("throws on rejection (nothing is recorded as anchored)", async () => {
    const fetchFn = vi.fn(async () => resp(400, { message: "nope" }));
    await expect(submitRekor(fetchFn as unknown as typeof fetch, buildRekorEntry("ab".repeat(32), p256Keygen().pubUncompressedHex, new Uint8Array([1])))).rejects.toThrow(/HTTP 400/);
  });
});

describe("FreeTSA client", () => {
  it("returns the token on granted status", async () => {
    const token = new Uint8Array([0xa0, 0x04, 0x04, 0x02, 0xde, 0xad]);
    const der = new Uint8Array([0x30, 0x0b, 0x30, 0x03, 0x02, 0x01, 0x00, ...token]);
    const fetchFn = vi.fn(async (url: unknown, init: unknown) => {
      expect(url).toBe(FREETSA_URL);
      expect((init as { headers: Record<string, string> }).headers["Content-Type"]).toBe("application/timestamp-query");
      return resp(200, {}, der);
    });
    const t = await requestTimestamp(fetchFn as unknown as typeof fetch, new Uint8Array(32).fill(7), 42);
    expect(t.tokenB64).toBe(Buffer.from(token).toString("base64"));
  });

  it("throws on failure status", async () => {
    const der = new Uint8Array([0x30, 0x05, 0x30, 0x03, 0x02, 0x01, 0x02]);
    const fetchFn = vi.fn(async () => resp(200, {}, der));
    await expect(requestTimestamp(fetchFn as unknown as typeof fetch, new Uint8Array(32), 1)).rejects.toThrow(/status 2/);
  });
});

describe("anchorCheckpoint", () => {
  it("signs with P-256 and the entry verifies under node:crypto", async () => {
    const k = p256Keygen();
    const canonical = te.encode('{"inbox":"inb_1","day":"2026-10-15","count":2,"head_hash":"ff"}');
    const hashHex = await sha256Hex('{"inbox":"inb_1","day":"2026-10-15","count":2,"head_hash":"ff"}');
    const token = new Uint8Array([0xa0, 0x04, 0x04, 0x02, 0xde, 0xad]);
    const tsaDer = new Uint8Array([0x30, 0x0b, 0x30, 0x03, 0x02, 0x01, 0x00, ...token]);
    let posted: { url: unknown; body: string } | null = null;
    const fetchFn = vi.fn(async (url: unknown, init: { body: { toString(): string } | Uint8Array; headers: Record<string, string> }) => {
      if (url === REKOR_URL) {
        posted = { url, body: init.body.toString() };
        return resp(201, { uuid1: { logIndex: 7 } });
      }
      return resp(200, {}, tsaDer);
    });
    const out = await anchorCheckpoint(fetchFn as unknown as typeof fetch, {
      checkpointBytes: canonical,
      checkpointHashHex: hashHex,
      digestBytes: Uint8Array.from(Buffer.from(hashHex, "hex")),
      anchorSecretHex: k.secretHex,
      anchorPubHex: k.pubUncompressedHex,
      tsaNonce: 99,
    });
    expect(out.rekor).toEqual({ uuid: "uuid1", logIndex: 7 });
    // The submitted signature is a real ECDSA signature over the canonical bytes.
    const entry = JSON.parse(posted!.body) as { spec: { data: { hash: { value: string } }; signature: { content: string; publicKey: { content: string } } } };
    expect(entry.spec.data.hash.value).toBe(hashHex);
    const v = createVerify("sha256");
    v.update(canonical);
    v.end();
    expect(v.verify(createPublicKey(p256SpkiPem(k.pubUncompressedHex)), Buffer.from(entry.spec.signature.content, "base64"))).toBe(true);
  });
});
