// AES-GCM secret box (WebCrypto: Workers + Node). Encrypts inbox HMAC
// secrets at rest (inboxes.hmac_secret_enc = base64(nonce 12B ‖ ciphertext)).

const te = new TextEncoder();

async function importKey(secretHex: string): Promise<CryptoKey> {
  const raw = Uint8Array.from(secretHex.match(/.{2}/g)!.map((h) => parseInt(h, 16)));
  if (raw.length !== 32) throw new Error("INBOX_SECRET_KEY must be 32 bytes hex");
  return crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

export async function sealSecret(secretHex: string, plaintext: string): Promise<string> {
  const key = await importKey(secretHex);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, key, te.encode(plaintext)));
  const out = new Uint8Array(12 + ct.length);
  out.set(nonce, 0);
  out.set(ct, 12);
  let s = "";
  for (const b of out) s += String.fromCharCode(b);
  return btoa(s);
}

export async function openSecret(secretHex: string, sealedB64: string): Promise<string> {
  const key = await importKey(secretHex);
  const raw = Uint8Array.from(atob(sealedB64), (c) => c.charCodeAt(0));
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv: raw.subarray(0, 12) }, key, raw.subarray(12));
  return new TextDecoder().decode(pt);
}
