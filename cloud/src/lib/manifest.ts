// Manifest signature verification (ported from website/js/epi-manifest-preimage.js).
// Dispatch matches epi_core._version.JCS_INTRODUCED_TUPLE (4, 4, 1):
//   spec < 4.4.1 → legacy json.dumps-style with preserved float text
//   spec >= 4.4.1 → JCS (900.0 hashes as "900")
// Omit null content_truncated, policy_load_status, producer_version.
// v1.x CBOR manifests cannot be verified here (rejected, not mislabelled).

import { edVerify } from "./signing.ts";
import { sha256Hex } from "./crypto.ts";

const te = new TextEncoder();

type Tok =
  | { type: "string"; value: string }
  | { type: "number"; raw: string }
  | { type: "true" | "false" | "null"; value: boolean | null }
  | { type: "{" | "}" | "[" | "]" | ":" | "," };

type JVal = string | boolean | null | { __num: string } | JVal[] | { [k: string]: JVal };

function tokenizeJSON(str: string): Tok[] {
  const tokens: Tok[] = [];
  let i = 0;
  while (i < str.length) {
    const c = str[i]!;
    if (c === " " || c === "\t" || c === "\n" || c === "\r") {
      i++;
      continue;
    }
    if (c === '"') {
      i++;
      let s = "";
      while (i < str.length) {
        const ch = str[i]!;
        if (ch === "\\") {
          i++;
          const e = str[i]!;
          if (e === "n") s += "\n";
          else if (e === "t") s += "\t";
          else if (e === "r") s += "\r";
          else if (e === "b") s += "\b";
          else if (e === "f") s += "\f";
          else if (e === "u") {
            s += String.fromCharCode(parseInt(str.substring(i + 1, i + 5), 16));
            i += 4;
          } else s += e;
          i++;
        } else if (ch === '"') {
          i++;
          break;
        } else {
          s += ch;
          i++;
        }
      }
      tokens.push({ type: "string", value: s });
      continue;
    }
    if (c === "{" || c === "}" || c === "[" || c === "]" || c === ":" || c === ",") {
      tokens.push({ type: c });
      i++;
      continue;
    }
    if (str.substring(i, i + 4) === "true") {
      tokens.push({ type: "true", value: true });
      i += 4;
      continue;
    }
    if (str.substring(i, i + 5) === "false") {
      tokens.push({ type: "false", value: false });
      i += 5;
      continue;
    }
    if (str.substring(i, i + 4) === "null") {
      tokens.push({ type: "null", value: null });
      i += 4;
      continue;
    }
    if (c === "-" || (c >= "0" && c <= "9")) {
      const start = i;
      if (str[i] === "-") i++;
      while (i < str.length && str[i]! >= "0" && str[i]! <= "9") i++;
      if (str[i] === ".") {
        i++;
        while (i < str.length && str[i]! >= "0" && str[i]! <= "9") i++;
      }
      if (str[i] === "e" || str[i] === "E") {
        i++;
        if (str[i] === "+" || str[i] === "-") i++;
        while (i < str.length && str[i]! >= "0" && str[i]! <= "9") i++;
      }
      tokens.push({ type: "number", raw: str.substring(start, i) });
      continue;
    }
    throw new Error(`Unexpected character ${c} at ${i}`);
  }
  return tokens;
}

function parseJSONPreserveNumbers(text: string): JVal {
  const tokens = tokenizeJSON(text);
  let pos = 0;
  function parseValue(): JVal {
    const tok = tokens[pos]!;
    if (!tok) throw new Error("Unexpected end");
    if (tok.type === "number") {
      pos++;
      return { __num: tok.raw };
    }
    if (tok.type === "string" || tok.type === "true" || tok.type === "false" || tok.type === "null") {
      pos++;
      return tok.value as string | boolean | null;
    }
    if (tok.type === "[") return parseArray();
    if (tok.type === "{") return parseObject();
    throw new Error(`Unexpected token ${tok.type}`);
  }
  function parseArray(): JVal[] {
    pos++;
    const arr: JVal[] = [];
    if (tokens[pos] && tokens[pos]!.type === "]") {
      pos++;
      return arr;
    }
    for (;;) {
      arr.push(parseValue());
      const tok = tokens[pos++]!;
      if (!tok) throw new Error("Unterminated array");
      if (tok.type === ",") continue;
      if (tok.type === "]") return arr;
      throw new Error(`Expected , or ] got ${tok.type}`);
    }
  }
  function parseObject(): { [k: string]: JVal } {
    pos++;
    const obj: { [k: string]: JVal } = {};
    if (tokens[pos] && tokens[pos]!.type === "}") {
      pos++;
      return obj;
    }
    for (;;) {
      const keyTok = tokens[pos++]!;
      if (!keyTok || keyTok.type !== "string") throw new Error("Expected string key");
      if (!tokens[pos] || tokens[pos]!.type !== ":") throw new Error("Expected :");
      pos++;
      obj[keyTok.value] = parseValue();
      const tok = tokens[pos++]!;
      if (!tok) throw new Error("Unterminated object");
      if (tok.type === ",") continue;
      if (tok.type === "}") return obj;
      throw new Error(`Expected , or } got ${tok.type}`);
    }
  }
  const val = parseValue();
  if (pos !== tokens.length) throw new Error("Unexpected trailing tokens");
  return val;
}

function jcsNumberFromRaw(raw: string): string {
  if (/^-?(0|[1-9][0-9]*)$/.test(raw)) return raw;
  const n = Number(raw);
  if (!isFinite(n)) return "null";
  return String(n);
}

function epiUtcZ(s: unknown): unknown {
  if (typeof s !== "string") return s;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$/.exec(s);
  if (!m || !m[8]) return s;
  let ms = Date.UTC(+m[1]!, +m[2]! - 1, +m[3]!, +m[4]!, +m[5]!, +m[6]!);
  const off = m[8]!;
  if (off !== "Z") {
    const sign = off[0] === "+" ? 1 : -1;
    const parts = off.slice(1).split(":");
    ms -= (parseInt(parts[0]!, 10) * 60 + parseInt(parts[1] || "0", 10)) * sign * 60000;
  }
  const d = new Date(ms);
  const p = (n: number) => (n < 10 ? "0" : "") + n;
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}Z`;
}

function sortedJSON(obj: JVal, jcsNumbers: boolean): string {
  if (obj && typeof obj === "object" && "__num" in (obj as Record<string, unknown>)) {
    const raw = (obj as { __num: string }).__num;
    return jcsNumbers ? jcsNumberFromRaw(raw) : raw;
  }
  if (obj === null) return "null";
  if (typeof obj === "string") return JSON.stringify(obj);
  if (typeof obj === "number") return String(Number.isFinite(obj) ? obj : "null");
  if (typeof obj === "boolean") return String(obj);
  if (Array.isArray(obj)) return `[${obj.map((v) => sortedJSON(v, jcsNumbers)).join(",")}]`;
  const keys = Object.keys(obj as Record<string, JVal>).sort();
  const parts: string[] = [];
  for (const k of keys) {
    const v = (obj as Record<string, JVal>)[k];
    if (v !== undefined) parts.push(`${JSON.stringify(k)}:${sortedJSON(v as JVal, jcsNumbers)}`);
  }
  return `{${parts.join(",")}}`;
}

function normalizeCreatedAt(manifest: JVal): JVal {
  const walk = (o: JVal): void => {
    if (!o || typeof o !== "object" || "__num" in (o as Record<string, unknown>)) return;
    if (Array.isArray(o)) {
      for (let i = 0; i < o.length; i++) {
        const v: JVal | undefined = o[i];
        if (v === undefined) continue;
        o[i] = (typeof v === "string" ? epiUtcZ(v) : (walk(v), v)) as JVal;
      }
      return;
    }
    const rec = o as Record<string, JVal>;
    for (const k of Object.keys(rec)) {
      const v: JVal | undefined = rec[k];
      if (typeof v === "string") rec[k] = epiUtcZ(v) as JVal;
      else if (v !== undefined) walk(v);
    }
  };
  walk(manifest);
  return manifest;
}

function omitAbsentOptionalHashFields(manifest: Record<string, JVal>): void {
  for (const k of ["content_truncated", "policy_load_status", "producer_version"]) {
    if (manifest[k] === null || manifest[k] === undefined) delete manifest[k];
  }
}

function isPreJcsSpec(sv: unknown): boolean {
  const s = String(sv ?? "").replace(/^v/i, "");
  const a = s.split(/[^\d]+/).map((x) => parseInt(x, 10) || 0);
  const maj = a[0] || 0;
  const min = a[1] || 0;
  const pat = a[2] || 0;
  if (maj <= 1) return false;
  if (maj !== 4) return maj < 4;
  if (min !== 4) return min < 4;
  return pat < 1;
}

export function specIsVerifiable(sv: unknown): boolean {
  // JSON manifests (spec 2.x+) verify here; v1.x CBOR and unparseable specs
  // do not (same dispatch as epi_core.serialize.canonical_format_for, minus
  // the CBOR branch, which needs the full Python implementation).
  const s = String(sv ?? "");
  if (!s) return false;
  const major = parseInt(s.replace(/^v/i, "").split(".")[0] || "", 10);
  return Number.isFinite(major) && major >= 2;
}

/** Canonical JSON text of a manifest (signature excluded). Exported for tests. */
export function canonicalManifestText(rawManifestText: string): string {
  let peek: Record<string, unknown> = {};
  try {
    peek = JSON.parse(rawManifestText) as Record<string, unknown>;
  } catch {
    // fall through with empty peek
  }
  if (!specIsVerifiable(peek.spec_version)) {
    throw new Error("Legacy CBOR manifest (v1.x) cannot be verified on the server — use epi verify on the CLI");
  }
  const legacy = isPreJcsSpec(peek.spec_version);
  const manifest = (legacy ? parseJSONPreserveNumbers(rawManifestText) : (peek as unknown as JVal)) as Record<string, JVal>;
  omitAbsentOptionalHashFields(manifest);
  normalizeCreatedAt(manifest);
  delete manifest.signature;
  return sortedJSON(manifest, !legacy);
}

/** Canonical sha256 of a manifest text (signature field excluded). */
export async function computeManifestHash(rawManifestText: string): Promise<string> {
  return sha256HexBytes(te.encode(canonicalManifestText(rawManifestText)));
}

async function sha256HexBytes(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** The one fingerprint EPI shows (parity with epi_core.keys.key_fingerprint). */
export async function keyFingerprint(publicKeyHex: string): Promise<string> {
  return (await sha256Hex(publicKeyHex.trim().toLowerCase())).slice(0, 16);
}

export type ManifestCheck =
  | { status: "valid"; fingerprint: string }
  | { status: "invalid"; fingerprint: string | null; reason: string }
  | { status: "unsigned" };

/** Verify an .epi manifest's Ed25519 seal (≤4 KB, cheap). */
export async function verifyManifestSignature(rawManifestText: string): Promise<ManifestCheck> {
  let manifest: Record<string, unknown>;
  try {
    manifest = JSON.parse(rawManifestText) as Record<string, unknown>;
  } catch {
    return { status: "invalid", fingerprint: null, reason: "manifest is not JSON" };
  }
  const sigStr = manifest.signature;
  const pubHex = manifest.public_key;
  if (typeof sigStr !== "string" || !sigStr) return { status: "unsigned" };
  if (typeof pubHex !== "string" || !/^[0-9a-fA-F]{64}$/.test(pubHex)) {
    return { status: "invalid", fingerprint: null, reason: "bad public_key" };
  }
  const fingerprint = await keyFingerprint(pubHex);
  const parts = sigStr.split(":");
  if (parts.length !== 3 || parts[0] !== "ed25519" || parts[1] !== fingerprint) {
    return { status: "invalid", fingerprint, reason: "key name does not match public key" };
  }
  let hashHex: string;
  try {
    hashHex = await computeManifestHash(rawManifestText);
  } catch (err) {
    return { status: "invalid", fingerprint, reason: err instanceof Error ? err.message : "hash failed" };
  }
  const ok = edVerify(pubHex, Uint8Array.from(hashHex.match(/.{2}/g)!.map((h) => parseInt(h, 16))), parts[2]!);
  return ok ? { status: "valid", fingerprint } : { status: "invalid", fingerprint, reason: "signature invalid" };
}
