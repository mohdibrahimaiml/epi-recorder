// Signing keys (@noble/*, pure TS: identical behavior in Workers and tests).
//
// Two keys, two jobs (probed against live Rekor 2026-10-15, docs/CLOUD.md):
// - witness key (Ed25519): signs daily checkpoints. Reviewers verify with
//   the published key. Raw-message signatures (Ed25519 has no prehash).
// - anchor key (ECDSA P-256): submits the checkpoint sha256 to Rekor
//   (hashedrekord v1, x509/PEM). Rekor rejects Ed25519+x509 entries, so the
//   anchor key exists for Rekor only and is documented as such.
// Noble v2 notes (verified by experiment, cloud/test/signing.test.ts):
// - ECDSA sign/verify PRE-HASH with sha256 by default: always pass RAW
//   bytes (it applies sha256 itself). Passing a digest double-hashes.
// - verify REJECTS high-S by default. Noble always emits low-S, and Rekor
//   accepted ours (HTTP 201), so production is unaffected.

import { ed25519 } from "@noble/curves/ed25519.js";
import { p256 } from "@noble/curves/nist.js";

export function edKeygen(): { secretHex: string; pubHex: string } {
  const secret = ed25519.utils.randomSecretKey();
  return { secretHex: hex(secret), pubHex: hex(ed25519.getPublicKey(secret)) };
}

/** Derive the public key hex from a 32-byte secret hex. */
export function edPubOfSecret(secretHex: string): string {
  return hex(ed25519.getPublicKey(unhex(secretHex, 32, "ed25519 secret")));
}

export function edSign(secretHex: string, message: Uint8Array): string {
  return hex(ed25519.sign(message, unhex(secretHex, 32, "ed25519 secret")));
}

export function edVerify(pubHex: string, message: Uint8Array, sigHex: string): boolean {
  try {
    return ed25519.verify(unhex(sigHex, 64, "signature"), message, unhex(pubHex, 32, "ed25519 public key"));
  } catch {
    return false;
  }
}

/** PKIX SubjectPublicKeyInfo DER for an Ed25519 key (for display/pinning). */
export function edSpkiDerB64(pubHex: string): string {
  const prefix = unhex("302a300506032b6570032100", 12, "spki prefix");
  return b64(new Uint8Array([...prefix, ...unhex(pubHex, 32, "ed25519 public key")]));
}

export function p256Keygen(): { secretHex: string; pubUncompressedHex: string } {
  const secret = p256.utils.randomSecretKey();
  return { secretHex: hex(secret), pubUncompressedHex: hex(p256.getPublicKey(secret, false)) };
}

/** Derive the uncompressed public key hex from a 32-byte secret hex. */
export function p256PubOfSecret(secretHex: string): string {
  return hex(p256.getPublicKey(unhex(secretHex, 32, "p256 secret"), false));
}

/** Standard ECDSA over sha256(message). Returns DER-encoded (r, s). */
export function p256SignDer(secretHex: string, message: Uint8Array): Uint8Array {
  const compact = p256.sign(message, unhex(secretHex, 32, "p256 secret"));
  const r = BigInt(`0x${hex(compact.subarray(0, 32))}`);
  const s = BigInt(`0x${hex(compact.subarray(32, 64))}`);
  const ri = derInt(r);
  const si = derInt(s);
  return new Uint8Array([0x30, ri.length + si.length, ...ri, ...si]);
}

export function p256VerifyDer(pubUncompressedHex: string, message: Uint8Array, derSig: Uint8Array): boolean {
  try {
    const { r, s } = parseDerSig(derSig);
    const compact = new Uint8Array(64);
    compact.set(pad32(r), 0);
    compact.set(pad32(s), 32);
    return p256.verify(compact, message, unhex(pubUncompressedHex, 65, "p256 public key"));
  } catch {
    return false;
  }
}

/** PKIX SPKI DER for a P-256 key (Rekor publicKey + well-known publish). */
export function p256SpkiDer(pubUncompressedHex: string): Uint8Array {
  const prefix = unhex("3059301306072a8648ce3d020106082a8648ce3d030107034200", 26, "spki prefix");
  return new Uint8Array([...prefix, ...unhex(pubUncompressedHex, 65, "p256 public key")]);
}

export function p256SpkiPem(pubUncompressedHex: string): string {
  const b64der = b64(p256SpkiDer(pubUncompressedHex));
  const lines = b64der.match(/.{1,64}/g) ?? [b64der];
  return `-----BEGIN PUBLIC KEY-----\n${lines.join("\n")}\n-----END PUBLIC KEY-----\n`;
}

function derInt(x: bigint): number[] {
  let b = hexToBytes(x.toString(16).padStart(64, "0"));
  let i = 0;
  while (i < b.length - 1 && b[i] === 0) i++;
  b = b.subarray(i);
  if (b[0]! & 0x80) b = new Uint8Array([0, ...b]);
  return [0x02, b.length, ...b];
}

function parseDerSig(der: Uint8Array): { r: bigint; s: bigint } {
  let o = 0;
  const take = (n: number) => {
    const v = der.subarray(o, o + n);
    o += n;
    return v;
  };
  if (take(1)[0] !== 0x30) throw new Error("not a sequence");
  const len = take(1)[0]!;
  if (len !== der.length - 2) throw new Error("bad sequence length");
  const readInt = () => {
    if (take(1)[0] !== 0x02) throw new Error("not an integer");
    const l = take(1)[0]!;
    return BigInt(`0x${hex(take(l))}` || "0");
  };
  const r = readInt();
  const s = readInt();
  if (o !== der.length) throw new Error("trailing bytes");
  return { r, s };
}

function pad32(x: bigint): Uint8Array {
  let h = x.toString(16);
  if (h.length > 64) h = h.slice(-64); // strip DER leading-zero padding
  return unhex(h.padStart(64, "0"), 32, "sig part");
}

function hex(b: Uint8Array): string {
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

function hexToBytes(h: string): Uint8Array {
  if (!/^[0-9a-fA-F]*$/.test(h) || h.length % 2 !== 0) throw new Error("bad hex");
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.slice(2 * i, 2 * i + 2), 16);
  return out;
}

function unhex(h: string, want: number, what: string): Uint8Array {
  const b = hexToBytes(h.toLowerCase());
  if (b.length !== want) throw new Error(`bad ${what} length`);
  return b;
}

function b64(b: Uint8Array): string {
  let s = "";
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
}
