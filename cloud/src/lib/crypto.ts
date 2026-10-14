// Small-input crypto only. The Worker must never hash or buffer whole
// uploads here (10 ms CPU budget, plan §1.2). Large bytes stream straight
// to R2 in the route handlers.

const te = new TextEncoder();

export function randomHex(bytes: number): string {
  const buf = new Uint8Array(bytes);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** SHA-256 over a small string (manifest, token, session id). */
export async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", te.encode(input));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time string compare (HMAC checks, token lookups). */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", te.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);
}

/** HMAC-SHA256 hex over the exact raw body bytes. */
export async function hmacHex(secret: string, body: string | Uint8Array): Promise<string> {
  const key = await hmacKey(secret);
  const data = typeof body === "string" ? te.encode(body) : body;
  const sig = await crypto.subtle.sign("HMAC", key, data);
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Verify `X-EPI-Signature: sha256=<hex>` against the raw body. */
export async function verifyHmac(header: string | null | undefined, secret: string, body: string): Promise<boolean> {
  if (!header || !header.startsWith("sha256=")) return false;
  const expected = await hmacHex(secret, body);
  return safeEqual(header.slice("sha256=".length), expected);
}

/** 32 random bytes as hex: session ids, invite/CSV tokens. */
export function newToken(): string {
  return randomHex(32);
}

/** API key shown once: `epik_` + 40 hex chars. Only sha256 is stored. */
export function newApiKey(): { raw: string; prefix: string } {
  const rand = randomHex(20);
  return { raw: `epik_${rand}`, prefix: rand.slice(0, 8) };
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function newId(prefix: string): string {
  return `${prefix}_${randomHex(12)}`;
}
