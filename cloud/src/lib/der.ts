// Minimal DER for RFC 3161 timestamps. Encodes TimeStampReq (sha256) and
// parses TimeStampResp status + token. Not a general ASN.1 library.

export function sha256Oid(): number[] {
  return [0x06, 0x09, 0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01];
}

function lenBytes(n: number): number[] {
  if (n < 128) return [n];
  const b: number[] = [];
  let x = n;
  while (x > 0) {
    b.unshift(x & 0xff);
    x >>= 8;
  }
  return [0x80 | b.length, ...b];
}

function tlv(tag: number, ...content: Array<number | number[]>): number[] {
  const body = content.flat() as number[];
  return [tag, ...lenBytes(body.length), ...body];
}

const seq = (...parts: number[][]): number[] => tlv(0x30, ...parts);


export function intVal(n: number): number[] {
  if (n === 0) return [0x02, 0x01, 0x00];
  const b: number[] = [];
  let x = n;
  while (x > 0) {
    b.unshift(x & 0xff);
    x = Math.floor(x / 256);
  }
  if (b[0]! & 0x80) b.unshift(0);
  return tlv(0x02, ...b);
}

/** TimeStampReq over a sha256 digest. nonce must be a positive safe integer. */
export function encodeTimestampReq(digest: Uint8Array, nonce: number): Uint8Array {
  if (digest.length !== 32) throw new Error("sha256 digest required");
  if (!Number.isSafeInteger(nonce) || nonce <= 0) throw new Error("positive nonce required");
  const req = seq(
    intVal(1),
    seq(seq(sha256Oid(), tlv(0x05)), tlv(0x04, ...digest)),
    intVal(nonce),
  );
  return new Uint8Array(req);
}

export interface TLV {
  tag: number;
  value: Uint8Array;
  raw: Uint8Array; // tag+length+value
  children: TLV[];
}

export function parseTLV(buf: Uint8Array, offset = 0): TLV {
  const tag = buf[offset]!;
  let o = offset + 1;
  let len = buf[o++]!;
  if (len & 0x80) {
    const n = len & 0x7f;
    if (n === 0 || n > 4) throw new Error("unsupported length");
    len = 0;
    for (let i = 0; i < n; i++) len = len * 256 + buf[o++]!;
  }
  const value = buf.subarray(o, o + len);
  if (value.length !== len) throw new Error("truncated DER");
  const raw = buf.subarray(offset, o + len);
  const children: TLV[] = [];
  if (tag === 0x30 || tag === 0x31) {
    let c = 0;
    while (c < value.length) {
      const child = parseTLV(value, c);
      children.push(child);
      c += child.raw.length;
    }
  }
  return { tag, value, raw, children };
}

/** Parse a TimeStampResp: status code + raw bytes of the [0] token TLV. */
export function parseTimestampResp(der: Uint8Array): { status: number; tokenRaw: Uint8Array | null } {
  const root = parseTLV(der);
  if (root.tag !== 0x30 || root.children.length < 1) throw new Error("not a TimeStampResp");
  const statusInfo = root.children[0]!;
  if (statusInfo.tag !== 0x30 || statusInfo.children.length < 1) throw new Error("no status");
  const code = statusInfo.children[0]!;
  if (code.tag !== 0x02) throw new Error("no status code");
  let status = 0;
  for (const b of code.value) status = status * 256 + b;
  const token = root.children.length > 1 && root.children[1]!.tag === 0xa0 ? root.children[1]!.raw : null;
  return { status, tokenRaw: token };
}

export function toB64(b: Uint8Array): string {
  let s = "";
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
}

export function fromB64(s: string): Uint8Array {
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}

