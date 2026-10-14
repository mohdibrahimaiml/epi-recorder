import { describe, expect, it } from "vitest";
import { createPublicKey, createSign, createVerify, generateKeyPairSync } from "node:crypto";
import {
  edKeygen,
  edPubOfSecret,
  edSign,
  edSpkiDerB64,
  edVerify,
  p256Keygen,
  p256PubOfSecret,
  p256SignDer,
  p256SpkiDer,
  p256SpkiPem,
  p256VerifyDer,
} from "../src/lib/signing.ts";

const te = new TextEncoder();

describe("ed25519 (witness key)", () => {
  it("signs and verifies; rejects tampering and wrong keys", () => {
    const k = edKeygen();
    const msg = te.encode('{"inbox":"a","day":"d","count":1,"head_hash":"h"}');
    const sig = edSign(k.secretHex, msg);
    expect(edVerify(k.pubHex, msg, sig)).toBe(true);
    expect(edVerify(k.pubHex, te.encode(msg + "x"), sig)).toBe(false);
    expect(edVerify(edKeygen().pubHex, msg, sig)).toBe(false);
    expect(edVerify(k.pubHex, msg, "00".repeat(64))).toBe(false);
    expect(edVerify("nothex", msg, sig)).toBe(false);
  });

  it("derives the same public key twice", () => {
    const k = edKeygen();
    expect(edPubOfSecret(k.secretHex)).toBe(k.pubHex);
  });

  it("SPKI DER has the RFC 8410 shape", () => {
    const pubHex = "11".repeat(32);
    const raw = Buffer.from(edSpkiDerB64(pubHex), "base64");
    expect(raw.subarray(0, 12).toString("hex")).toBe("302a300506032b6570032100");
    expect(raw.subarray(12).toString("hex")).toBe(pubHex);
  });
});

describe("p256 (anchor key)", () => {
  it("signs raw bytes; node:crypto verifies (interop)", () => {
    const k = p256Keygen();
    const msg = te.encode('{"checkpoint":1}');
    const der = p256SignDer(k.secretHex, msg);
    expect(p256VerifyDer(k.pubUncompressedHex, msg, der)).toBe(true);
    const pem = p256SpkiPem(k.pubUncompressedHex);
    const v = createVerify("sha256");
    v.update(msg);
    v.end();
    expect(v.verify(createPublicKey(pem), der)).toBe(true);
  });

  it("verifies node:crypto signatures (interop the other way)", () => {
    const { publicKey, privateKey } = generateKeyPairSync("ec", { namedCurve: "prime256v1" });
    const jwk = publicKey.export({ format: "jwk" });
    const pubHex = "04" + Buffer.from(jwk.x!, "base64url").toString("hex") + Buffer.from(jwk.y!, "base64url").toString("hex");
    const msg = te.encode("hello rekor");
    // Noble rejects high-S by default; ours are always low-S. Retry node
    // (random-S) until it deals low-S — P(fail 10x) is negligible.
    let derSig: Uint8Array | null = null;
    for (let i = 0; i < 10 && !derSig; i++) {
      const s = createSign("sha256");
      s.update(msg);
      s.end();
      const cand = new Uint8Array(s.sign(privateKey));
      try {
        if (p256VerifyDer(pubHex, msg, cand)) derSig = cand;
      } catch {
        /* keep trying */
      }
    }
    expect(derSig).not.toBeNull();
    expect(p256VerifyDer(pubHex, te.encode("hello rekot"), derSig!)).toBe(false);
  });

  it("SPKI DER matches node:crypto byte-for-byte", () => {
    const k = p256Keygen();
    const mine = Buffer.from(p256SpkiDer(k.pubUncompressedHex));
    const nodeDer = createPublicKey(p256SpkiPem(k.pubUncompressedHex)).export({ format: "der", type: "spki" });
    expect(mine.equals(nodeDer)).toBe(true);
  });

  it("derives the same public key twice", () => {
    const k = p256Keygen();
    expect(p256PubOfSecret(k.secretHex)).toBe(k.pubUncompressedHex);
  });
});
