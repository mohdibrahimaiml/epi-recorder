// Third-party anchoring (all free): Sigstore Rekor public transparency log
// + RFC 3161 timestamp from FreeTSA. Both are best-effort: failures leave
// the checkpoint signed-but-unanchored and the next cron retries.
//
// Rekor entry shape was verified live against rekor.sigstore.dev: hashedrekord
// v1, x509/PEM P-256 key, DER(r,s) signature over the raw checkpoint bytes.
// Ed25519 keys are rejected by Rekor, so anchoring uses a dedicated P-256
// key (ANCHOR_SIGNING_KEY); checkpoints themselves stay Ed25519.

import { encodeTimestampReq, parseTimestampResp, toB64 } from "./der.ts";
import { p256SpkiPem, p256SignDer } from "./signing.ts";

export const REKOR_URL = "https://rekor.sigstore.dev/api/v1/log/entries";
export const FREETSA_URL = "https://freetsa.org/tsr";

export interface RekorEntry {
  kind: "hashedrekord";
  apiVersion: "0.0.1";
  spec: {
    data: { hash: { algorithm: "sha256"; value: string } };
    signature: { format: "x509"; publicKey: { content: string }; content: string };
  };
}

/** hashedrekord v1: sha256(checkpoint bytes), DER sig, PEM P-256 key. */
export function buildRekorEntry(hashHex: string, anchorPubHex: string, sigDer: Uint8Array): RekorEntry {
  return {
    kind: "hashedrekord",
    apiVersion: "0.0.1",
    spec: {
      data: { hash: { algorithm: "sha256", value: hashHex } },
      signature: {
        format: "x509",
        publicKey: { content: b64str(p256SpkiPem(anchorPubHex)) },
        content: b64bytes(sigDer),
      },
    },
  };
}

export interface RekorResult {
  uuid: string;
  logIndex: number;
}

export async function submitRekor(fetchFn: typeof fetch, entry: RekorEntry): Promise<RekorResult> {
  const res = await fetchFn(REKOR_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(entry),
  });
  if (res.status !== 201) throw new Error(`Rekor rejected the entry (HTTP ${res.status})`);
  const body = (await res.json()) as Record<string, { logIndex: number }>;
  const uuid = Object.keys(body)[0];
  if (!uuid) throw new Error("Rekor returned no UUID");
  return { uuid, logIndex: body[uuid]!.logIndex };
}

export interface TsaResult {
  tokenB64: string;
}

/** RFC 3161 stamp over the checkpoint sha256. Throws on non-granted status. */
export async function requestTimestamp(
  fetchFn: typeof fetch,
  digest: Uint8Array,
  nonce: number,
): Promise<TsaResult> {
  const req = encodeTimestampReq(digest, nonce);
  const res = await fetchFn(FREETSA_URL, {
    method: "POST",
    headers: { "Content-Type": "application/timestamp-query", Accept: "application/timestamp-reply" },
    body: req as unknown as BodyInit,
  });
  if (!res.ok) throw new Error(`FreeTSA HTTP ${res.status}`);
  const parsed = parseTimestampResp(new Uint8Array(await res.arrayBuffer()));
  if (parsed.status !== 0 && parsed.status !== 1) throw new Error(`FreeTSA status ${parsed.status}`);
  if (!parsed.tokenRaw) throw new Error("FreeTSA returned no token");
  return { tokenB64: toB64(parsed.tokenRaw) };
}

/** Anchor one checkpoint: P-256 sign, Rekor submit, TSA stamp. */
export async function anchorCheckpoint(
  fetchFn: typeof fetch,
  opts: {
    checkpointBytes: Uint8Array;
    checkpointHashHex: string;
    digestBytes: Uint8Array;
    anchorSecretHex: string;
    anchorPubHex: string;
    tsaNonce: number;
  },
): Promise<{ rekor: RekorResult; tsa: TsaResult }> {
  const sigDer = p256SignDer(opts.anchorSecretHex, opts.checkpointBytes);
  const rekor = await submitRekor(fetchFn, buildRekorEntry(opts.checkpointHashHex, opts.anchorPubHex, sigDer));
  const tsa = await requestTimestamp(fetchFn, opts.digestBytes, opts.tsaNonce);
  return { rekor, tsa };
}

function b64str(s: string): string {
  let out = "";
  const b = new TextEncoder().encode(s);
  for (let i = 0; i < b.length; i += 0x8000) out += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(out);
}

function b64bytes(b: Uint8Array): string {
  let s = "";
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
}
